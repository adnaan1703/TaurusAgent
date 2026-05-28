from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_DOWN
from typing import Any

from sqlalchemy.orm import Session

from taurus_core.backtesting.context import BacktestConfig, BacktestResult
from taurus_core.backtesting.graph import (
    GraphBacktestSignal,
    GraphBacktestSignalLoader,
    GraphBacktestTrade,
    summarize_graph_performance,
)
from taurus_core.backtesting.metrics import calculate_backtest_metrics
from taurus_core.db.models import (
    AuditLogModel,
    BacktestEquityPointModel,
    BacktestFillModel,
    BacktestOrderModel,
    BacktestPositionModel,
    BacktestRunModel,
    BacktestSignalModel,
    FeatureValueModel,
)
from taurus_core.db.repositories import BacktestRepository, CandleRepository, InstrumentRepository
from taurus_core.domain.market_data import DailyCandle
from taurus_core.features.store import FeatureValue, TechnicalFeatureService
from taurus_core.strategies import StrategyConfig, StrategySignal, build_strategy

MONEY = Decimal("0.0001")
RATE_DENOMINATOR = Decimal("10000")


@dataclass(slots=True)
class PositionState:
    symbol: str
    quantity: int = 0
    average_cost_inr: Decimal = Decimal("0")
    realized_pnl_inr: Decimal = Decimal("0")


@dataclass(frozen=True, slots=True)
class TradePnl:
    symbol: str
    pnl_inr: Decimal


@dataclass(frozen=True, slots=True)
class OpenGraphTrade:
    symbol: str
    entry_date: date
    entry_price_inr: Decimal
    signal: GraphBacktestSignal


class BacktestEngine:
    def __init__(self, session: Session, config: BacktestConfig) -> None:
        self.session = session
        self.config = config

    def run(self) -> BacktestResult:
        candles_by_symbol = self._load_candles()
        if not candles_by_symbol:
            raise ValueError(
                "No daily candles are available. Run make seed-mock or make import-price-csv first."
            )

        symbols = sorted(candles_by_symbol)
        candles_by_date = {
            symbol: {candle.trade_date: candle for candle in candles}
            for symbol, candles in candles_by_symbol.items()
        }
        common_dates = sorted(
            set.intersection(
                *[set(candles_by_date[symbol]) for symbol in symbols]
            )
        )
        if len(common_dates) <= self.config.lookback_days + 1:
            raise ValueError("Not enough candle history for the configured backtest lookback.")

        start_date = common_dates[self.config.lookback_days + 1]
        end_date = common_dates[-1]
        run_id = self._stable_run_id(
            symbols=symbols,
            start_date=start_date,
            end_date=end_date,
        )

        strategy = build_strategy(
            StrategyConfig(
                strategy_name=self.config.strategy_name,
                strategy_type=self.config.strategy_type,
                target_positions=min(self.config.target_positions, self.config.max_open_positions),
                lookback_days=self.config.lookback_days,
                rebalance_every_days=self.config.rebalance_every_days,
                parameters=dict(self.config.strategy_parameters),
                source_path=self.config.strategy_config_path,
            )
        )
        feature_service = TechnicalFeatureService.from_strategy_parameters(
            dict(self.config.strategy_parameters)
        )
        graph_loader = GraphBacktestSignalLoader(self.session) if self._graph_enabled() else None
        cash = self.config.initial_capital_inr
        positions: dict[str, PositionState] = {}
        closed_pnl: list[TradePnl] = []
        open_graph_trades: dict[str, OpenGraphTrade] = {}
        closed_graph_trades: list[GraphBacktestTrade] = []
        graph_signal_count = 0
        equity_values: list[Decimal] = [self.config.initial_capital_inr]
        feature_values: list[FeatureValueModel] = []
        signals: list[BacktestSignalModel] = []
        orders: list[BacktestOrderModel] = []
        fills: list[BacktestFillModel] = []
        equity_points: list[BacktestEquityPointModel] = []

        for date_index, trade_date in enumerate(common_dates):
            if trade_date < start_date:
                continue

            candles_today = {
                symbol: candles_by_date[symbol][trade_date]
                for symbol in symbols
            }

            if self._is_rebalance_day(date_index):
                history_dates = common_dates[:date_index]
                history_by_symbol = {
                    symbol: [candles_by_date[symbol][history_date] for history_date in history_dates]
                    for symbol in symbols
                }
                features_by_symbol = {}
                for symbol, history in history_by_symbol.items():
                    snapshot = feature_service.build_snapshot(
                        symbol=symbol,
                        as_of_date=trade_date,
                        history=history,
                    )
                    if snapshot is None:
                        continue
                    features_by_symbol[symbol] = snapshot
                    feature_values.extend(
                        _feature_model(run_id, feature_value)
                        for feature_value in snapshot.rows
                    )
                current_symbols = {
                    symbol for symbol, position in positions.items() if position.quantity > 0
                }
                graph_signals_by_symbol: dict[str, GraphBacktestSignal] = {}
                if graph_loader is not None:
                    graph_signals_by_symbol = graph_loader.load_by_as_of_date(
                        as_of_date=trade_date,
                        symbols=symbols,
                    )
                    graph_signal_count += len(graph_signals_by_symbol)

                select_with_graph = getattr(strategy, "select_targets_with_graph", None)
                if callable(select_with_graph):
                    targets, generated_signals = select_with_graph(
                        trade_date=trade_date,
                        features_by_symbol=features_by_symbol,
                        current_positions=current_symbols,
                        graph_signals_by_symbol=graph_signals_by_symbol,
                    )
                else:
                    targets, generated_signals = strategy.select_targets(
                        trade_date=trade_date,
                        features_by_symbol=features_by_symbol,
                        current_positions=current_symbols,
                    )
                signals.extend(_signal_model(run_id, signal) for signal in generated_signals)
                cash, new_orders, new_fills, new_closed_pnl = self._rebalance(
                    run_id=run_id,
                    trade_date=trade_date,
                    targets=targets,
                    candles_today=candles_today,
                    cash=cash,
                    positions=positions,
                    equity_before_trades=self._mark_to_market(cash, positions, candles_today),
                )
                orders.extend(new_orders)
                fills.extend(new_fills)
                closed_pnl.extend(new_closed_pnl)
                self._record_graph_trades(
                    fills=new_fills,
                    graph_signals_by_symbol=graph_signals_by_symbol,
                    open_graph_trades=open_graph_trades,
                    closed_graph_trades=closed_graph_trades,
                )

            holdings_value = sum(
                _money(position.quantity * candles_today[symbol].close)
                for symbol, position in positions.items()
                if position.quantity > 0
            )
            total_equity = _money(cash + holdings_value)
            equity_values.append(total_equity)
            peak = max(equity_values)
            drawdown = (total_equity / peak) - Decimal("1") if peak > 0 else Decimal("0")
            equity_points.append(
                BacktestEquityPointModel(
                    run_id=run_id,
                    trade_date=trade_date,
                    cash_inr=_money(cash),
                    holdings_value_inr=holdings_value,
                    total_equity_inr=total_equity,
                    drawdown_pct=drawdown.quantize(Decimal("0.00000001")),
                )
            )

        winning_pnl = [trade.pnl_inr for trade in closed_pnl if trade.pnl_inr > 0]
        losing_pnl = [trade.pnl_inr for trade in closed_pnl if trade.pnl_inr < 0]
        metrics = calculate_backtest_metrics(
            equity_values,
            winning_pnl=winning_pnl,
            losing_pnl=losing_pnl,
        )
        if graph_loader is not None:
            metrics.update(summarize_graph_performance(closed_graph_trades))
            metrics["graph_signal_count"] = graph_signal_count
            metrics["graph_open_trade_count"] = len(open_graph_trades)
        final_equity = equity_points[-1].total_equity_inr
        final_candles = {
            symbol: candles_by_date[symbol][end_date]
            for symbol in symbols
        }
        position_models = self._position_models(run_id, positions, final_candles)
        run = BacktestRunModel(
            run_id=run_id,
            strategy_name=self.config.strategy_name,
            seed=self.config.seed,
            start_date=start_date,
            end_date=end_date,
            initial_capital_inr=self.config.initial_capital_inr,
            final_equity_inr=final_equity,
            metrics=metrics,
            parameters=self._parameters(),
        )
        audit_rows = [
            AuditLogModel(
                event_type="backtest.run_started",
                actor="backtest_engine",
                payload={"run_id": run_id, "strategy": self.config.strategy_name},
                note="Backtest run started.",
            ),
            AuditLogModel(
                event_type="backtest.run_completed",
                actor="backtest_engine",
                payload={
                    "run_id": run_id,
                    "feature_values": len(feature_values),
                    "signals": len(signals),
                    "orders": len(orders),
                    "fills": len(fills),
                    "positions": len(position_models),
                    "equity_points": len(equity_points),
                    "graph_signals_loaded": graph_signal_count,
                    "graph_trades_closed": len(closed_graph_trades),
                },
                note="Backtest run completed.",
            ),
        ]

        BacktestRepository(self.session).replace_run(
            run=run,
            feature_values=feature_values,
            signals=signals,
            orders=orders,
            fills_by_order_index=fills,
            positions=position_models,
            equity_points=equity_points,
            audit_rows=audit_rows,
        )
        self.session.commit()

        return BacktestResult(
            run_id=run_id,
            start_date=start_date,
            end_date=end_date,
            metrics=metrics,
            feature_value_count=len(feature_values),
            signal_count=len(signals),
            order_count=len(orders),
            fill_count=len(fills),
            position_count=len(position_models),
            equity_point_count=len(equity_points),
            audit_row_count=len(audit_rows),
        )

    def _graph_enabled(self) -> bool:
        return self.config.graph_enabled

    def _record_graph_trades(
        self,
        *,
        fills: list[BacktestFillModel],
        graph_signals_by_symbol: dict[str, GraphBacktestSignal],
        open_graph_trades: dict[str, OpenGraphTrade],
        closed_graph_trades: list[GraphBacktestTrade],
    ) -> None:
        for fill in fills:
            if fill.side == "SELL":
                open_trade = open_graph_trades.pop(fill.symbol, None)
                if open_trade is None or open_trade.entry_price_inr <= 0:
                    continue
                closed_graph_trades.append(
                    GraphBacktestTrade(
                        symbol=fill.symbol,
                        entry_date=open_trade.entry_date,
                        exit_date=fill.trade_date,
                        return_pct=(
                            (fill.fill_price_inr / open_trade.entry_price_inr) - Decimal("1")
                        ).quantize(Decimal("0.00000001")),
                        signal_score=open_trade.signal.score,
                        signal_confidence=open_trade.signal.confidence,
                        edge_types=open_trade.signal.edge_types,
                        edge_keys=open_trade.signal.edge_keys,
                    )
                )
                continue

            if fill.side != "BUY":
                continue
            graph_signal = graph_signals_by_symbol.get(fill.symbol)
            if graph_signal is None or not graph_signal.contributions:
                continue
            open_graph_trades[fill.symbol] = OpenGraphTrade(
                symbol=fill.symbol,
                entry_date=fill.trade_date,
                entry_price_inr=fill.fill_price_inr,
                signal=graph_signal,
            )

    def _load_candles(self) -> dict[str, list[DailyCandle]]:
        instruments = InstrumentRepository(self.session).list(active_only=True)
        candle_repo = CandleRepository(self.session)
        candles_by_symbol: dict[str, list[DailyCandle]] = {}
        for instrument in instruments:
            candle_models = candle_repo.get_by_symbol_and_date_range(
                symbol=instrument.symbol,
                timeframe=self.config.timeframe,
            )
            if candle_models:
                candles_by_symbol[instrument.symbol] = [
                    DailyCandle(
                        symbol=candle.symbol,
                        trade_date=candle.trade_date,
                        open=candle.open,
                        high=candle.high,
                        low=candle.low,
                        close=candle.close,
                        volume=candle.volume,
                        timeframe=candle.timeframe,
                        source=candle.source,
                        data_available_time=candle.data_available_time,
                    )
                    for candle in candle_models
                ]
        return candles_by_symbol

    def _rebalance(
        self,
        *,
        run_id: str,
        trade_date: date,
        targets: set[str],
        candles_today: dict[str, DailyCandle],
        cash: Decimal,
        positions: dict[str, PositionState],
        equity_before_trades: Decimal,
    ) -> tuple[Decimal, list[BacktestOrderModel], list[BacktestFillModel], list[TradePnl]]:
        orders: list[BacktestOrderModel] = []
        fills: list[BacktestFillModel] = []
        closed_pnl: list[TradePnl] = []

        for symbol in sorted(list(positions)):
            position = positions[symbol]
            if position.quantity <= 0 or symbol in targets:
                continue
            cash, order, fill, trade_pnl = self._sell(
                run_id=run_id,
                trade_date=trade_date,
                candle=candles_today[symbol],
                quantity=position.quantity,
                cash=cash,
                position=position,
            )
            orders.append(order)
            fills.append(fill)
            closed_pnl.append(trade_pnl)

        held_symbols = {
            symbol for symbol, position in positions.items() if position.quantity > 0
        }
        missing_targets = sorted(targets - held_symbols)
        if not missing_targets:
            return cash, orders, fills, closed_pnl

        allocation = equity_before_trades / Decimal(max(len(targets), 1))
        for symbol in missing_targets:
            if len({s for s, p in positions.items() if p.quantity > 0}) >= self.config.max_open_positions:
                break
            cash, order, fill = self._buy(
                run_id=run_id,
                trade_date=trade_date,
                candle=candles_today[symbol],
                allocation=allocation,
                cash=cash,
                positions=positions,
            )
            if order is not None and fill is not None:
                orders.append(order)
                fills.append(fill)

        return cash, orders, fills, closed_pnl

    def _buy(
        self,
        *,
        run_id: str,
        trade_date: date,
        candle: DailyCandle,
        allocation: Decimal,
        cash: Decimal,
        positions: dict[str, PositionState],
    ) -> tuple[Decimal, BacktestOrderModel | None, BacktestFillModel | None]:
        fill_price = _money(candle.open * (Decimal("1") + self.config.slippage_bps / RATE_DENOMINATOR))
        quantity = int((min(allocation, cash) / fill_price).to_integral_value(rounding=ROUND_DOWN))
        while quantity > 0:
            gross_value = _money(fill_price * quantity)
            cost = _money(gross_value * self.config.cost_bps / RATE_DENOMINATOR)
            if gross_value + cost <= cash:
                break
            quantity -= 1
        if quantity <= 0:
            return cash, None, None

        gross_value = _money(fill_price * quantity)
        cost = _money(gross_value * self.config.cost_bps / RATE_DENOMINATOR)
        cash = _money(cash - gross_value - cost)
        position = positions.setdefault(candle.symbol, PositionState(symbol=candle.symbol))
        total_cost = _money((position.average_cost_inr * position.quantity) + gross_value + cost)
        position.quantity += quantity
        position.average_cost_inr = _money(total_cost / Decimal(position.quantity))
        return cash, _order_model(run_id, trade_date, candle.symbol, "BUY", quantity), _fill_model(
            run_id,
            trade_date,
            candle.symbol,
            "BUY",
            quantity,
            fill_price,
            gross_value,
            cost,
            self.config.slippage_bps,
        )

    def _sell(
        self,
        *,
        run_id: str,
        trade_date: date,
        candle: DailyCandle,
        quantity: int,
        cash: Decimal,
        position: PositionState,
    ) -> tuple[Decimal, BacktestOrderModel, BacktestFillModel, TradePnl]:
        fill_price = _money(candle.open * (Decimal("1") - self.config.slippage_bps / RATE_DENOMINATOR))
        gross_value = _money(fill_price * quantity)
        cost = _money(gross_value * self.config.cost_bps / RATE_DENOMINATOR)
        cash = _money(cash + gross_value - cost)
        pnl = _money(gross_value - cost - (position.average_cost_inr * quantity))
        position.quantity = 0
        position.realized_pnl_inr = _money(position.realized_pnl_inr + pnl)
        return cash, _order_model(run_id, trade_date, candle.symbol, "SELL", quantity), _fill_model(
            run_id,
            trade_date,
            candle.symbol,
            "SELL",
            quantity,
            fill_price,
            gross_value,
            cost,
            self.config.slippage_bps,
        ), TradePnl(symbol=candle.symbol, pnl_inr=pnl)

    def _mark_to_market(
        self,
        cash: Decimal,
        positions: dict[str, PositionState],
        candles_today: dict[str, DailyCandle],
    ) -> Decimal:
        return _money(
            cash
            + sum(
                position.quantity * candles_today[symbol].close
                for symbol, position in positions.items()
                if position.quantity > 0
            )
        )

    def _position_models(
        self,
        run_id: str,
        positions: dict[str, PositionState],
        final_candles: dict[str, DailyCandle],
    ) -> list[BacktestPositionModel]:
        models: list[BacktestPositionModel] = []
        for symbol in sorted(positions):
            position = positions[symbol]
            last_close = final_candles[symbol].close
            market_value = _money(position.quantity * last_close)
            unrealized = _money(market_value - (position.average_cost_inr * position.quantity))
            models.append(
                BacktestPositionModel(
                    run_id=run_id,
                    symbol=symbol,
                    quantity=position.quantity,
                    average_cost_inr=position.average_cost_inr,
                    market_value_inr=market_value,
                    realized_pnl_inr=position.realized_pnl_inr,
                    unrealized_pnl_inr=unrealized,
                )
            )
        return models

    def _is_rebalance_day(self, date_index: int) -> bool:
        first_trade_index = self.config.lookback_days + 1
        return (date_index - first_trade_index) % self.config.rebalance_every_days == 0

    def _stable_run_id(
        self,
        *,
        symbols: list[str],
        start_date: date,
        end_date: date,
    ) -> str:
        payload = {
            "strategy_name": self.config.strategy_name,
            "seed": self.config.seed,
            "symbols": symbols,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "parameters": self._parameters(),
        }
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
        return f"bt-{digest[:16]}"

    def _parameters(self) -> dict[str, object]:
        return {
            "initial_capital_inr": str(self.config.initial_capital_inr),
            "max_open_positions": self.config.max_open_positions,
            "target_positions": self.config.target_positions,
            "lookback_days": self.config.lookback_days,
            "rebalance_every_days": self.config.rebalance_every_days,
            "cost_bps": str(self.config.cost_bps),
            "slippage_bps": str(self.config.slippage_bps),
            "timeframe": self.config.timeframe,
            "graph_enabled": self.config.graph_enabled,
            "strategy_type": self.config.strategy_type,
            "strategy_config_path": self.config.strategy_config_path,
            "strategy_parameters": _json_safe(dict(self.config.strategy_parameters)),
        }


def _signal_model(run_id: str, signal: StrategySignal) -> BacktestSignalModel:
    return BacktestSignalModel(
        run_id=run_id,
        trade_date=signal.trade_date,
        symbol=signal.symbol,
        action=signal.action,
        score=signal.score.quantize(Decimal("0.00000001")),
        reason=signal.reason,
        feature_snapshot_id=signal.explanation.feature_snapshot_id,
        explanation=signal.explanation.to_dict(),
    )


def _feature_model(run_id: str, feature: FeatureValue) -> FeatureValueModel:
    return FeatureValueModel(
        run_id=run_id,
        snapshot_id=feature.snapshot_id,
        symbol=feature.symbol,
        feature_name=feature.feature_name,
        feature_value=feature.feature_value.quantize(Decimal("0.00000001")),
        feature_time=feature.feature_time,
        data_available_time=feature.data_available_time,
        source=feature.source,
        feature_version=feature.feature_version,
    )


def _order_model(
    run_id: str,
    trade_date: date,
    symbol: str,
    side: str,
    quantity: int,
) -> BacktestOrderModel:
    return BacktestOrderModel(
        run_id=run_id,
        trade_date=trade_date,
        symbol=symbol,
        side=side,
        quantity=quantity,
    )


def _fill_model(
    run_id: str,
    trade_date: date,
    symbol: str,
    side: str,
    quantity: int,
    fill_price: Decimal,
    gross_value: Decimal,
    cost: Decimal,
    slippage_bps: Decimal,
) -> BacktestFillModel:
    return BacktestFillModel(
        order_id=0,
        run_id=run_id,
        trade_date=trade_date,
        symbol=symbol,
        side=side,
        quantity=quantity,
        fill_price_inr=fill_price,
        gross_value_inr=gross_value,
        cost_inr=cost,
        slippage_bps=slippage_bps,
    )


def _money(value: Decimal | int) -> Decimal:
    return Decimal(value).quantize(MONEY)


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    return value
