from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP

from sqlalchemy.orm import Session

from taurus_core.alerts.service import AlertService
from taurus_core.alerts.templates import order_rejection_event, paper_fill_event
from taurus_core.brokers.base import BrokerAdapter
from taurus_core.config import Settings, get_settings
from taurus_core.db.repositories import CandleRepository, ExecutionRepository
from taurus_core.execution.costs import IndiaPaperCostModel
from taurus_core.execution.schemas import (
    ExecutionPolicy,
    NextOpenSettlementOrderDetail,
    NextOpenSettlementSummary,
    OrderSide,
    PaperAccount,
    PaperFill,
    PaperOrder,
    PaperPosition,
    paper_account_id,
    paper_fill_id,
    paper_order_id,
)
from taurus_core.execution.slippage import FixedBpsSlippageModel
from taurus_core.logging import get_logger
from taurus_core.observability.tracing import bound_trace_context
from taurus_core.profiles.runtime import resolve_runtime_profile
from taurus_core.risk.schemas import FinalDecision

MONEY_QUANT = Decimal("0.0001")
SCORE_ZERO = Decimal("0.0000")


@dataclass(slots=True)
class _PositionState:
    symbol: str
    quantity: int = 0
    average_cost_inr: Decimal = SCORE_ZERO
    realized_pnl_inr: Decimal = SCORE_ZERO
    last_price_inr: Decimal = SCORE_ZERO


@dataclass(slots=True)
class _AccountState:
    run_id: str
    portfolio_id: str
    starting_cash_inr: Decimal
    available_cash_inr: Decimal
    realized_pnl_inr: Decimal = SCORE_ZERO


class PaperBroker(BrokerAdapter):
    model_version = "paper_broker_v1"

    def __init__(self, session: Session, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.cost_model = IndiaPaperCostModel(
            brokerage_bps=self.settings.taurus_paper_brokerage_bps,
            exchange_txn_charge_bps=self.settings.taurus_paper_exchange_txn_charge_bps,
            tax_levy_bps=self.settings.taurus_paper_tax_levy_bps,
        )
        self.slippage_model = FixedBpsSlippageModel(
            slippage_bps=self.settings.taurus_paper_slippage_bps,
        )

    def place_order(
        self,
        decision: FinalDecision,
        *,
        execution_policy: ExecutionPolicy = "immediate",
    ) -> PaperOrder:
        if execution_policy not in {"immediate", "next_open"}:
            raise ValueError("PaperBroker execution_policy must be immediate or next_open.")
        self._validate_decision(decision)
        runtime_profile = resolve_runtime_profile(
            self.session,
            self.settings,
            profile_id=decision.portfolio_id,
        )
        timestamp = _as_utc(decision.as_of)
        repo = ExecutionRepository(self.session)
        repo.delete_execution_for_final_decision(decision.final_decision_id)
        self.session.flush()

        account_state, positions = self._rebuild_state_from_fills(
            run_id=decision.run_id,
            portfolio_id=runtime_profile.profile_id,
            starting_cash_inr=runtime_profile.starting_corpus_inr,
            updated_at=timestamp,
        )
        side = _side_for_action(decision.final_action)
        candle = self._latest_candle(decision.symbol)
        if candle is None:
            order, account, position_models = self._rejected_order(
                decision=decision,
                side=side,
                quantity=decision.approved_quantity,
                timestamp=timestamp,
                account_state=account_state,
                positions=positions,
                reason=f"No candle data available for {decision.symbol}.",
                execution_policy=execution_policy,
            )
            repo.store_rejected_order(order=order, account=account, positions=position_models)
            self.session.commit()
            self._log_order(order, fill_ids=[])
            self._send_order_alert(order, fill_ids=[])
            return order

        quantity = self._execution_quantity(
            decision=decision,
            account_state=account_state,
            positions=positions,
            reference_price=candle.close,
        )
        if quantity <= 0:
            order, account, position_models = self._rejected_order(
                decision=decision,
                side=side,
                quantity=decision.approved_quantity,
                timestamp=timestamp,
                account_state=account_state,
                positions=positions,
                reason="No existing paper position or positive executable quantity for action.",
                execution_policy=execution_policy,
                signal_trade_date=candle.trade_date if execution_policy == "next_open" else None,
            )
            repo.store_rejected_order(order=order, account=account, positions=position_models)
            self.session.commit()
            self._log_order(order, fill_ids=[])
            self._send_order_alert(order, fill_ids=[])
            return order

        if execution_policy == "next_open":
            affordable_quantity = self._pending_next_open_quantity(
                decision=decision,
                side=side,
                quantity=quantity,
                timestamp=timestamp,
                reference_price=candle.close,
                trade_date=candle.trade_date,
                account_state=account_state,
                positions=positions,
            )
            if affordable_quantity <= 0:
                order, account, position_models = self._rejected_order(
                    decision=decision,
                    side=side,
                    quantity=quantity,
                    timestamp=timestamp,
                    account_state=account_state,
                    positions=positions,
                    reason="Insufficient paper cash or position for approved order.",
                    execution_policy=execution_policy,
                    signal_trade_date=candle.trade_date,
                )
                repo.store_rejected_order(order=order, account=account, positions=position_models)
                self.session.commit()
                self._log_order(order, fill_ids=[])
                self._send_order_alert(order, fill_ids=[])
                return order

            self._mark_prices(positions=positions, symbol=decision.symbol, last_price=candle.close)
            account, position_models = self._account_and_positions(
                account_state=account_state,
                positions=positions,
                updated_at=timestamp,
            )
            order = self._pending_next_open_order(
                decision=decision,
                side=side,
                quantity=affordable_quantity,
                timestamp=timestamp,
                signal_trade_date=candle.trade_date,
            )
            repo.store_pending_next_open_order(
                order=order,
                account=account,
                positions=position_models,
            )
            self.session.commit()
            self._log_order(order, fill_ids=[])
            self._send_order_alert(order, fill_ids=[])
            return order

        fills = self._build_fills(
            decision=decision,
            side=side,
            quantity=quantity,
            order_id=paper_order_id(
                final_decision_id=decision.final_decision_id,
                decision_id=decision.decision_id,
                quantity=quantity,
            ),
            timestamp=timestamp,
            open_price=candle.open,
            close_price=candle.close,
            trade_date=candle.trade_date,
        )
        if not fills:
            order, account, position_models = self._rejected_order(
                decision=decision,
                side=side,
                quantity=quantity,
                timestamp=timestamp,
                account_state=account_state,
                positions=positions,
                reason="Approved quantity could not produce a valid fill.",
                execution_policy=execution_policy,
            )
            repo.store_rejected_order(order=order, account=account, positions=position_models)
            self.session.commit()
            self._log_order(order, fill_ids=[])
            self._send_order_alert(order, fill_ids=[])
            return order

        affordable_quantity = self._affordable_quantity(
            side=side,
            requested_quantity=quantity,
            fills=fills,
            available_cash=account_state.available_cash_inr,
            positions=positions,
            symbol=decision.symbol,
        )
        if affordable_quantity <= 0:
            order, account, position_models = self._rejected_order(
                decision=decision,
                side=side,
                quantity=quantity,
                timestamp=timestamp,
                account_state=account_state,
                positions=positions,
                reason="Insufficient paper cash or position for approved order.",
                execution_policy=execution_policy,
            )
            repo.store_rejected_order(order=order, account=account, positions=position_models)
            self.session.commit()
            self._log_order(order, fill_ids=[])
            self._send_order_alert(order, fill_ids=[])
            return order
        if affordable_quantity != quantity:
            fills = self._build_fills(
                decision=decision,
                side=side,
                quantity=affordable_quantity,
                order_id=paper_order_id(
                    final_decision_id=decision.final_decision_id,
                    decision_id=decision.decision_id,
                    quantity=affordable_quantity,
                ),
                timestamp=timestamp,
                open_price=candle.open,
                close_price=candle.close,
                trade_date=candle.trade_date,
            )

        for fill in fills:
            self._apply_fill(account_state=account_state, positions=positions, fill=fill)
        self._mark_prices(positions=positions, symbol=decision.symbol, last_price=candle.close)
        account, position_models = self._account_and_positions(
            account_state=account_state,
            positions=positions,
            updated_at=timestamp,
        )
        order = self._filled_order(
            decision=decision,
            side=side,
            requested_quantity=quantity,
            fills=fills,
            timestamp=timestamp,
        )
        repo.replace_order_execution(
            order=order,
            fills=fills,
            account=account,
            positions=position_models,
        )
        self.session.commit()
        self._log_order(order, fill_ids=[fill.fill_id for fill in fills])
        self._send_order_alert(order, fill_ids=[fill.fill_id for fill in fills])
        return order

    def cancel_order(self, order_id: str) -> PaperOrder:
        model = ExecutionRepository(self.session).get_order(order_id)
        if model is None:
            raise ValueError(f"Paper order {order_id} not found.")
        order = PaperOrder.model_validate(model.payload)
        if order.status in {"FILLED", "REJECTED", "CANCELLED"}:
            return order
        cancelled = order.model_copy(
            update={
                "status": "CANCELLED",
                "remaining_quantity": order.quantity - order.filled_quantity,
                "status_history": [*order.status_history, "CANCELLED"],
                "updated_at": order.updated_at,
            }
        )
        model.status = cancelled.status
        model.remaining_quantity = cancelled.remaining_quantity
        model.payload = cancelled.model_dump(mode="json")
        self.session.commit()
        return cancelled

    def get_order(self, order_id: str) -> PaperOrder | None:
        model = ExecutionRepository(self.session).get_order(order_id)
        return PaperOrder.model_validate(model.payload) if model is not None else None

    def list_orders(
        self,
        *,
        symbol: str | None = None,
        limit: int | None = 100,
    ) -> list[PaperOrder]:
        rows = ExecutionRepository(self.session).list_orders(
            portfolio_id=self.settings.taurus_paper_portfolio_id,
            symbol=symbol,
            limit=limit,
        )
        return [PaperOrder.model_validate(row.payload) for row in rows]

    def positions(self, *, symbol: str | None = None) -> list[PaperPosition]:
        rows = ExecutionRepository(self.session).latest_open_positions_by_portfolio(
            portfolio_id=self.settings.taurus_paper_portfolio_id,
        )
        if symbol is not None:
            rows = [row for row in rows if row.symbol == symbol.upper()]
        return [PaperPosition.model_validate(row.payload) for row in rows]

    def cash(self, *, run_id: str | None = None) -> PaperAccount | None:
        repo = ExecutionRepository(self.session)
        row = (
            repo.latest_account(run_id=run_id)
            if run_id is not None
            else repo.latest_account_by_portfolio(
                portfolio_id=self.settings.taurus_paper_portfolio_id,
            )
        )
        return PaperAccount.model_validate(row.payload) if row is not None else None

    def settle_pending_next_open_orders(
        self,
        *,
        portfolio_id: str,
        run_id: str,
        settled_at: datetime,
        symbol: str | None = None,
    ) -> NextOpenSettlementSummary:
        timestamp = _as_utc(settled_at)
        if portfolio_id != self.settings.effective_profile_id:
            raise ValueError(
                "Settlement profile does not match selected paper profile: "
                f"portfolio_id={portfolio_id} selected={self.settings.effective_profile_id}."
            )
        runtime_profile = resolve_runtime_profile(
            self.session,
            self.settings,
            profile_id=portfolio_id,
        )
        repo = ExecutionRepository(self.session)
        pending_rows = repo.list_pending_next_open_orders(
            portfolio_id=runtime_profile.profile_id,
            symbol=symbol,
            limit=None,
        )
        account_state, positions = self._rebuild_state_from_fills(
            run_id=run_id,
            portfolio_id=runtime_profile.profile_id,
            starting_cash_inr=runtime_profile.starting_corpus_inr,
            updated_at=timestamp,
        )

        settled = 0
        rejected = 0
        still_pending = 0
        skipped = 0
        terminal_sequence = 0
        details: list[NextOpenSettlementOrderDetail] = []
        alert_orders: list[tuple[PaperOrder, list[str]]] = []

        for row in pending_rows:
            pending_order = PaperOrder.model_validate(row.payload)
            if pending_order.signal_trade_date is None:
                skipped += 1
                details.append(
                    self._settlement_detail(
                        order=pending_order,
                        quantity=0,
                        status=pending_order.status,
                        outcome_reason="missing_signal_trade_date",
                    )
                )
                continue

            execution_candle = self._first_candle_after_signal(
                symbol=pending_order.symbol,
                signal_trade_date=pending_order.signal_trade_date,
            )
            if execution_candle is None:
                still_pending += 1
                details.append(
                    self._settlement_detail(
                        order=pending_order,
                        quantity=0,
                        status=pending_order.status,
                        outcome_reason="waiting_for_next_candle",
                    )
                )
                continue

            requested_quantity = pending_order.remaining_quantity
            if requested_quantity <= 0:
                requested_quantity = max(
                    0,
                    pending_order.quantity - pending_order.filled_quantity,
                )
            reference_price = _money(execution_candle.open)
            if requested_quantity <= 0:
                terminal_sequence += 1
                rejected_order = self._terminal_pending_order(
                    order=pending_order,
                    status="REJECTED",
                    updated_at=timestamp + timedelta(seconds=terminal_sequence),
                    filled_trade_date=execution_candle.trade_date,
                    rejection_reason="No remaining quantity available for next-open settlement.",
                )
                repo.replace_pending_next_open_order(
                    order_id=pending_order.order_id,
                    order=rejected_order,
                    fills=[],
                )
                rejected += 1
                details.append(
                    self._settlement_detail(
                        order=rejected_order,
                        quantity=0,
                        status=rejected_order.status,
                        execution_trade_date=execution_candle.trade_date,
                        reference_price=reference_price,
                        rejection_reason=rejected_order.rejection_reason,
                    )
                )
                alert_orders.append((rejected_order, []))
                continue

            preview_fill = self._build_next_open_fill(
                order=pending_order,
                run_id=run_id,
                quantity=requested_quantity,
                reference_price=reference_price,
                trade_date=execution_candle.trade_date,
                filled_at=timestamp,
            )
            affordable_quantity = self._affordable_quantity(
                side=pending_order.side,
                requested_quantity=requested_quantity,
                fills=[preview_fill],
                available_cash=account_state.available_cash_inr,
                positions=positions,
                symbol=pending_order.symbol,
            )
            if affordable_quantity <= 0:
                terminal_sequence += 1
                reason = (
                    "Insufficient paper cash for next-open settlement."
                    if pending_order.side == "BUY"
                    else "No paper holdings available for next-open settlement."
                )
                rejected_order = self._terminal_pending_order(
                    order=pending_order,
                    status="REJECTED",
                    updated_at=timestamp + timedelta(seconds=terminal_sequence),
                    filled_trade_date=execution_candle.trade_date,
                    rejection_reason=reason,
                )
                repo.replace_pending_next_open_order(
                    order_id=pending_order.order_id,
                    order=rejected_order,
                    fills=[],
                )
                rejected += 1
                details.append(
                    self._settlement_detail(
                        order=rejected_order,
                        quantity=0,
                        status=rejected_order.status,
                        execution_trade_date=execution_candle.trade_date,
                        reference_price=reference_price,
                        rejection_reason=reason,
                    )
                )
                alert_orders.append((rejected_order, []))
                continue

            terminal_sequence += 1
            fill = self._build_next_open_fill(
                order=pending_order,
                run_id=run_id,
                quantity=affordable_quantity,
                reference_price=reference_price,
                trade_date=execution_candle.trade_date,
                filled_at=timestamp + timedelta(seconds=terminal_sequence),
            )
            self._apply_fill(account_state=account_state, positions=positions, fill=fill)
            status = (
                "FILLED"
                if affordable_quantity == requested_quantity
                else "PARTIALLY_FILLED"
            )
            settled_order = self._terminal_pending_order(
                order=pending_order,
                status=status,
                updated_at=fill.filled_at,
                filled_trade_date=execution_candle.trade_date,
                fill=fill,
            )
            repo.replace_pending_next_open_order(
                order_id=pending_order.order_id,
                order=settled_order,
                fills=[fill],
            )
            settled += 1
            details.append(
                self._settlement_detail(
                    order=settled_order,
                    quantity=fill.quantity,
                    status=settled_order.status,
                    execution_trade_date=execution_candle.trade_date,
                    reference_price=reference_price,
                    fill=fill,
                )
            )
            alert_orders.append((settled_order, [fill.fill_id]))

        self._mark_latest_prices_for_positions(positions)
        account_updated_at = timestamp + timedelta(seconds=terminal_sequence)
        account, position_models = self._account_and_positions(
            account_state=account_state,
            positions=positions,
            updated_at=account_updated_at,
        )
        repo.replace_account_state(
            run_id=run_id,
            portfolio_id=runtime_profile.profile_id,
            account=account,
            positions=position_models,
        )
        self.session.commit()

        for order, fill_ids in alert_orders:
            self._log_order(order, fill_ids=fill_ids)
            self._send_order_alert(order, fill_ids=fill_ids)

        return NextOpenSettlementSummary(
            portfolio_id=runtime_profile.profile_id,
            run_id=run_id,
            settled=settled,
            rejected=rejected,
            still_pending=still_pending,
            skipped=skipped,
            details=details,
        )

    def _validate_decision(self, decision: FinalDecision) -> None:
        if self.settings.live_trading_enabled:
            raise ValueError("PaperBroker cannot run while live trading is enabled.")
        if self.settings.broker_provider != "paper":
            raise ValueError("PaperBroker requires BROKER_PROVIDER=paper.")
        if decision.status != "APPROVED_FOR_PAPER":
            raise ValueError("PaperBroker accepts only approved final paper decisions.")
        if not decision.can_send_to_broker:
            raise ValueError("Final decision is not broker-routable.")
        if decision.approved_quantity <= 0:
            raise ValueError("Final decision approved quantity must be positive.")
        if decision.portfolio_id != self.settings.effective_profile_id:
            raise ValueError(
                "Final decision profile does not match selected paper profile: "
                f"decision={decision.portfolio_id} selected={self.settings.effective_profile_id}."
            )
        _side_for_action(decision.final_action)

    def _log_order(self, order: PaperOrder, *, fill_ids: list[str]) -> None:
        with bound_trace_context(
            run_id=order.run_id,
            decision_id=order.decision_id,
            order_id=order.order_id,
            final_decision_id=order.final_decision_id,
        ):
            get_logger(__name__).info(
                "paper.order.routed",
                symbol=order.symbol,
                status=order.status,
                side=order.side,
                quantity=order.quantity,
                filled_quantity=order.filled_quantity,
                fill_ids=fill_ids,
            )

    def _send_order_alert(self, order: PaperOrder, *, fill_ids: list[str]) -> None:
        try:
            if order.status == "REJECTED":
                event = order_rejection_event(order)
            elif order.filled_quantity > 0:
                event = paper_fill_event(order, fill_ids=fill_ids)
            else:
                return
            AlertService(self.session, self.settings).send(event)
        except Exception as exc:
            get_logger(__name__).warning(
                "alert.paper_order.failed",
                order_id=order.order_id,
                status=order.status,
                error=str(exc),
            )

    def _latest_candle(self, symbol: str):
        candles = CandleRepository(self.session).get_by_symbol_and_date_range(symbol=symbol)
        return candles[-1] if candles else None

    def _first_candle_after_signal(self, *, symbol: str, signal_trade_date):
        candles = CandleRepository(self.session).get_by_symbol_and_date_range(
            symbol=symbol,
            start_date=signal_trade_date + timedelta(days=1),
        )
        return candles[0] if candles else None

    def _execution_quantity(
        self,
        *,
        decision: FinalDecision,
        account_state: _AccountState,
        positions: dict[str, _PositionState],
        reference_price: Decimal,
    ) -> int:
        symbol = decision.symbol.upper()
        held = positions.get(symbol, _PositionState(symbol=symbol)).quantity
        if decision.final_action == "BUY":
            return decision.approved_quantity
        if decision.final_action == "EXIT":
            return held
        if decision.final_action == "REDUCE":
            if held <= 0 or reference_price <= 0:
                return 0
            target_notional = (
                (account_state.available_cash_inr + self._gross_exposure(positions))
                * decision.approved_position_pct_nav
                / Decimal("100")
            )
            target_quantity = int(target_notional // reference_price)
            return max(0, min(held, held - target_quantity))
        return 0

    def _gross_exposure(self, positions: dict[str, _PositionState]) -> Decimal:
        return sum(
            (
                _money(position.last_price_inr * Decimal(position.quantity))
                for position in positions.values()
                if position.quantity > 0
            ),
            SCORE_ZERO,
        )

    def _build_fills(
        self,
        *,
        decision: FinalDecision,
        side: OrderSide,
        quantity: int,
        order_id: str,
        timestamp: datetime,
        open_price: Decimal,
        close_price: Decimal,
        trade_date,
    ) -> list[PaperFill]:
        fills: list[PaperFill] = []
        for sequence, fill_quantity in enumerate(self._fill_plan(quantity), start=1):
            reference_price = open_price if sequence == 1 else close_price
            fill_price = self.slippage_model.fill_price(
                reference_price_inr=reference_price,
                side=side,
            )
            gross_value = _money(fill_price * Decimal(fill_quantity))
            costs = self.cost_model.calculate(gross_value)
            slippage_value = self.slippage_model.slippage_value(
                reference_price_inr=reference_price,
                fill_price_inr=fill_price,
                quantity=fill_quantity,
            )
            fills.append(
                PaperFill(
                    fill_id=paper_fill_id(
                        order_id=order_id,
                        fill_sequence=sequence,
                        quantity=fill_quantity,
                        reference_price=reference_price,
                    ),
                    order_id=order_id,
                    final_decision_id=decision.final_decision_id,
                    run_id=decision.run_id,
                    portfolio_id=self.settings.taurus_paper_portfolio_id,
                    symbol=decision.symbol,
                    trade_date=trade_date,
                    side=side,
                    quantity=fill_quantity,
                    reference_price_inr=_money(reference_price),
                    fill_price_inr=fill_price,
                    gross_value_inr=gross_value,
                    brokerage_inr=costs.brokerage_inr,
                    exchange_txn_charge_inr=costs.exchange_txn_charge_inr,
                    tax_levy_inr=costs.tax_levy_inr,
                    cost_inr=costs.total_inr,
                    slippage_bps=self.settings.taurus_paper_slippage_bps,
                    slippage_inr=slippage_value,
                    fill_sequence=sequence,
                    filled_at=timestamp + timedelta(seconds=sequence),
                    model_version=self.model_version,
                )
            )
        return fills

    def _build_next_open_fill(
        self,
        *,
        order: PaperOrder,
        run_id: str,
        quantity: int,
        reference_price: Decimal,
        trade_date,
        filled_at: datetime,
    ) -> PaperFill:
        fill_price = self.slippage_model.fill_price(
            reference_price_inr=reference_price,
            side=order.side,
        )
        gross_value = _money(fill_price * Decimal(quantity))
        costs = self.cost_model.calculate(gross_value)
        slippage_value = self.slippage_model.slippage_value(
            reference_price_inr=reference_price,
            fill_price_inr=fill_price,
            quantity=quantity,
        )
        return PaperFill(
            fill_id=paper_fill_id(
                order_id=order.order_id,
                fill_sequence=1,
                quantity=quantity,
                reference_price=reference_price,
            ),
            order_id=order.order_id,
            final_decision_id=order.final_decision_id,
            run_id=run_id,
            portfolio_id=order.portfolio_id,
            symbol=order.symbol,
            trade_date=trade_date,
            side=order.side,
            quantity=quantity,
            reference_price_inr=reference_price,
            fill_price_inr=fill_price,
            gross_value_inr=gross_value,
            brokerage_inr=costs.brokerage_inr,
            exchange_txn_charge_inr=costs.exchange_txn_charge_inr,
            tax_levy_inr=costs.tax_levy_inr,
            cost_inr=costs.total_inr,
            slippage_bps=self.settings.taurus_paper_slippage_bps,
            slippage_inr=slippage_value,
            fill_sequence=1,
            filled_at=filled_at,
            model_version=self.model_version,
        )

    def _fill_plan(self, quantity: int) -> list[int]:
        if quantity <= 0:
            return []
        threshold = self.settings.taurus_paper_partial_fill_threshold
        if quantity <= threshold:
            return [quantity]
        first = int(
            (Decimal(quantity) * self.settings.taurus_paper_first_fill_pct).to_integral_value(
                rounding=ROUND_DOWN,
            )
        )
        first = max(1, min(first, quantity - 1))
        return [first, quantity - first]

    def _affordable_quantity(
        self,
        *,
        side: OrderSide,
        requested_quantity: int,
        fills: list[PaperFill],
        available_cash: Decimal,
        positions: dict[str, _PositionState],
        symbol: str,
    ) -> int:
        if side == "SELL":
            held = positions.get(symbol.upper(), _PositionState(symbol=symbol.upper())).quantity
            return min(requested_quantity, held)
        total_debit = sum((fill.gross_value_inr + fill.cost_inr for fill in fills), SCORE_ZERO)
        if total_debit <= available_cash:
            return requested_quantity

        affordable = requested_quantity
        while affordable > 0:
            scaled = Decimal(affordable) / Decimal(requested_quantity)
            debit = sum(
                (
                    _money(fill.gross_value_inr * scaled)
                    + _money(fill.cost_inr * scaled)
                    for fill in fills
                ),
                SCORE_ZERO,
            )
            if debit <= available_cash:
                return affordable
            affordable -= 1
        return 0

    def _pending_next_open_quantity(
        self,
        *,
        decision: FinalDecision,
        side: OrderSide,
        quantity: int,
        timestamp: datetime,
        reference_price: Decimal,
        trade_date,
        account_state: _AccountState,
        positions: dict[str, _PositionState],
    ) -> int:
        preview_order_id = paper_order_id(
            final_decision_id=decision.final_decision_id,
            decision_id=decision.decision_id,
            quantity=quantity,
        )
        preview_fills = self._build_fills(
            decision=decision,
            side=side,
            quantity=quantity,
            order_id=preview_order_id,
            timestamp=timestamp,
            open_price=reference_price,
            close_price=reference_price,
            trade_date=trade_date,
        )
        if not preview_fills:
            return 0
        return self._affordable_quantity(
            side=side,
            requested_quantity=quantity,
            fills=preview_fills,
            available_cash=account_state.available_cash_inr,
            positions=positions,
            symbol=decision.symbol,
        )

    def _apply_fill(
        self,
        *,
        account_state: _AccountState,
        positions: dict[str, _PositionState],
        fill: PaperFill,
    ) -> None:
        position = positions.setdefault(fill.symbol, _PositionState(symbol=fill.symbol))
        position.last_price_inr = fill.fill_price_inr
        if fill.side == "BUY":
            debit = _money(fill.gross_value_inr + fill.cost_inr)
            account_state.available_cash_inr = _money(account_state.available_cash_inr - debit)
            total_cost_basis = _money(
                (position.average_cost_inr * Decimal(position.quantity))
                + fill.gross_value_inr
                + fill.cost_inr
            )
            position.quantity += fill.quantity
            position.average_cost_inr = _money(total_cost_basis / Decimal(position.quantity))
            return

        sell_quantity = min(fill.quantity, position.quantity)
        if sell_quantity <= 0:
            return
        proceeds = _money(fill.gross_value_inr - fill.cost_inr)
        account_state.available_cash_inr = _money(account_state.available_cash_inr + proceeds)
        realized = _money(
            (fill.fill_price_inr - position.average_cost_inr) * Decimal(sell_quantity)
            - fill.cost_inr
        )
        position.quantity -= sell_quantity
        position.realized_pnl_inr = _money(position.realized_pnl_inr + realized)
        account_state.realized_pnl_inr = _money(account_state.realized_pnl_inr + realized)
        if position.quantity == 0:
            position.average_cost_inr = SCORE_ZERO

    def _rebuild_state_from_fills(
        self,
        *,
        run_id: str,
        portfolio_id: str,
        starting_cash_inr: Decimal | None = None,
        updated_at: datetime,
    ) -> tuple[_AccountState, dict[str, _PositionState]]:
        starting_cash = _money(
            starting_cash_inr
            if starting_cash_inr is not None
            else resolve_runtime_profile(
                self.session,
                self.settings,
                profile_id=portfolio_id,
            ).starting_corpus_inr
        )
        account_state = _AccountState(
            run_id=run_id,
            portfolio_id=portfolio_id,
            starting_cash_inr=starting_cash,
            available_cash_inr=starting_cash,
        )
        positions: dict[str, _PositionState] = {}
        rows = ExecutionRepository(self.session).list_fills_by_portfolio(
            portfolio_id=portfolio_id,
        )
        for row in rows:
            self._apply_fill(
                account_state=account_state,
                positions=positions,
                fill=PaperFill.model_validate(row.payload),
            )
        for symbol in list(positions):
            candle = self._latest_candle(symbol)
            if candle is not None:
                self._mark_prices(positions=positions, symbol=symbol, last_price=candle.close)
        self._account_and_positions(
            account_state=account_state,
            positions=positions,
            updated_at=updated_at,
        )
        return account_state, positions

    def _mark_prices(
        self,
        *,
        positions: dict[str, _PositionState],
        symbol: str,
        last_price: Decimal,
    ) -> None:
        if symbol.upper() in positions:
            positions[symbol.upper()].last_price_inr = _money(last_price)

    def _mark_latest_prices_for_positions(
        self,
        positions: dict[str, _PositionState],
    ) -> None:
        for symbol, position in list(positions.items()):
            if position.quantity <= 0:
                continue
            candle = self._latest_candle(symbol)
            if candle is not None:
                self._mark_prices(positions=positions, symbol=symbol, last_price=candle.close)

    def _filled_order(
        self,
        *,
        decision: FinalDecision,
        side: OrderSide,
        requested_quantity: int,
        fills: list[PaperFill],
        timestamp: datetime,
    ) -> PaperOrder:
        filled_quantity = sum(fill.quantity for fill in fills)
        gross_value = sum((fill.gross_value_inr for fill in fills), SCORE_ZERO)
        total_cost = sum((fill.cost_inr for fill in fills), SCORE_ZERO)
        total_slippage = sum((fill.slippage_inr for fill in fills), SCORE_ZERO)
        average_fill_price = (
            _money(gross_value / Decimal(filled_quantity)) if filled_quantity else SCORE_ZERO
        )
        history = ["CREATED", "ACCEPTED"]
        if len(fills) > 1:
            history.append("PARTIALLY_FILLED")
        status = "FILLED" if filled_quantity == requested_quantity else "PARTIALLY_FILLED"
        history.append(status)
        return PaperOrder(
            order_id=fills[0].order_id,
            final_decision_id=decision.final_decision_id,
            decision_id=decision.decision_id,
            run_id=decision.run_id,
            portfolio_id=self.settings.taurus_paper_portfolio_id,
            symbol=decision.symbol,
            side=side,
            quantity=requested_quantity,
            order_type="MARKET",
            status=status,
            filled_quantity=filled_quantity,
            remaining_quantity=max(0, requested_quantity - filled_quantity),
            average_fill_price_inr=average_fill_price,
            gross_value_inr=_money(gross_value),
            total_cost_inr=_money(total_cost),
            total_slippage_inr=_money(total_slippage),
            slippage_bps=self.settings.taurus_paper_slippage_bps,
            rejection_reason="",
            status_history=history,
            submitted_at=timestamp,
            updated_at=timestamp + timedelta(seconds=len(fills)),
            model_version=self.model_version,
        )

    def _pending_next_open_order(
        self,
        *,
        decision: FinalDecision,
        side: OrderSide,
        quantity: int,
        timestamp: datetime,
        signal_trade_date,
    ) -> PaperOrder:
        return PaperOrder(
            order_id=paper_order_id(
                final_decision_id=decision.final_decision_id,
                decision_id=decision.decision_id,
                quantity=quantity,
            ),
            final_decision_id=decision.final_decision_id,
            decision_id=decision.decision_id,
            run_id=decision.run_id,
            portfolio_id=self.settings.taurus_paper_portfolio_id,
            symbol=decision.symbol,
            side=side,
            quantity=quantity,
            order_type="MARKET",
            status="PENDING_NEXT_OPEN",
            execution_policy="next_open",
            filled_quantity=0,
            remaining_quantity=quantity,
            average_fill_price_inr=SCORE_ZERO,
            gross_value_inr=SCORE_ZERO,
            total_cost_inr=SCORE_ZERO,
            total_slippage_inr=SCORE_ZERO,
            slippage_bps=self.settings.taurus_paper_slippage_bps,
            rejection_reason="",
            status_history=["CREATED", "ACCEPTED", "PENDING_NEXT_OPEN"],
            signal_trade_date=signal_trade_date,
            scheduled_fill_session="next_open",
            filled_trade_date=None,
            submitted_at=timestamp,
            updated_at=timestamp,
            model_version=self.model_version,
        )

    def _terminal_pending_order(
        self,
        *,
        order: PaperOrder,
        status,
        updated_at: datetime,
        filled_trade_date,
        fill: PaperFill | None = None,
        rejection_reason: str = "",
    ) -> PaperOrder:
        filled_quantity = fill.quantity if fill is not None else 0
        gross_value = fill.gross_value_inr if fill is not None else SCORE_ZERO
        total_cost = fill.cost_inr if fill is not None else SCORE_ZERO
        total_slippage = fill.slippage_inr if fill is not None else SCORE_ZERO
        average_fill_price = fill.fill_price_inr if fill is not None else SCORE_ZERO
        history = list(order.status_history)
        if status not in history:
            history.append(status)
        return order.model_copy(
            update={
                "status": status,
                "filled_quantity": filled_quantity,
                "remaining_quantity": max(0, order.quantity - filled_quantity),
                "average_fill_price_inr": average_fill_price,
                "gross_value_inr": gross_value,
                "total_cost_inr": total_cost,
                "total_slippage_inr": total_slippage,
                "rejection_reason": rejection_reason,
                "status_history": history,
                "filled_trade_date": filled_trade_date,
                "updated_at": updated_at,
            }
        )

    def _settlement_detail(
        self,
        *,
        order: PaperOrder,
        quantity: int,
        status,
        execution_trade_date=None,
        reference_price: Decimal | None = None,
        fill: PaperFill | None = None,
        rejection_reason: str = "",
        outcome_reason: str = "",
    ) -> NextOpenSettlementOrderDetail:
        return NextOpenSettlementOrderDetail(
            order_id=order.order_id,
            symbol=order.symbol,
            side=order.side,
            signal_trade_date=order.signal_trade_date,
            execution_trade_date=execution_trade_date,
            reference_price_inr=reference_price,
            fill_price_inr=fill.fill_price_inr if fill is not None else None,
            quantity=quantity,
            status=status,
            rejection_reason=rejection_reason,
            outcome_reason=outcome_reason,
        )

    def _rejected_order(
        self,
        *,
        decision: FinalDecision,
        side: OrderSide,
        quantity: int,
        timestamp: datetime,
        account_state: _AccountState,
        positions: dict[str, _PositionState],
        reason: str,
        execution_policy: ExecutionPolicy = "immediate",
        signal_trade_date=None,
    ) -> tuple[PaperOrder, PaperAccount, list[PaperPosition]]:
        account, position_models = self._account_and_positions(
            account_state=account_state,
            positions=positions,
            updated_at=timestamp,
        )
        order = PaperOrder(
            order_id=paper_order_id(
                final_decision_id=decision.final_decision_id,
                decision_id=decision.decision_id,
                quantity=quantity,
            ),
            final_decision_id=decision.final_decision_id,
            decision_id=decision.decision_id,
            run_id=decision.run_id,
            portfolio_id=self.settings.taurus_paper_portfolio_id,
            symbol=decision.symbol,
            side=side,
            quantity=quantity,
            order_type="MARKET",
            status="REJECTED",
            execution_policy=execution_policy,
            filled_quantity=0,
            remaining_quantity=quantity,
            average_fill_price_inr=SCORE_ZERO,
            gross_value_inr=SCORE_ZERO,
            total_cost_inr=SCORE_ZERO,
            total_slippage_inr=SCORE_ZERO,
            slippage_bps=self.settings.taurus_paper_slippage_bps,
            rejection_reason=reason,
            status_history=["CREATED", "REJECTED"],
            signal_trade_date=signal_trade_date,
            submitted_at=timestamp,
            updated_at=timestamp,
            model_version=self.model_version,
        )
        return order, account, position_models

    def _account_and_positions(
        self,
        *,
        account_state: _AccountState,
        positions: dict[str, _PositionState],
        updated_at: datetime,
    ) -> tuple[PaperAccount, list[PaperPosition]]:
        position_models: list[PaperPosition] = []
        gross_exposure = SCORE_ZERO
        unrealized_pnl = SCORE_ZERO
        realized_pnl = account_state.realized_pnl_inr

        for symbol, position in sorted(positions.items()):
            if position.quantity <= 0:
                continue
            last_price = position.last_price_inr
            market_value = _money(last_price * Decimal(position.quantity))
            unrealized = _money(
                (last_price - position.average_cost_inr) * Decimal(position.quantity)
            )
            gross_exposure = _money(gross_exposure + market_value)
            unrealized_pnl = _money(unrealized_pnl + unrealized)
            position_models.append(
                PaperPosition(
                    run_id=account_state.run_id,
                    portfolio_id=account_state.portfolio_id,
                    symbol=symbol,
                    quantity=position.quantity,
                    average_cost_inr=position.average_cost_inr,
                    last_price_inr=last_price,
                    market_value_inr=market_value,
                    realized_pnl_inr=position.realized_pnl_inr,
                    unrealized_pnl_inr=unrealized,
                    updated_at=updated_at,
                    model_version=self.model_version,
                )
            )

        account = PaperAccount(
            account_id=paper_account_id(
                portfolio_id=account_state.portfolio_id,
                run_id=account_state.run_id,
            ),
            run_id=account_state.run_id,
            portfolio_id=account_state.portfolio_id,
            starting_cash_inr=account_state.starting_cash_inr,
            available_cash_inr=account_state.available_cash_inr,
            reserved_cash_inr=SCORE_ZERO,
            realized_pnl_inr=realized_pnl,
            unrealized_pnl_inr=unrealized_pnl,
            gross_exposure_inr=gross_exposure,
            equity_inr=_money(account_state.available_cash_inr + gross_exposure),
            currency="INR",
            updated_at=updated_at,
            model_version=self.model_version,
        )
        return account, position_models


def _side_for_action(action: str) -> OrderSide:
    if action == "BUY":
        return "BUY"
    if action in {"REDUCE", "EXIT"}:
        return "SELL"
    raise ValueError(f"Final action {action} is not executable by PaperBroker.")


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)
