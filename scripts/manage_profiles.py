from __future__ import annotations

import argparse
import json
from decimal import Decimal
from typing import Any

from scripts.migrate import run_migrations
from taurus_core.config import Settings, get_settings
from taurus_core.db.repositories import TaurusProfileRepository
from taurus_core.db.session import build_session_factory
from taurus_core.logging import configure_logging
from taurus_core.profiles.schemas import TaurusProfileCreate, TaurusProfileResponse


def run_profile_command(
    args: argparse.Namespace, settings: Settings | None = None
) -> int:
    settings = settings or get_settings()
    run_migrations(settings)
    session_factory = build_session_factory(settings)
    with session_factory() as session:
        repo = TaurusProfileRepository(session)
        repo.ensure_default_profile()
        if args.command == "list":
            profiles = repo.list_profiles(include_archived=args.include_archived)
            _print_profiles(profiles, as_json=args.json)
            return 0
        if args.command == "create":
            profile = TaurusProfileCreate(
                profile_id=args.profile_id,
                display_name=args.display_name,
                starting_corpus_inr=Decimal(args.corpus_inr),
                currency=args.currency,
                description=args.description,
                profile_metadata=_parse_metadata(args.metadata_json),
            )
            model = repo.create_profile(profile)
            session.commit()
            _print_profiles([model], as_json=args.json)
            return 0
        if args.command == "archive":
            model = repo.archive_profile(args.profile_id)
            session.commit()
            _print_profiles([model], as_json=args.json)
            return 0
        if args.command == "update-corpus":
            model = repo.update_profile_corpus(
                args.profile_id, Decimal(args.corpus_inr)
            )
            session.commit()
            _print_profiles([model], as_json=args.json)
            return 0
    raise ValueError(f"Unsupported profile command: {args.command}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Manage Taurus paper-trading profiles."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="List active Taurus profiles.")
    list_parser.add_argument("--include-archived", action="store_true")
    list_parser.add_argument("--json", action="store_true")

    create_parser = subparsers.add_parser("create", help="Create a Taurus profile.")
    create_parser.add_argument("--profile-id", required=True)
    create_parser.add_argument("--display-name", required=True)
    create_parser.add_argument("--corpus-inr", required=True)
    create_parser.add_argument("--currency", default="INR")
    create_parser.add_argument("--description", default="")
    create_parser.add_argument("--metadata-json", default="{}")
    create_parser.add_argument("--json", action="store_true")

    archive_parser = subparsers.add_parser("archive", help="Archive a Taurus profile.")
    archive_parser.add_argument("--profile-id", required=True)
    archive_parser.add_argument("--json", action="store_true")

    corpus_parser = subparsers.add_parser(
        "update-corpus",
        help="Update a profile starting corpus before trading activity exists.",
    )
    corpus_parser.add_argument("--profile-id", required=True)
    corpus_parser.add_argument("--corpus-inr", required=True)
    corpus_parser.add_argument("--json", action="store_true")

    return parser


def _parse_metadata(value: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError("--metadata-json must be a JSON object.") from exc
    if not isinstance(parsed, dict):
        raise ValueError("--metadata-json must be a JSON object.")
    return parsed


def _print_profiles(profiles: list[object], *, as_json: bool) -> None:
    responses = [TaurusProfileResponse.model_validate(profile) for profile in profiles]
    if as_json:
        print(
            json.dumps(
                [profile.model_dump(mode="json") for profile in responses],
                sort_keys=True,
            )
        )
        return

    if not responses:
        print("No profiles found.")
        return
    print("profile_id | display_name | status | starting_corpus_inr | currency")
    for profile in responses:
        print(
            " | ".join(
                [
                    profile.profile_id,
                    profile.display_name,
                    profile.status,
                    str(profile.starting_corpus_inr),
                    profile.currency,
                ]
            )
        )


def main() -> int:
    configure_logging()
    parser = build_parser()
    args = parser.parse_args()
    return run_profile_command(args)


if __name__ == "__main__":
    raise SystemExit(main())
