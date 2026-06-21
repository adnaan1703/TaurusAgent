import type { JsonObject, UiMetric } from "../api/types";
import { DataPanel } from "../components/DataPanel";
import { DataTable } from "../components/DataTable";
import { MetricCard } from "../components/MetricCard";
import { StatusBadge } from "../components/StatusBadge";
import {
  formatId,
  formatInr,
  formatMetric,
  formatNumber,
  formatPercent,
  getPrimitive,
  getString,
  isJsonObject,
  jsonArray,
} from "../utils/format";

type AllocationPanelsProps = {
  allocation: JsonObject | null | undefined;
  showCore?: boolean;
};

export function AllocationPanels({ allocation, showCore = true }: AllocationPanelsProps) {
  const enabled = getPrimitive(allocation, "enabled") === true;
  const metrics = jsonArray(allocation?.summary_metrics);
  const sleeves = jsonArray(allocation?.sleeves);
  const coreBasket = isJsonObject(allocation?.core_basket) ? allocation.core_basket : null;
  const cash = isJsonObject(allocation?.cash) ? allocation.cash : null;
  const openRisk = isJsonObject(allocation?.open_risk) ? allocation.open_risk : null;
  const decisions = jsonArray(allocation?.latest_decisions);
  const governors = isJsonObject(allocation?.drawdown_governors)
    ? allocation.drawdown_governors
    : null;
  const portfolioPlan = isJsonObject(allocation?.portfolio_plan) ? allocation.portfolio_plan : null;

  if (!enabled) {
    return (
      <div className="grid gap-6">
        <DataPanel title="Allocation">
          <p className="text-sm text-taurus-muted">
            Money management is disabled; allocation surfaces will appear after
            TAURUS_MONEY_MANAGEMENT_ENABLED is true.
          </p>
        </DataPanel>
        <PortfolioPlanPanel plan={portfolioPlan} />
      </div>
    );
  }

  return (
    <div className="grid gap-6">
      {metrics.length > 0 && (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          {metrics.map((metric) => (
            <MetricCard
              key={getString(metric, "label")}
              label={getString(metric, "label")}
              tone={metricTone(metric)}
              value={formatMetric(metric as UiMetric)}
            />
          ))}
        </div>
      )}

      <DataPanel
        actions={<StatusBadge label={getString(allocation, "policy_version") || "Policy"} status="complete" size="sm" />}
        title="Sleeve Allocation"
      >
        <DataTable
          columns={[
            { key: "sleeve", header: "Sleeve", render: (row) => getString(row, "sleeve_name") || getString(row, "sleeve_id") || "-" },
            { key: "target", header: "Target", align: "right", render: (row) => formatPercent(getPrimitive(row, "target_weight_pct")) },
            { key: "current", header: "Current", align: "right", render: (row) => formatPercent(getPrimitive(row, "current_weight_pct")) },
            { key: "drift", header: "Drift", align: "right", render: (row) => formatPercent(getPrimitive(row, "drift_pct_nav")) },
            { key: "exposure", header: "Exposure", align: "right", render: (row) => formatInr(getPrimitive(row, "current_exposure_inr")) },
            { key: "risk", header: "Open risk", align: "right", render: (row) => formatInr(getPrimitive(row, "open_trade_risk_inr")) },
            { key: "positions", header: "Positions", align: "right", render: (row) => formatNumber(getPrimitive(row, "open_position_count")) },
          ]}
          emptyLabel="No sleeve allocation rows"
          getRowKey={(row) => getString(row, "sleeve_id")}
          rows={sleeves}
        />
      </DataPanel>

      <div className="grid gap-6 xl:grid-cols-2">
        <CashAndRiskPanel cash={cash} openRisk={openRisk} />
        <DrawdownGovernorPanel governors={governors} />
      </div>

      <PortfolioPlanPanel plan={portfolioPlan} />

      <DataPanel title="Latest Allocation Decisions">
        <DataTable
          columns={[
            { key: "symbol", header: "Symbol", render: (row) => getString(row, "symbol") || "-" },
            { key: "rank", header: "Rank", align: "right", render: (row) => formatNumber(getPrimitive(row, "rank")) },
            { key: "source", header: "Source", render: (row) => getString(row, "proposal_source") || getString(row, "planner_source") || "-" },
            { key: "planner", header: "Planner rank", align: "right", render: (row) => formatNumber(getPrimitive(row, "planner_rank")) },
            { key: "capacity", header: "Capacity", render: (row) => getString(row, "capacity_source") || "-" },
            { key: "funding", header: "Funding", render: (row) => getString(row, "funding_source") || "-" },
            { key: "proceeds", header: "Same-run used", align: "right", render: (row) => formatInr(getPrimitive(row, "same_run_proceeds_used_inr")) },
            { key: "sleeve", header: "Sleeve", render: (row) => getString(row, "sleeve_name") || getString(row, "sleeve_id") || "-" },
            { key: "strategy", header: "Strategy", render: (row) => getString(row, "strategy_name") || "-" },
            { key: "status", header: "Status", render: (row) => <StatusBadge status={getString(row, "status") || getString(row, "allocation_status")} size="sm" /> },
            { key: "requested", header: "Requested", align: "right", render: (row) => formatPercent(getPrimitive(row, "requested_position_pct_nav")) },
            { key: "approved", header: "Approved", align: "right", render: (row) => formatPercent(getPrimitive(row, "approved_position_pct_nav")) },
            { key: "risk", header: "Risk", align: "right", render: (row) => formatInr(getPrimitive(row, "estimated_risk_inr")) },
            { key: "constraint", header: "Binding constraint", render: (row) => getString(row, "binding_constraint") || "None" },
            { key: "reason", header: "Reason", render: (row) => getString(row, "reason") || "-" },
          ]}
          emptyLabel="No allocation decisions have been stored yet"
          getRowKey={(row) => `${getString(row, "proposal_id")}-${getString(row, "symbol")}`}
          rows={decisions}
        />
      </DataPanel>

      {showCore && <CoreBasketPanel coreBasket={coreBasket} />}
    </div>
  );
}

export function PortfolioPlanPanel({ plan }: { plan: JsonObject | null | undefined }) {
  const available = getPrimitive(plan, "available") === true || Boolean(getString(plan, "plan_id"));
  const plannedTrades = jsonArray(plan?.planned_trades).slice(0, 10);
  const candidates = jsonArray(plan?.candidates).slice(0, 10);
  const cashBudget = jsonArray(plan?.cash_budget);
  const sleeveBudgets = jsonArray(plan?.sleeve_budgets);

  if (!available) {
    return (
      <DataPanel
        actions={<StatusBadge label="No artifact" status="missing" size="sm" />}
        title="Portfolio Plan"
      >
        <p className="text-sm text-taurus-muted">No portfolio plan artifact is stored.</p>
      </DataPanel>
    );
  }

  return (
    <DataPanel
      actions={<StatusBadge label={getString(plan, "model_version") || "Dry run"} status="complete" size="sm" />}
      title="Portfolio Plan"
    >
      <div className="grid gap-5">
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-6">
          <MetricCard
            label="NAV"
            supportingText={getString(plan, "policy_version") || "Policy"}
            value={formatInr(getPrimitive(plan, "current_nav_inr"))}
          />
          <MetricCard
            label="Cash"
            supportingText={`After reserve ${formatInr(getPrimitive(plan, "spendable_cash_after_reserve_inr"))}`}
            value={formatInr(getPrimitive(plan, "current_cash_inr"))}
          />
          <MetricCard
            label="Reserve"
            supportingText={formatPercent(getPrimitive(plan, "hard_cash_reserve_pct_nav"))}
            value={formatInr(getPrimitive(plan, "hard_cash_reserve_inr"))}
          />
          <MetricCard
            label="Proceeds"
            supportingText={`Net ${formatInr(getPrimitive(plan, "same_run_sell_proceeds_net_inr"))}`}
            value={formatInr(getPrimitive(plan, "same_run_sell_proceeds_spendable_inr"))}
          />
          <MetricCard
            label="BUY buffer"
            supportingText={`Sell haircut ${formatPercent(getPrimitive(plan, "same_run_sell_proceeds_haircut_pct"))}`}
            value={formatPercent(getPrimitive(plan, "buy_price_buffer_pct"))}
          />
          <MetricCard
            label="Trades"
            supportingText={`${formatNumber(jsonArray(plan?.candidates).length)} candidates`}
            value={formatNumber(plannedTrades.length)}
          />
        </div>

        <DataTable
          columns={[
            { key: "label", header: "Cash row", render: (row) => getString(row, "label") || getString(row, "row_id") || "-" },
            { key: "amount", header: "Amount", align: "right", render: (row) => formatInr(getPrimitive(row, "amount_inr")) },
            { key: "spendable", header: "Spendable", render: (row) => <StatusBadge label={getPrimitive(row, "spendable") ? "Yes" : "No"} status={getPrimitive(row, "spendable") ? "complete" : "skipped"} size="sm" /> },
            { key: "description", header: "Description", render: (row) => getString(row, "description") || "-" },
          ]}
          emptyLabel="No cash budget rows"
          getRowKey={(row) => getString(row, "row_id")}
          rows={cashBudget}
        />

        <DataTable
          columns={[
            { key: "sleeve", header: "Sleeve", render: (row) => getString(row, "sleeve_name") || getString(row, "sleeve_id") || "-" },
            { key: "target", header: "Target", align: "right", render: (row) => formatPercent(getPrimitive(row, "target_pct_nav")) },
            { key: "current", header: "Current", align: "right", render: (row) => formatPercent(getPrimitive(row, "current_pct_nav")) },
            { key: "idle", header: "Idle", align: "right", render: (row) => formatInr(getPrimitive(row, "idle_capacity_inr")) },
            { key: "protected", header: "Protected", align: "right", render: (row) => formatInr(getPrimitive(row, "protected_capacity_inr")) },
            { key: "borrowable", header: "Borrowable", align: "right", render: (row) => formatInr(getPrimitive(row, "borrowable_capacity_inr")) },
            { key: "borrowed", header: "Borrowed", align: "right", render: (row) => formatInr(getPrimitive(row, "borrowed_capacity_inr")) },
            { key: "borrowedBy", header: "Borrowed by", render: (row) => getString(row, "borrowed_by_sleeve_id") || "-" },
            { key: "projected", header: "Projected", align: "right", render: (row) => formatPercent(getPrimitive(row, "projected_pct_nav")) },
          ]}
          emptyLabel="No sleeve budget rows"
          getRowKey={(row) => getString(row, "sleeve_id")}
          rows={sleeveBudgets}
        />

        <DataTable
          columns={[
            { key: "symbol", header: "Symbol", render: (row) => getString(row, "symbol") || "-" },
            { key: "action", header: "Action", render: (row) => <StatusBadge status={getString(row, "action")} size="sm" /> },
            { key: "source", header: "Source", render: (row) => getString(row, "source") || "-" },
            { key: "sleeve", header: "Sleeve", render: (row) => getString(row, "sleeve_id") || "-" },
            { key: "rank", header: "Rank", align: "right", render: (row) => formatNumber(getPrimitive(row, "strategy_rank")) },
            { key: "score", header: "Score", align: "right", render: (row) => formatNumber(getPrimitive(row, "allocation_score_component")) },
            { key: "target", header: "Target", align: "right", render: (row) => formatPercent(getPrimitive(row, "target_position_pct_nav")) },
            { key: "status", header: "Status", render: (row) => getString(row, "decision_status") || "-" },
            {
              key: "reasons",
              header: "Reasons",
              render: (row) =>
                (isJsonObject(row) ? jsonArray(row.rejection_reasons).map(String).join(", ") : "") || "-",
            },
          ]}
          emptyLabel="No candidate rows"
          getRowKey={(row) => getString(row, "candidate_id")}
          rows={candidates}
        />

        <DataTable
          columns={[
            { key: "symbol", header: "Symbol", render: (row) => getString(row, "symbol") || "-" },
            { key: "side", header: "Side", render: (row) => <StatusBadge status={getString(row, "side")} size="sm" /> },
            { key: "source", header: "Source", render: (row) => getString(row, "source") || "-" },
            { key: "rank", header: "Rank", align: "right", render: (row) => formatNumber(getPrimitive(row, "rank")) },
            { key: "target", header: "Target", align: "right", render: (row) => formatPercent(getPrimitive(row, "target_pct_nav")) },
            { key: "delta", header: "Delta", align: "right", render: (row) => formatPercent(getPrimitive(row, "delta_pct_nav")) },
            { key: "notional", header: "Notional", align: "right", render: (row) => formatInr(getPrimitive(row, "estimated_notional_inr")) },
            { key: "quantity", header: "Qty", align: "right", render: (row) => formatNumber(getPrimitive(row, "estimated_quantity")) },
            { key: "status", header: "Status", render: (row) => <StatusBadge status={getString(row, "status")} size="sm" /> },
          ]}
          emptyLabel="No planned trade rows"
          getRowKey={(row) => getString(row, "trade_id")}
          rows={plannedTrades}
        />
      </div>
    </DataPanel>
  );
}

export function AllocationDecisionPanel({
  allocationDecision,
}: {
  allocationDecision: JsonObject | null | undefined;
}) {
  if (!allocationDecision) {
    return (
      <DataPanel title="Allocation Decision">
        <p className="text-sm text-taurus-muted">
          No allocation decision is linked to this symbol trail.
        </p>
      </DataPanel>
    );
  }

  return (
    <DataPanel
      actions={<StatusBadge status={getString(allocationDecision, "status")} size="sm" />}
      title="Allocation Decision"
    >
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          label="Sleeve"
          supportingText={getString(allocationDecision, "strategy_name")}
          value={getString(allocationDecision, "sleeve_name") || getString(allocationDecision, "sleeve_id") || "-"}
        />
        <MetricCard
          label="Approved NAV"
          supportingText={`Requested ${formatPercent(getPrimitive(allocationDecision, "requested_position_pct_nav"))}`}
          value={formatPercent(getPrimitive(allocationDecision, "approved_position_pct_nav"))}
        />
        <MetricCard
          label="Estimated risk"
          supportingText={`Allowed ${formatInr(getPrimitive(allocationDecision, "allowed_risk_inr"))}`}
          value={formatInr(getPrimitive(allocationDecision, "estimated_risk_inr"))}
        />
        <MetricCard
          label="Constraint"
          supportingText={constraintReasons(allocationDecision)}
          value={getString(allocationDecision, "binding_constraint") || "None"}
        />
        <MetricCard
          label="Planner"
          supportingText={getString(allocationDecision, "portfolio_plan_trade_id") || "No plan trade"}
          value={getString(allocationDecision, "planner_source") || getString(allocationDecision, "proposal_source") || "-"}
        />
        <MetricCard
          label="Capacity"
          supportingText={listValue(allocationDecision.borrowed_from_sleeve_ids)}
          value={getString(allocationDecision, "capacity_source") || "-"}
        />
        <MetricCard
          label="Funding"
          supportingText={`Existing ${formatInr(getPrimitive(allocationDecision, "existing_cash_used_inr"))}`}
          value={getString(allocationDecision, "funding_source") || "-"}
        />
        <MetricCard
          label="Same-run proceeds"
          supportingText={`Available ${formatInr(getPrimitive(allocationDecision, "same_run_proceeds_available_inr"))}`}
          value={formatInr(getPrimitive(allocationDecision, "same_run_proceeds_used_inr"))}
        />
      </div>
    </DataPanel>
  );
}

function CashAndRiskPanel({
  cash,
  openRisk,
}: {
  cash: JsonObject | null;
  openRisk: JsonObject | null;
}) {
  return (
    <DataPanel title="Cash And Open Risk">
      <div className="grid gap-4 md:grid-cols-2">
        <MetricCard
          label="Cash buffer"
          supportingText={`Target ${formatPercent(getPrimitive(cash, "target_cash_pct_nav"))}`}
          value={formatInr(getPrimitive(cash, "available_cash_inr"))}
        />
        <MetricCard
          label="Undeployed capacity"
          supportingText={`Surplus ${formatInr(getPrimitive(cash, "cash_surplus_inr"))}`}
          value={formatInr(getPrimitive(cash, "undeployed_capacity_inr"))}
        />
        <MetricCard
          label="Open risk used"
          supportingText={`Limit ${formatInr(getPrimitive(openRisk, "limit_risk_inr"))}`}
          value={formatInr(getPrimitive(openRisk, "used_risk_inr"))}
        />
        <MetricCard
          label="Risk limit usage"
          supportingText={`Remaining ${formatInr(getPrimitive(openRisk, "remaining_risk_inr"))}`}
          value={formatPercent(getPrimitive(openRisk, "used_pct_limit"))}
        />
      </div>
    </DataPanel>
  );
}

function DrawdownGovernorPanel({ governors }: { governors: JsonObject | null }) {
  const sleeveStatuses = jsonArray(governors?.sleeve_statuses);
  const thresholds = jsonArray(governors?.policy_thresholds);
  return (
    <DataPanel title="Drawdown Governors">
      <div className="grid gap-5">
        <div className="grid gap-4 md:grid-cols-2">
          <MetricCard
            label="Portfolio drawdown"
            supportingText={governorReasons(governors)}
            value={formatPercent(getPrimitive(governors, "portfolio_drawdown_pct"))}
          />
          <MetricCard
            label="Governor thresholds"
            supportingText={thresholds.map((row) => `${getString(row, "name")} ${formatPercent(getPrimitive(row, "drawdown_pct"))}`).join(", ") || "None"}
            value={formatNumber(thresholds.length)}
          />
        </div>
        <DataTable
          columns={[
            { key: "sleeve", header: "Sleeve", render: (row) => getString(row, "sleeve_name") || getString(row, "sleeve_id") || "-" },
            { key: "drawdown", header: "Drawdown", align: "right", render: (row) => formatPercent(getPrimitive(row, "drawdown_pct")) },
            { key: "scale", header: "Scale", align: "right", render: (row) => formatPercent(getPrimitive(row, "new_entry_scale_factor")) },
            { key: "frozen", header: "Frozen", render: (row) => <StatusBadge label={getPrimitive(row, "new_entries_frozen") ? "Yes" : "No"} status={getPrimitive(row, "new_entries_frozen") ? "BLOCKED" : "complete"} size="sm" /> },
          ]}
          emptyLabel="No sleeve governor statuses"
          getRowKey={(row) => getString(row, "sleeve_id")}
          rows={sleeveStatuses}
        />
      </div>
    </DataPanel>
  );
}

function CoreBasketPanel({ coreBasket }: { coreBasket: JsonObject | null }) {
  const available = getPrimitive(coreBasket, "available") === true;
  const composition = jsonArray(coreBasket?.composition);
  const rejected = jsonArray(coreBasket?.rejected_candidates);
  const drift = isJsonObject(coreBasket?.drift) ? coreBasket.drift : null;
  const rebalance = isJsonObject(coreBasket?.rebalance) ? coreBasket.rebalance : null;

  return (
    <DataPanel
      actions={<StatusBadge label={available ? "Available" : "No artifact"} status={available ? "complete" : "missing"} size="sm" />}
      title="Core Basket Composition"
    >
      <div className="grid gap-5">
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <MetricCard label="Core current" value={formatPercent(getPrimitive(drift, "sleeve_current_pct_nav"))} />
          <MetricCard label="Core target" value={formatPercent(getPrimitive(drift, "sleeve_target_pct_nav"))} />
          <MetricCard label="Core drift" value={formatPercent(getPrimitive(drift, "sleeve_drift_pct_nav"))} />
          <MetricCard
            label="Rebalance"
            supportingText={String(getPrimitive(rebalance, "rationale") ?? "")}
            value={<StatusBadge label={getPrimitive(rebalance, "should_rebalance") ? "Due" : "Not due"} status={getPrimitive(rebalance, "should_rebalance") ? "APPROVED" : "complete"} />}
          />
        </div>
        <DataTable
          columns={[
            { key: "symbol", header: "Symbol", render: (row) => getString(row, "symbol") || "-" },
            { key: "target", header: "Target", align: "right", render: (row) => formatPercent(getPrimitive(row, "target_weight_pct_nav")) },
            { key: "current", header: "Current", align: "right", render: (row) => formatPercent(getPrimitive(row, "current_weight_pct_nav")) },
            { key: "drift", header: "Drift", align: "right", render: (row) => formatPercent(getPrimitive(row, "drift_pct_nav")) },
            { key: "targetInr", header: "Target INR", align: "right", render: (row) => formatInr(getPrimitive(row, "target_notional_inr")) },
          ]}
          emptyLabel="No core basket composition artifact"
          getRowKey={(row) => getString(row, "symbol")}
          rows={composition}
        />
        <DataTable
          columns={[
            { key: "symbol", header: "Rejected candidate", render: (row) => getString(row, "symbol") || "-" },
            { key: "reasons", header: "Reasons", render: (row) => listValue(row.reasons) },
          ]}
          emptyLabel="No rejected core candidates in the latest artifact"
          getRowKey={(row) => getString(row, "symbol")}
          rows={rejected}
        />
      </div>
    </DataPanel>
  );
}

function metricTone(metric: JsonObject): "neutral" | "success" | "caution" | "failure" {
  const tone = getString(metric, "tone");
  return tone === "success" || tone === "caution" || tone === "failure" ? tone : "neutral";
}

function governorReasons(governors: JsonObject | null): string {
  const reasons = listValue(governors?.portfolio_governor_reasons);
  return reasons === "None" ? "No active governor reasons" : reasons;
}

function constraintReasons(allocationDecision: JsonObject): string {
  const reasons = listValue(allocationDecision.governor_reasons);
  return reasons === "None" ? `Qty ${formatNumber(getPrimitive(allocationDecision, "approved_quantity"))}` : reasons;
}

function listValue(value: unknown): string {
  if (!Array.isArray(value) || value.length === 0) {
    return "None";
  }
  return value.map((item) => String(item)).join(", ");
}
