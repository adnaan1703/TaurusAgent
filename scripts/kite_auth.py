from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Protocol

from taurus_core.config import Settings, get_settings
from taurus_core.domain.market_data import MarketDataProviderError


class KiteAuthClient(Protocol):
    def login_url(self) -> str:
        ...

    def generate_session(self, request_token: str, api_secret: str) -> dict[str, object]:
        ...


def build_login_url(settings: Settings | None = None, *, client: KiteAuthClient | None = None) -> str:
    settings = settings or get_settings()
    if not settings.kite_api_key:
        raise MarketDataProviderError("KITE_API_KEY is required to build the Kite login URL.")
    client = client or _build_auth_client(settings)
    return client.login_url()


def exchange_request_token(
    request_token: str,
    *,
    settings: Settings | None = None,
    client: KiteAuthClient | None = None,
    env_path: str | Path = ".env",
) -> str:
    settings = settings or get_settings()
    if not settings.kite_api_key or not settings.kite_api_secret:
        raise MarketDataProviderError(
            "KITE_API_KEY and KITE_API_SECRET are required to exchange a Kite request token."
        )
    normalized_token = request_token.strip()
    if not normalized_token:
        raise MarketDataProviderError("Kite request token is empty.")

    client = client or _build_auth_client(settings)
    data = client.generate_session(normalized_token, api_secret=settings.kite_api_secret)
    access_token = data.get("access_token")
    if not isinstance(access_token, str) or not access_token.strip():
        raise MarketDataProviderError("Kite generate_session response did not include access_token.")
    _upsert_env_value(Path(env_path), "KITE_ACCESS_TOKEN", access_token.strip())
    return access_token.strip()


def _build_auth_client(settings: Settings) -> KiteAuthClient:
    try:
        from kiteconnect import KiteConnect
    except ImportError as exc:  # pragma: no cover - dependency is locked in pyproject.
        raise MarketDataProviderError("kiteconnect is not installed. Run `uv sync`.") from exc
    return KiteConnect(api_key=settings.kite_api_key)


def _upsert_env_value(path: Path, key: str, value: str) -> None:
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    replacement = f"{key}={value}"
    for index, line in enumerate(lines):
        if line.startswith(f"{key}="):
            lines[index] = replacement
            break
    else:
        lines.append(replacement)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Kite Connect manual auth helper.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("login-url", help="Print the Kite login URL for the configured API key.")
    exchange = subparsers.add_parser(
        "exchange",
        help="Exchange KITE_REQUEST_TOKEN or --request-token for KITE_ACCESS_TOKEN in .env.",
    )
    exchange.add_argument("--request-token", default=os.environ.get("KITE_REQUEST_TOKEN", ""))
    exchange.add_argument("--env-path", default=".env")
    return parser


if __name__ == "__main__":
    args = _build_parser().parse_args()
    if args.command == "login-url":
        print(build_login_url())
    elif args.command == "exchange":
        token = exchange_request_token(args.request_token, env_path=args.env_path)
        print(f"Stored Kite access token in {args.env_path} ({len(token)} characters).")
