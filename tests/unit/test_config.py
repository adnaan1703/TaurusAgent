from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from taurus_core.config import DEFAULT_DATABASE_URL, Settings
from taurus_core.portfolio import load_money_management_policy
from taurus_core.strategies.config import load_strategy_config


def test_default_settings_are_safe() -> None:
    settings = Settings()

    assert settings.taurus_env == "local"
    assert settings.taurus_mode == "paper"
    assert settings.live_trading_enabled is False
    assert settings.broker_provider == "paper"
    assert settings.database_url == DEFAULT_DATABASE_URL
    assert settings.taurus_graph_enabled is False
    assert settings.taurus_graph_risk_enabled is False
    assert settings.taurus_graph_auto_promote_edges is False
    assert settings.graph_stats_windows == (60, 120, 252)
    assert settings.taurus_graph_min_edge_sample_size == 30
    assert settings.taurus_graph_min_edge_confidence == Decimal("0.65")
    assert settings.taurus_graph_min_residual_corr == Decimal("0.35")
    assert settings.taurus_graph_min_lead_lag_score == Decimal("0.35")
    assert settings.taurus_graph_min_stability_score == Decimal("0.50")
    assert settings.taurus_graph_lead_lag_max_days == 5
    assert settings.taurus_graph_max_basic_industry_exposure_pct == Decimal("25.0")
    assert settings.taurus_graph_max_product_group_exposure_pct == Decimal("30.0")
    assert settings.taurus_graph_max_customer_industry_exposure_pct == Decimal("30.0")
    assert settings.taurus_graph_max_dependency_exposure_pct == Decimal("30.0")
    assert settings.taurus_graph_max_risk_category_exposure_pct == Decimal("25.0")
    assert settings.taurus_graph_max_correlated_cluster_exposure_pct == Decimal("35.0")
    assert settings.taurus_graph_concentration_warning_fraction == Decimal("0.80")
    assert settings.taurus_neo4j_enabled is False
    assert settings.taurus_neo4j_uri == "bolt://localhost:7687"
    assert settings.taurus_neo4j_user == "neo4j"
    assert settings.taurus_neo4j_password == "taurus-neo4j-local"
    assert settings.taurus_neo4j_database == "neo4j"
    assert settings.taurus_universe == "NIFTY_500_SHARIAH"
    assert settings.taurus_market_data_provider == "kite"
    assert settings.taurus_market_data_universe_path == (
        "configs/market_data/nifty_500_shariah.yaml"
    )
    assert settings.taurus_market_data_lookback_days == 400
    assert settings.taurus_kite_exchange == "NSE"
    assert settings.taurus_llm_provider == "lmstudio"
    assert settings.taurus_llm_base_url == ""
    assert settings.taurus_llm_model == ""
    assert settings.taurus_llm_timeout_seconds == 20
    assert settings.configured_llm_model == "local-model"
    assert settings.configured_llm_model_version == "lmstudio:local-model"
    assert settings.taurus_enabled_analysts == "technical"
    assert settings.enabled_analyst_keys == ("technical",)
    assert settings.taurus_initial_capital_inr == 10_000
    assert settings.taurus_profile_id == "local-paper"
    assert settings.taurus_paper_portfolio_id == "local-paper"
    assert settings.effective_profile_id == "local-paper"
    assert settings.taurus_max_position_pct == 5
    assert settings.taurus_max_open_positions == 8
    assert settings.taurus_money_management_enabled is False
    assert settings.taurus_money_management_config_path == (
        "configs/portfolio/money_management_v1.yaml"
    )
    assert settings.taurus_paper_analysis_scope == "strategy_selected"
    assert settings.taurus_paper_execution_scope == "allocated_only"


def test_profile_id_preferred_alias_sets_legacy_portfolio_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TAURUS_PROFILE_ID", "client-a")

    settings = Settings()

    assert settings.taurus_profile_id == "client-a"
    assert settings.taurus_paper_portfolio_id == "client-a"
    assert settings.effective_profile_id == "client-a"


def test_legacy_paper_portfolio_id_still_sets_effective_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TAURUS_PAPER_PORTFOLIO_ID", "legacy_profile")

    settings = Settings()

    assert settings.taurus_profile_id == "legacy_profile"
    assert settings.taurus_paper_portfolio_id == "legacy_profile"
    assert settings.effective_profile_id == "legacy_profile"


def test_profile_aliases_must_match_when_both_are_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TAURUS_PROFILE_ID", "client-a")
    monkeypatch.setenv("TAURUS_PAPER_PORTFOLIO_ID", "client-b")

    with pytest.raises(ValidationError, match="both set but differ"):
        Settings()


def test_profile_id_must_be_lowercase_slug(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TAURUS_PROFILE_ID", "Client A")

    with pytest.raises(ValidationError, match="profile_id"):
        Settings()


def test_live_trading_cannot_be_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LIVE_TRADING_ENABLED", "true")

    with pytest.raises(ValidationError, match="Live trading is disabled"):
        Settings()


def test_non_paper_broker_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BROKER_PROVIDER", "live")

    with pytest.raises(ValidationError, match="paper broker provider"):
        Settings()


def test_sqlite_database_url_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./taurus.db")

    with pytest.raises(ValidationError, match="SQLite database URLs"):
        Settings()


def test_unknown_market_data_provider_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TAURUS_MARKET_DATA_PROVIDER", "scraper")

    with pytest.raises(ValidationError, match="market data provider"):
        Settings()


@pytest.mark.parametrize("provider", ["mock", "csv", "external"])
def test_runtime_market_data_mocks_and_placeholders_are_rejected(
    monkeypatch: pytest.MonkeyPatch,
    provider: str,
) -> None:
    monkeypatch.setenv("TAURUS_MARKET_DATA_PROVIDER", provider)

    with pytest.raises(ValidationError, match="market data provider"):
        Settings()


def test_mock_llm_provider_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TAURUS_LLM_PROVIDER", "mock")

    with pytest.raises(ValidationError, match="LLM provider"):
        Settings()


def test_gemini_llm_provider_is_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TAURUS_LLM_PROVIDER", "gemini")

    settings = Settings()

    assert settings.taurus_llm_provider == "gemini"
    assert settings.configured_llm_model == "gemini-2.5-flash"
    assert settings.configured_llm_model_version == "gemini:gemini-2.5-flash"


def test_graph_flags_can_be_enabled_explicitly(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TAURUS_GRAPH_ENABLED", "true")
    monkeypatch.setenv("TAURUS_GRAPH_RISK_ENABLED", "true")
    monkeypatch.setenv("TAURUS_GRAPH_AUTO_PROMOTE_EDGES", "true")
    monkeypatch.setenv("TAURUS_NEO4J_ENABLED", "true")

    settings = Settings()

    assert settings.taurus_graph_enabled is True
    assert settings.taurus_graph_risk_enabled is True
    assert settings.taurus_graph_auto_promote_edges is True
    assert settings.taurus_neo4j_enabled is True


def test_graph_analyst_key_can_be_enabled_explicitly(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TAURUS_ENABLED_ANALYSTS", "technical,graph")

    assert Settings().enabled_analyst_keys == ("technical", "graph")


def test_paper_analysis_and_execution_scopes_are_validated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TAURUS_PAPER_ANALYSIS_SCOPE", "full_universe")
    monkeypatch.setenv("TAURUS_PAPER_EXECUTION_SCOPE", "allocated_only")

    settings = Settings()

    assert settings.taurus_paper_analysis_scope == "full_universe"
    assert settings.taurus_paper_execution_scope == "allocated_only"

    monkeypatch.setenv("TAURUS_PAPER_EXECUTION_SCOPE", "selected_only")
    settings = Settings()
    assert settings.taurus_paper_execution_scope == "allocated_only"

    monkeypatch.setenv("TAURUS_PAPER_ANALYSIS_SCOPE", "everything")
    with pytest.raises(ValidationError, match="paper analysis scope"):
        Settings()

    monkeypatch.setenv("TAURUS_PAPER_ANALYSIS_SCOPE", "strategy_selected")
    monkeypatch.setenv("TAURUS_PAPER_EXECUTION_SCOPE", "live")
    with pytest.raises(ValidationError, match="paper execution scope"):
        Settings()


def test_graph_stats_windows_are_validated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TAURUS_GRAPH_STATS_WINDOWS", "20,not-a-window")

    with pytest.raises(ValidationError, match="GRAPH_STATS_WINDOWS"):
        Settings()


def test_unknown_enabled_analyst_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TAURUS_ENABLED_ANALYSTS", "technical,macro")

    with pytest.raises(ValidationError, match="Unsupported analyst key"):
        Settings()


def test_empty_enabled_analyst_roster_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TAURUS_ENABLED_ANALYSTS", "")

    with pytest.raises(ValidationError, match="at least one analyst"):
        Settings()


def test_secret_values_are_redacted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-test")
    monkeypatch.setenv("KITE_API_KEY", "kite-key")
    monkeypatch.setenv("KITE_API_SECRET", "kite-secret")
    monkeypatch.setenv("KITE_ACCESS_TOKEN", "kite-token")
    monkeypatch.setenv("TAURUS_NEO4J_PASSWORD", "neo4j-secret")

    safe = Settings().safe_dict()
    assert safe["openai_api_key"] == "***REDACTED***"
    assert safe["gemini_api_key"] == "***REDACTED***"
    assert safe["kite_api_key"] == "***REDACTED***"
    assert safe["kite_api_secret"] == "***REDACTED***"
    assert safe["kite_access_token"] == "***REDACTED***"
    assert safe["taurus_neo4j_password"] == "***REDACTED***"


def test_database_url_password_is_redacted() -> None:
    settings = Settings(database_url="postgresql+psycopg://taurus:secret@localhost:5432/taurus")

    assert (
        settings.safe_dict()["database_url"]
        == "postgresql+psycopg://taurus:***REDACTED***@localhost:5432/taurus"
    )


def test_money_management_policy_loads_default_config() -> None:
    policy = load_money_management_policy("configs/portfolio/money_management_v1.yaml")

    assert policy.policy_version == "money_management_v1"
    assert policy.cash_buffer_target_pct == Decimal("5.0")
    assert sum(sleeve.target_weight_pct for sleeve in policy.sleeves) == Decimal("100.0")
    metadata = policy.to_metadata()
    assert "cash_buffer_target_pct" not in metadata
    assert "core_symbols" not in metadata
    assert all("core_symbols" not in sleeve for sleeve in metadata["sleeves"])
    assert policy.limits.max_stock_hard_cap_pct_nav >= policy.limits.max_stock_pct_nav
    assert policy.allocation_scoring.weights.strategy_score == Decimal("0.30")
    assert policy.allocation_scoring.score_bands.reject_below == Decimal("60.0")


def test_missing_strategy_target_positions_stays_unset(tmp_path: Path) -> None:
    path = tmp_path / "strategy.yaml"
    path.write_text(
        "strategy_name: ranking_test\n"
        "strategy_type: moving_average_crossover\n"
        "lookback_days: 60\n"
        "rebalance_every_days: 21\n"
        "parameters:\n"
        "  fast_window: 1\n"
        "  slow_window: 2\n",
        encoding="utf-8",
    )

    config = load_strategy_config(path)

    assert config.target_positions is None


@pytest.mark.parametrize(
    ("override", "message"),
    [
        (
            "sleeves:\n"
            "  - sleeve_id: core_shariah\n"
            "    name: Core\n"
            "    target_weight_pct: 90.0\n"
            "    role: Core sleeve\n",
            "sleeve weights must sum to 100",
        ),
        (
            "limits:\n"
            "  max_stock_pct_nav: 8.0\n"
            "  max_stock_hard_cap_pct_nav: 5.0\n"
            "  max_sector_pct_nav: 25.0\n"
            "  max_graph_cluster_pct_nav: 35.0\n"
            "  max_open_positions: 20\n",
            "hard cap must be greater than or equal",
        ),
        (
            "drawdown_governors:\n"
            "  - name: invalid\n"
            "    drawdown_pct: 3.0\n"
            "    action: reduce\n",
            "Input should be",
        ),
    ],
)
def test_money_management_policy_validation_failures(
    tmp_path: Path,
    override: str,
    message: str,
) -> None:
    policy_path = _write_money_management_policy(tmp_path, override=override)

    with pytest.raises(ValueError, match=message):
        load_money_management_policy(policy_path)


def _write_universe(tmp_path: Path, *, symbols: list[str]) -> Path:
    entries = "\n".join(
        f"  - symbol: {symbol}\n"
        f"    name: {symbol} Ltd.\n"
        "    enabled: true\n"
        "    providers:\n"
        "      kite:\n"
        "        exchange: NSE\n"
        f"        tradingsymbol: {symbol}\n"
        for symbol in symbols
    )
    universe_path = tmp_path / "universe.yaml"
    universe_path.write_text(
        "universe_name: test_shariah\n"
        "default_exchange: NSE\n"
        "default_segment: EQUITY\n"
        "symbols:\n"
        f"{entries}",
        encoding="utf-8",
    )
    return universe_path


def _write_money_management_policy(
    tmp_path: Path,
    *,
    universe_path: Path | None = None,
    override: str | None = None,
) -> Path:
    universe_path = universe_path or _write_universe(tmp_path, symbols=["INFY"])
    base = (
        "policy_version: test_policy\n"
        f"shariah_universe_path: {universe_path}\n"
        "sleeves:\n"
        "  - sleeve_id: core_shariah\n"
        "    name: Core\n"
        "    target_weight_pct: 95.0\n"
        "    role: Core sleeve\n"
        "  - sleeve_id: cash_buffer\n"
        "    name: Cash\n"
        "    target_weight_pct: 5.0\n"
        "    role: Cash buffer\n"
        "strategy_mappings:\n"
        "  - strategy_name: core_shariah_basket_v1\n"
        "    sleeve_id: core_shariah\n"
        "limits:\n"
        "  max_stock_pct_nav: 5.0\n"
        "  max_stock_hard_cap_pct_nav: 7.5\n"
        "  max_sector_pct_nav: 25.0\n"
        "  max_graph_cluster_pct_nav: 35.0\n"
        "  max_open_positions: 20\n"
        "trade_risk:\n"
        "  normal_trade_risk_pct_nav: 0.50\n"
        "  strong_trade_risk_pct_nav: 0.75\n"
        "  max_single_trade_risk_pct_nav: 1.00\n"
        "  max_total_open_trade_risk_pct_nav: 5.00\n"
        "allocation_scoring:\n"
        "  weights:\n"
        "    strategy_score: 0.30\n"
        "    trader_confidence: 0.25\n"
        "    liquidity: 0.15\n"
        "    volatility: 0.15\n"
        "    diversification: 0.10\n"
        "    recent_sleeve_performance: 0.05\n"
        "  score_bands:\n"
        "    reject_below: 60.0\n"
        "    half_normal_below: 75.0\n"
        "    normal_below: 85.0\n"
        "drawdown_governors:\n"
        "  - name: caution\n"
        "    drawdown_pct: 3.0\n"
        "    action: reduce_new_position_sizes_25_pct\n"
        "rebalance:\n"
        "  sleeve_drift_threshold_pct: 20.0\n"
        "  min_rebalance_notional_inr: 5000\n"
        "  review_frequency: daily_after_close\n"
        "  core_rebalance_frequency: monthly\n"
    )
    if override is not None:
        key = override.split(":", maxsplit=1)[0]
        lines = base.splitlines()
        filtered = [line for line in lines if not line.startswith(f"{key}:")]
        if key in {"sleeves", "limits", "drawdown_governors", "rebalance"}:
            start = next(index for index, line in enumerate(lines) if line.startswith(f"{key}:"))
            end = next(
                (
                    index
                    for index in range(start + 1, len(lines))
                    if lines[index] and not lines[index].startswith(" ")
                ),
                len(lines),
            )
            filtered = lines[:start] + lines[end:]
        base = "\n".join(filtered) + "\n" + override + "\n"
    policy_path = tmp_path / "money_management.yaml"
    policy_path.write_text(base, encoding="utf-8")
    return policy_path
