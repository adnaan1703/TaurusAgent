from __future__ import annotations

from argparse import Namespace
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from pydantic import TypeAdapter, ValidationError

from scripts.manage_profiles import run_profile_command
from taurus_core.config import Settings
from taurus_core.db.repositories import ExecutionRepository, TaurusProfileRepository
from taurus_core.db.session import build_session_factory
from taurus_core.execution.schemas import PaperAccount, paper_account_id
from taurus_core.profiles.schemas import (
    TaurusProfileCreate,
    TaurusProfileResponse,
    TaurusProfileUpdate,
)

PROFILE_LIST_ADAPTER = TypeAdapter(list[TaurusProfileResponse])


def test_profile_schema_validates_slug_name_and_money_precision() -> None:
    profile = TaurusProfileCreate(
        profile_id="client_a-1",
        display_name=" Client A ",
        starting_corpus_inr=Decimal("250000.12345"),
        currency="inr",
        profile_metadata={"desk": "family"},
    )

    assert profile.profile_id == "client_a-1"
    assert profile.display_name == "Client A"
    assert profile.starting_corpus_inr == Decimal("250000.1235")
    assert profile.currency == "INR"

    with pytest.raises(ValidationError, match="profile_id"):
        TaurusProfileCreate(
            profile_id="Client A",
            display_name="Client A",
            starting_corpus_inr=Decimal("250000"),
        )

    with pytest.raises(ValidationError, match="display_name"):
        TaurusProfileCreate(
            profile_id="client-a",
            display_name=" ",
            starting_corpus_inr=Decimal("250000"),
        )

    with pytest.raises(ValidationError, match="starting_corpus_inr"):
        TaurusProfileCreate(
            profile_id="client-a",
            display_name="Client A",
            starting_corpus_inr=Decimal("0"),
        )


def test_profile_repository_lifecycle_filters_archived_profiles(
    postgres_test_settings: Settings,
) -> None:
    session_factory = build_session_factory(postgres_test_settings)
    with session_factory() as session:
        repo = TaurusProfileRepository(session)

        default = repo.ensure_default_profile()
        created = repo.create_profile(
            TaurusProfileCreate(
                profile_id="client-a",
                display_name="Client A",
                starting_corpus_inr=Decimal("250000"),
                description="First client profile",
            )
        )
        session.commit()

        assert default.profile_id == "local-paper"
        assert created.starting_corpus_inr == Decimal("250000.0000")

    with session_factory() as session:
        repo = TaurusProfileRepository(session)
        active_ids = [profile.profile_id for profile in repo.list_profiles()]
        assert active_ids == ["client-a", "local-paper"]

        archived = repo.archive_profile("client-a")
        session.commit()
        assert archived.status == "ARCHIVED"

    with session_factory() as session:
        repo = TaurusProfileRepository(session)
        assert [profile.profile_id for profile in repo.list_profiles()] == ["local-paper"]
        assert [profile.profile_id for profile in repo.list_profiles(include_archived=True)] == [
            "client-a",
            "local-paper",
        ]


def test_update_profile_corpus_before_trading_activity_updates_initial_snapshot(
    postgres_test_settings: Settings,
) -> None:
    session_factory = build_session_factory(postgres_test_settings)
    now = datetime.now(timezone.utc)
    with session_factory() as session:
        repo = TaurusProfileRepository(session)
        repo.create_profile(
            TaurusProfileCreate(
                profile_id="client-a",
                display_name="Client A",
                starting_corpus_inr=Decimal("250000"),
            )
        )
        account = PaperAccount(
            account_id=paper_account_id(portfolio_id="client-a", run_id="run-initial"),
            run_id="run-initial",
            portfolio_id="client-a",
            starting_cash_inr=Decimal("250000"),
            available_cash_inr=Decimal("250000"),
            reserved_cash_inr=Decimal("0"),
            realized_pnl_inr=Decimal("0"),
            unrealized_pnl_inr=Decimal("0"),
            gross_exposure_inr=Decimal("0"),
            equity_inr=Decimal("250000"),
            updated_at=now,
        )
        ExecutionRepository(session).replace_account_state(
            run_id="run-initial",
            portfolio_id="client-a",
            account=account,
            positions=[],
        )
        session.commit()

    with session_factory() as session:
        repo = TaurusProfileRepository(session)
        updated = repo.update_profile_corpus("client-a", Decimal("500000"))
        session.commit()
        assert updated.starting_corpus_inr == Decimal("500000.0000")

    with session_factory() as session:
        account_model = ExecutionRepository(session).latest_account_by_portfolio(
            portfolio_id="client-a"
        )
        assert account_model is not None
        assert account_model.starting_cash_inr == Decimal("500000.0000")
        assert account_model.available_cash_inr == Decimal("500000.0000")
        assert account_model.equity_inr == Decimal("500000.0000")


def test_update_profile_corpus_rejects_trading_activity(
    postgres_test_settings: Settings,
) -> None:
    session_factory = build_session_factory(postgres_test_settings)
    now = datetime.now(timezone.utc)
    with session_factory() as session:
        repo = TaurusProfileRepository(session)
        repo.create_profile(
            TaurusProfileCreate(
                profile_id="client-a",
                display_name="Client A",
                starting_corpus_inr=Decimal("250000"),
            )
        )
        account = PaperAccount(
            account_id=paper_account_id(portfolio_id="client-a", run_id="run-active"),
            run_id="run-active",
            portfolio_id="client-a",
            starting_cash_inr=Decimal("250000"),
            available_cash_inr=Decimal("249000"),
            reserved_cash_inr=Decimal("0"),
            realized_pnl_inr=Decimal("0"),
            unrealized_pnl_inr=Decimal("0"),
            gross_exposure_inr=Decimal("1000"),
            equity_inr=Decimal("250000"),
            updated_at=now,
        )
        ExecutionRepository(session).replace_account_state(
            run_id="run-active",
            portfolio_id="client-a",
            account=account,
            positions=[],
        )
        session.commit()

    with session_factory() as session:
        repo = TaurusProfileRepository(session)
        with pytest.raises(ValueError, match="capital-events milestone"):
            repo.update_profile_corpus("client-a", Decimal("500000"))


def test_profile_update_schema_allows_metadata_and_corpus_patch() -> None:
    update = TaurusProfileUpdate(
        display_name=" Client A ",
        starting_corpus_inr=Decimal("500000"),
        currency="inr",
        profile_metadata={"relationship": "advisory"},
    )

    assert update.display_name == "Client A"
    assert update.starting_corpus_inr == Decimal("500000.0000")
    assert update.currency == "INR"


def test_manage_profiles_cli_create_list_archive_and_update_corpus(
    postgres_test_settings: Settings,
    capsys: pytest.CaptureFixture[str],
) -> None:
    create_args = Namespace(
        command="create",
        profile_id="client-a",
        display_name="Client A",
        corpus_inr="250000",
        currency="INR",
        description="",
        metadata_json='{"owner": "demo"}',
        json=True,
    )
    assert run_profile_command(create_args, postgres_test_settings) == 0
    created = PROFILE_LIST_ADAPTER.validate_json(capsys.readouterr().out)[0]
    assert created.profile_id == "client-a"
    assert created.starting_corpus_inr == Decimal("250000.0000")

    update_args = Namespace(
        command="update-corpus",
        profile_id="client-a",
        corpus_inr="500000",
        json=True,
    )
    assert run_profile_command(update_args, postgres_test_settings) == 0
    updated = PROFILE_LIST_ADAPTER.validate_json(capsys.readouterr().out)[0]
    assert updated.starting_corpus_inr == Decimal("500000.0000")

    list_args = Namespace(command="list", include_archived=False, json=True)
    assert run_profile_command(list_args, postgres_test_settings) == 0
    active_ids = [
        profile.profile_id
        for profile in PROFILE_LIST_ADAPTER.validate_json(capsys.readouterr().out)
    ]
    assert active_ids == ["client-a", "local-paper"]

    archive_args = Namespace(command="archive", profile_id="client-a", json=True)
    assert run_profile_command(archive_args, postgres_test_settings) == 0
    archived = PROFILE_LIST_ADAPTER.validate_json(capsys.readouterr().out)[0]
    assert archived.status == "ARCHIVED"
