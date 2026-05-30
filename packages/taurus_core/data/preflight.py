from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from taurus_core.db.models import DailyCandleModel, InstrumentModel, PaperRunModel
from taurus_core.domain.market_data import MarketDataProviderError

LEGACY_MOCK_CANDLE_SOURCE = "mock_market_data"
LEGACY_MOCK_PROVIDERS = {"mock", "mock_market_data"}


def assert_no_legacy_mock_candles(session: Session) -> None:
    count = int(
        session.scalar(
            select(func.count())
            .select_from(DailyCandleModel)
            .where(DailyCandleModel.source == LEGACY_MOCK_CANDLE_SOURCE)
        )
        or 0
    )
    if count:
        raise MarketDataProviderError(
            "Kite market-data import refused to run because this database contains "
            f"{count} legacy mock_market_data candle rows. Use a clean database or "
            "archive/remove those rows before running Kite-backed market data."
        )


def assert_no_legacy_mock_paper_runs(session: Session) -> None:
    legacy_run_ids = [
        run.run_id
        for run in session.scalars(select(PaperRunModel).order_by(PaperRunModel.started_at.desc()))
        if _is_legacy_mock_market_summary(run.market_data_summary)
    ]
    if legacy_run_ids:
        preview = ", ".join(legacy_run_ids[:3])
        suffix = "" if len(legacy_run_ids) <= 3 else f" and {len(legacy_run_ids) - 3} more"
        raise MarketDataProviderError(
            "Kite paper run refused to start because this database contains old "
            f"mock-backed paper-run summaries ({preview}{suffix}). Use a clean "
            "database or archive those paper runs before running Kite-backed paper loops."
        )


def assert_kite_runtime_preflight(session: Session, *, include_paper_runs: bool = False) -> None:
    assert_no_legacy_mock_candles(session)
    if include_paper_runs:
        assert_no_legacy_mock_paper_runs(session)


def assert_active_instruments_available(session: Session) -> None:
    count = int(
        session.scalar(
            select(func.count())
            .select_from(InstrumentModel)
            .where(InstrumentModel.active.is_(True))
        )
        or 0
    )
    if not count:
        raise MarketDataProviderError(
            "No active instruments are available. Run make kite-sync-instruments or "
            "make import-market-data before running this command."
        )


def assert_daily_candles_available(session: Session, *, symbols: list[str] | None = None) -> None:
    statement = select(func.count()).select_from(DailyCandleModel)
    if symbols:
        statement = statement.where(DailyCandleModel.symbol.in_([symbol.upper() for symbol in symbols]))
    count = int(session.scalar(statement) or 0)
    if not count:
        target = f" for {', '.join(symbols)}" if symbols else ""
        raise MarketDataProviderError(
            f"No Kite-imported daily candles are available{target}. Run make import-market-data "
            "before running this command."
        )


def _is_legacy_mock_market_summary(summary: dict[str, object]) -> bool:
    provider = str(summary.get("provider_name") or summary.get("provider") or "").lower()
    source = str(summary.get("source") or "").lower()
    return provider in LEGACY_MOCK_PROVIDERS or source == LEGACY_MOCK_CANDLE_SOURCE
