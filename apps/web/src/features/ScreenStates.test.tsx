import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { createTaurusQueryClient } from "../app/providers";
import { routes } from "../app/routes";

const safety = {
  taurus_mode: "paper",
  broker_provider: "paper",
  live_trading_enabled: false,
  llm_provider: "lmstudio",
  llm_model_version: "lmstudio:local-model",
  llm_failure_count: 0,
  alert_provider: "mock",
};

const profile = {
  profile_id: "local-paper",
  display_name: "Local Paper",
  starting_corpus_inr: "10000.0000",
  currency: "INR",
  status: "ACTIVE",
  description: "",
  profile_metadata: {},
  created_at: "2026-06-10T00:00:00Z",
  updated_at: "2026-06-10T00:00:00Z",
};

const technicalV2 = {
  profile_name: "technical_ohlcv_v2",
  alpha_score: "0.4200",
  risk_score: "0.1800",
  tradability_score: "0.2400",
  confidence: "0.7600",
  composite_score: "0.3120",
  coverage: "0.9200",
  score_source: "technical_ohlcv_v2",
  top_contributors: [
    {
      feature_name: "return_63d",
      label: "63d return",
      family: "alpha",
      direction: "positive",
      score: "0.6400",
      contribution: "0.1200",
    },
  ],
  missing_features: ["turnover_z_score_20"],
  metadata: {
    universe_context_available: true,
    symbol_context_available: true,
    universe_size: 3,
  },
};

const runSummary = {
  run_id: "pr-test",
  profile_id: "local-paper",
  status: "COMPLETED",
  schedule_name: "daily_after_close",
  started_at: "2026-05-21T15:00:00Z",
  completed_at: "2026-05-21T15:01:00Z",
  duration_seconds: 60,
  timezone: "Asia/Kolkata",
  run_after_market_close: true,
  symbols: ["INFY"],
  succeeded_symbols: ["INFY"],
  failed_symbols: [],
  error_count: 0,
  market_provider: "kite",
  universe_count: 3,
  analyzed_count: 3,
  ranked_count: 3,
  proposal_count: 3,
  selected_count: 1,
  not_selected_count: 1,
  allocation_rejected_count: 1,
  risk_rejected_count: 0,
  executed_count: 1,
  selection_preview: [
    {
      symbol: "INFY",
      proposal_id: "tp-1",
      final_decision_id: "fd-1",
      decision_id: "dec-test",
      order_id: "po-1",
      rank: 1,
      strategy_score: 0.92,
      candidate_score: 91.5,
      trader_action: "BUY",
      proposal_confidence: 0.9,
      allocation_status: "selected",
      final_status: "APPROVED_FOR_PAPER",
      final_action: "BUY",
      execution_status: "FILLED",
      selected: true,
      binding_constraint: null,
      technical_v2: technicalV2,
      reason: "executed_by_paper_order:filled",
    },
    {
      symbol: "TCS",
      proposal_id: "tp-2",
      final_decision_id: "fd-2",
      decision_id: "dec-tcs",
      order_id: null,
      rank: 2,
      strategy_score: 0.8,
      candidate_score: 84.0,
      trader_action: "BUY",
      proposal_confidence: 0.76,
      allocation_status: "not_selected",
      final_status: "NO_ACTION",
      final_action: "NO_TRADE",
      execution_status: "skipped",
      selected: false,
      binding_constraint: "open_positions",
      reason: "not_selected_by_run_allocation:open_positions",
    },
    {
      symbol: "RELIANCE",
      proposal_id: "tp-3",
      final_decision_id: "fd-3",
      decision_id: "dec-reliance",
      order_id: null,
      rank: 3,
      strategy_score: 0.7,
      candidate_score: 77.0,
      trader_action: "BUY",
      proposal_confidence: 0.64,
      allocation_status: "allocation_rejected",
      final_status: "NO_ACTION",
      final_action: "NO_TRADE",
      execution_status: "skipped",
      selected: false,
      binding_constraint: "strategy_unmapped",
      reason: "allocation_rejected_by_run_allocation:strategy_unmapped",
    },
  ],
  final_status_counts: { APPROVED_FOR_PAPER: 1 },
  order_status_counts: { FILLED: 1 },
  settlement_summary: {
    settled: 1,
    rejected: 0,
    still_pending: 0,
    skipped: 0,
    detail_count: 1,
    status_counts: { FILLED: 1 },
    still_pending_order_count: 0,
    pending_next_open_order_symbols: [],
    has_activity: true,
  },
};

const monitorStatus = {
  enabled: false,
  provider: "kite",
  market_hours_only: true,
  interval_seconds: 30,
  max_iterations: 0,
  latest_event_type: null,
  latest_note: null,
  last_iteration_time: null,
  trigger_count_today: 0,
};

const allocationDecision = {
  symbol: "INFY",
  action: "BUY",
  strategy_name: "graph_aware_score_v1",
  sleeve_id: "active_strategy",
  sleeve_name: "Active Strategy",
  status: "approved",
  requested_position_pct_nav: 3,
  approved_position_pct_nav: 2,
  requested_notional_inr: 30000,
  approved_notional_inr: 20000,
  approved_quantity: 10,
  allowed_risk_inr: 5000,
  estimated_risk_inr: 1200,
  governor_scale_factor: 1,
  governor_reasons: [],
  binding_constraint: "cash_buffer",
  technical_v2: technicalV2,
};

const portfolioPlan = {
  available: true,
  plan_id: "plan-m61",
  run_id: "pr-test",
  portfolio_id: "local-paper",
  policy_version: "m61_rebalance_policy",
  model_version: "portfolio_rebalance_plan_v3",
  current_nav_inr: 1000000,
  current_cash_inr: 970000,
  hard_cash_reserve_pct_nav: 5,
  hard_cash_reserve_inr: 50000,
  spendable_cash_after_reserve_inr: 920000,
  same_run_sell_proceeds_net_inr: 120000,
  same_run_sell_proceeds_spendable_inr: 96000,
  same_run_sell_proceeds_safety_reserve_inr: 24000,
  same_run_sell_proceeds_haircut_pct: 80,
  buy_price_buffer_pct: 5,
  cash_budget: [
    {
      row_id: "hard_cash_reserve",
      label: "Hard cash reserve",
      amount_inr: 50000,
      spendable: false,
      description: "Protected 5% NAV cash buffer.",
    },
    {
      row_id: "spendable_same_run_proceeds",
      label: "Spendable same-run proceeds",
      amount_inr: 96000,
      spendable: true,
      description: "80% of same-run sell proceeds can fund BUY orders.",
    },
  ],
  sleeve_budgets: [
    {
      sleeve_id: "active_strategy",
      sleeve_name: "Active Strategy",
      target_pct_nav: 35,
      current_pct_nav: 4,
      idle_capacity_inr: 120000,
      protected_capacity_inr: 0,
      borrowable_capacity_inr: 0,
      borrowed_capacity_inr: 60000,
      borrowed_by_sleeve_id: null,
      projected_pct_nav: 15,
    },
    {
      sleeve_id: "core_shariah",
      sleeve_name: "Core Shariah",
      target_pct_nav: 40,
      current_pct_nav: 16,
      idle_capacity_inr: 180000,
      protected_capacity_inr: 0,
      borrowable_capacity_inr: 80000,
      borrowed_capacity_inr: 0,
      borrowed_by_sleeve_id: "active_strategy",
      projected_pct_nav: 22,
    },
    {
      sleeve_id: "cash_buffer",
      sleeve_name: "Cash Buffer",
      target_pct_nav: 5,
      current_pct_nav: 97,
      idle_capacity_inr: 0,
      protected_capacity_inr: 50000,
      borrowable_capacity_inr: 0,
      borrowed_capacity_inr: 0,
      borrowed_by_sleeve_id: null,
      projected_pct_nav: 5,
    },
  ],
  candidates: [
    {
      candidate_id: "candidate-infy",
      symbol: "INFY",
      action: "BUY",
      source: "trader_proposal",
      sleeve_id: "active_strategy",
      strategy_rank: 1,
      raw_strategy_score: "0.1800",
      allocation_score_component: 91.5,
      target_position_pct_nav: 20,
      decision_status: "eligible",
      rejection_reasons: [],
    },
    {
      candidate_id: "candidate-lt",
      symbol: "LT",
      action: "BUY",
      source: "core_shariah_basket_v1",
      sleeve_id: "core_shariah",
      strategy_rank: 4,
      raw_strategy_score: "0.0350",
      allocation_score_component: 75,
      target_position_pct_nav: 10,
      decision_status: "eligible",
      rejection_reasons: [],
    },
    {
      candidate_id: "candidate-tcs",
      symbol: "TCS",
      action: "EXIT",
      source: "threshold_exit",
      sleeve_id: "active_strategy",
      strategy_rank: 5,
      raw_strategy_score: "-0.2500",
      allocation_score_component: 0,
      target_position_pct_nav: 0,
      decision_status: "threshold_exit",
      rejection_reasons: ["strategy_score_below_exit_threshold"],
    },
  ],
  planned_trades: [
    {
      trade_id: "trade-exit-tcs",
      symbol: "TCS",
      side: "SELL",
      action: "EXIT",
      source: "threshold_exit",
      rank: 1,
      target_pct_nav: 0,
      delta_pct_nav: -12,
      estimated_notional_inr: 120000,
      estimated_quantity: 60,
      status: "planned",
    },
    {
      trade_id: "trade-core-lt",
      symbol: "LT",
      side: "BUY",
      action: "BUY",
      source: "core_shariah_basket_v1",
      rank: 4,
      target_pct_nav: 10,
      delta_pct_nav: 10,
      estimated_notional_inr: 100000,
      estimated_quantity: 20,
      status: "planned",
    },
  ],
};

const allocation = {
  enabled: true,
  config_path: "configs/portfolio/money_management_v1.yaml",
  policy_version: "ui_test_policy",
  summary_metrics: [
    { label: "Sleeves", value: 2, tone: "neutral" },
    { label: "Cash buffer", value: 97, unit: "%", tone: "success" },
    { label: "Undeployed capacity", value: 920000, unit: "INR", tone: "neutral" },
    { label: "Open risk used", value: 24, unit: "%", tone: "neutral" },
  ],
  sleeves: [
    {
      sleeve_id: "active_strategy",
      sleeve_name: "Active Strategy",
      role: "Research strategy sleeve",
      target_weight_pct: 20,
      target_notional_inr: 200000,
      current_weight_pct: 1.51,
      current_exposure_inr: 15100,
      drift_pct_nav: -18.49,
      drift_notional_inr: -184900,
      open_position_count: 1,
      symbols: ["INFY"],
      open_trade_risk_inr: 1200,
    },
  ],
  cash: {
    target_cash_pct_nav: 5,
    target_cash_inr: 50000,
    available_cash_inr: 970000,
    current_cash_pct_nav: 97,
    cash_surplus_inr: 920000,
    undeployed_capacity_inr: 920000,
  },
  open_risk: {
    used_risk_inr: 1200,
    limit_risk_inr: 5000,
    limit_pct_nav: 0.5,
    remaining_risk_inr: 3800,
    used_pct_limit: 24,
  },
  latest_decisions: [
    {
      ...allocationDecision,
      run_id: "pr-test",
      proposal_id: "tp-1",
      as_of: "2026-05-21T15:00:20Z",
      rank: 1,
      allocation_status: "selected",
      reason: "executed_by_paper_order:filled",
    },
  ],
  drawdown_governors: {
    portfolio_drawdown_pct: 0,
    portfolio_governor_reasons: [],
    policy_thresholds: [{ name: "caution", drawdown_pct: 3, action: "reduce_new_position_sizes_25_pct" }],
    sleeve_statuses: [
      {
        sleeve_id: "active_strategy",
        sleeve_name: "Active Strategy",
        drawdown_pct: 0,
        new_entry_scale_factor: 1,
        new_entries_frozen: false,
      },
    ],
    latest_decision_governor_reasons: [],
  },
  portfolio_plan: portfolioPlan,
  core_basket: {
    available: true,
    run_id: "pr-test",
    strategy_name: "core_shariah_basket_v1",
    sleeve_id: "core_shariah",
    selected_symbols: ["INFY"],
    drift: {
      sleeve_target_pct_nav: 40,
      sleeve_current_pct_nav: 1.51,
      sleeve_drift_pct_nav: 38.49,
      sleeve_drift_notional_inr: 384900,
    },
    rebalance: {
      should_rebalance: true,
      rationale: ["monthly_core_rebalance_due"],
    },
    composition: [
      {
        symbol: "INFY",
        target_weight_pct_nav: 5,
        current_weight_pct_nav: 1.51,
        drift_pct_nav: -3.49,
        target_notional_inr: 50000,
      },
    ],
    rejected_candidates: [{ symbol: "TCS", reasons: ["insufficient_daily_candle_history"] }],
  },
};

const emptyOverview = {
  active_profile: profile,
  available_profiles: [profile],
  safety,
  monitor_status: monitorStatus,
  allocation: { enabled: false, config_path: "configs/portfolio/money_management_v1.yaml" },
  latest_account: null,
  latest_run: null,
  latest_final_decision: null,
  latest_order: null,
  recent_runs: [],
  positions: [],
  warnings: [],
};

const overview = {
  active_profile: profile,
  available_profiles: [profile],
  safety,
  monitor_status: { ...monitorStatus, enabled: true, trigger_count_today: 1 },
  allocation,
  latest_account: {
    account_id: "acct-1",
    run_id: "pr-test",
    equity_inr: 1000000,
    available_cash_inr: 970000,
    gross_exposure_inr: 30000,
  },
  latest_run: runSummary,
  latest_final_decision: {
    final_decision_id: "fd-1",
    decision_id: "dec-test",
    run_id: "pr-test",
    symbol: "INFY",
    status: "APPROVED_FOR_PAPER",
    final_action: "BUY",
    approved_quantity: 10,
    reason: "Approved for paper execution.",
  },
  latest_order: {
    order_id: "po-1",
    run_id: "pr-test",
    symbol: "INFY",
    status: "FILLED",
    side: "BUY",
    quantity: 10,
    filled_quantity: 10,
    average_fill_price_inr: 1500,
    total_cost_inr: 12,
    slippage_bps: 3,
  },
  recent_runs: [runSummary],
  positions: [
    {
      run_id: "pr-test",
      symbol: "INFY",
      quantity: 10,
      average_cost_inr: 1500,
      last_price_inr: 1510,
      market_value_inr: 15100,
      unrealized_pnl_inr: 100,
      sleeve_id: "active_strategy",
      sleeve_name: "Active Strategy",
      strategy_name: "graph_aware_score_v1",
    },
  ],
  warnings: [],
};

const stages = [
  {
    id: "inputs",
    label: "Inputs",
    status: "complete",
    timestamp: "2026-05-21T15:00:00Z",
    summary: "Market provider kite; 252 candles; 1 event.",
    metrics: {
      market_provider: "kite",
      candle_count: 252,
      event_count: 1,
      technical_v2_profile: "technical_ohlcv_v2",
      technical_v2_composite_score: "0.3120",
    },
    artifact_ids: ["pr-test"],
    artifacts: [{ run_id: "pr-test", provider: "kite", technical_v2: technicalV2 }],
    raw: { provider: "kite", technical_v2: technicalV2 },
  },
  {
    id: "analyst_reports",
    label: "Analyst Reports",
    status: "complete",
    summary: "1 analyst report.",
    metrics: { report_count: 1 },
    artifact_ids: ["ar-1"],
    artifacts: [
      {
        report_id: "ar-1",
        agent_name: "TechnicalAnalystAgent",
        stance: "bullish",
        score: 0.7,
        confidence: 0.8,
        score_metadata: { technical_v2: technicalV2 },
        key_points: ["Trend improved"],
      },
    ],
    raw: [],
  },
  {
    id: "debate_report",
    label: "Debate",
    status: "missing",
    summary: "No debate report is stored for this run and symbol.",
    metrics: {},
    artifact_ids: [],
    artifacts: [],
    raw: [],
  },
  {
    id: "trader_proposal",
    label: "Trader Proposal",
    status: "complete",
    summary: "BUY proposal.",
    metrics: { action: "BUY", confidence: 0.7, requested_position_pct_nav: 0.03 },
    artifact_ids: ["tp-1"],
    artifacts: [{ proposal_id: "tp-1", action: "BUY", requested_position_pct_nav: 0.03, allocation_decision: allocationDecision }],
    raw: [],
  },
  {
    id: "risk_review",
    label: "Risk Review",
    status: "complete",
    summary: "Risk approved with reduction.",
    metrics: { status: "APPROVED_WITH_REDUCTION", requested_position_pct_nav: 0.03, approved_position_pct_nav: 0.02 },
    artifact_ids: ["risk-1"],
    artifacts: [
      {
        risk_check_id: "risk-1",
        status: "APPROVED_WITH_REDUCTION",
        hard_rule_results: [{ rule: "position_cap", status: "APPROVED", message: "Within cap" }],
        persona_reviews: [{ persona: "SafeRiskAgent", stance: "cautious", summary: "Reduce size" }],
      },
    ],
    raw: [],
  },
  {
    id: "final_decision",
    label: "Final Decision",
    status: "complete",
    summary: "Final decision approved.",
    metrics: { status: "APPROVED_FOR_PAPER", final_action: "BUY", approved_quantity: 10 },
    artifact_ids: ["fd-1"],
    artifacts: [overview.latest_final_decision],
    raw: [],
  },
  {
    id: "paper_order",
    label: "Paper Order",
    status: "complete",
    summary: "Paper order FILLED.",
    metrics: { order_count: 1, status: "FILLED", filled_quantity: 10 },
    artifact_ids: ["po-1"],
    artifacts: [overview.latest_order],
    raw: [],
  },
  {
    id: "paper_fills",
    label: "Paper Fills",
    status: "complete",
    summary: "1 fill stored.",
    metrics: { fill_count: 1, filled_quantity: 10 },
    artifact_ids: ["fill-1"],
    artifacts: [
      {
        fill_id: "fill-1",
        order_id: "po-1",
        symbol: "INFY",
        fill_sequence: 1,
        quantity: 10,
        reference_price_inr: 1498,
        fill_price_inr: 1500,
        cost_inr: 12,
        slippage_bps: 3,
        filled_at: "2026-05-21T15:01:00Z",
      },
    ],
    raw: [],
  },
  {
    id: "audit_log",
    label: "Audit Log",
    status: "complete",
    summary: "1 audit event.",
    metrics: { event_count: 1 },
    artifact_ids: ["1"],
    artifacts: [{ id: 1, event_type: "paper_order.filled", actor: "PaperBroker", note: "Filled" }],
    raw: [],
  },
];

const runDetail = {
  safety,
  run: runSummary,
  symbols: [
    {
      symbol: "INFY",
      run_id: "pr-test",
      pipeline_status: "complete",
      final_status: "APPROVED_FOR_PAPER",
      final_action: "BUY",
      order_status: "FILLED",
      decision_id: "dec-test",
      analyst_roster: {
        enabled: ["technical", "news"],
        skipped: ["sentiment", "fundamentals"],
        report_count: 2,
        min_required: 1,
        status: "enough_reports",
      },
      stages: stages.map(({ artifacts, metrics, raw, ...stage }) => ({
        ...stage,
        artifact_ids: stage.artifact_ids,
      })),
      errors: [],
    },
  ],
  market_data_summary: { provider_name: "kite", candle_count: 252 },
  strategy_summary: {
    strategy_name: "graph_aware_score_v2",
    signal_count: 1,
    technical_v2_by_symbol: { INFY: technicalV2 },
  },
  selection_ledger: runSummary.selection_preview,
  errors: [],
  artifacts: {},
  warnings: [],
};

const trail = {
  run: runSummary,
  symbol: "INFY",
  company_name: "Infosys",
  decision_id: "dec-test",
  final_status: "APPROVED_FOR_PAPER",
  final_action: "BUY",
  can_send_to_broker: true,
  allocation_decision: allocationDecision,
  selection_decision: runSummary.selection_preview[0],
  decision_reason: "executed_by_paper_order:filled",
  analyst_roster: runDetail.symbols[0].analyst_roster,
  selected_stage_id: "inputs",
  stages,
  warnings: [],
};

const replay = {
  decision_id: "dec-test",
  run_id: "pr-test",
  symbol: "INFY",
  status: "APPROVED_FOR_PAPER",
  generated_at: "2026-05-21T15:02:00Z",
  note: "Replay is reconstructed from stored Taurus artifacts.",
  stages: [
    {
      id: "strategy_ranking",
      label: "Strategy Ranking",
      status: "complete",
      summary: "1 strategy ranking artifact.",
      metrics: { artifact_count: 1 },
      artifact_ids: [],
      artifacts: [
        {
          symbol: "INFY",
          strategy_name: "graph_aware_score_v2",
          technical_v2: technicalV2,
          ranking: { symbol: "INFY", rank: 1, metadata: { technical_v2: technicalV2 } },
        },
      ],
      raw: [],
    },
    {
      id: "allocation_ledger",
      label: "Allocation Ledger",
      status: "complete",
      summary: "1 allocation ledger artifact.",
      metrics: { artifact_count: 1 },
      artifact_ids: [],
      artifacts: [
        {
          symbol: "INFY",
          technical_v2: technicalV2,
          ledger_entry: { symbol: "INFY", status: "selected", binding_constraint: "cash_buffer" },
        },
      ],
      raw: [],
    },
  ],
};

const risk = {
  safety,
  money_management: { enabled: true },
  allocation,
  latest_risk_reviews: [
    {
      risk_check_id: "risk-1",
      decision_id: "dec-test",
      run_id: "pr-test",
      symbol: "INFY",
      status: "APPROVED_WITH_REDUCTION",
      requested_position_pct_nav: 0.03,
      approved_position_pct_nav: 0.02,
      can_send_to_broker: true,
      sleeve_id: "active_strategy",
      sleeve_name: "Active Strategy",
      strategy_name: "graph_aware_score_v1",
      binding_constraint: "cash_buffer",
      estimated_risk_inr: 1200,
      as_of: "2026-05-21T15:00:30Z",
    },
    {
      risk_check_id: "risk-2",
      decision_id: "dec-blocked",
      run_id: "pr-blocked",
      symbol: "RELIANCE",
      status: "BLOCKED",
      requested_position_pct_nav: 0.05,
      approved_position_pct_nav: 0,
      can_send_to_broker: false,
      as_of: "2026-05-21T15:00:45Z",
    },
  ],
  hard_rule_results: [{ risk_check_id: "risk-2", symbol: "RELIANCE", rule: "kill_switch", status: "BLOCKED", message: "Kill switch active" }],
  persona_reviews: [{ risk_check_id: "risk-1", symbol: "INFY", persona: "SafeRiskAgent", stance: "cautious", summary: "Reduce size" }],
  latest_final_decisions: [overview.latest_final_decision],
  status_counts: { APPROVED_WITH_REDUCTION: 1, BLOCKED: 1 },
};

const portfolio = {
  safety,
  money_management: { enabled: true },
  allocation,
  monitor_status: monitorStatus,
  latest_account: overview.latest_account,
  positions: overview.positions,
  orders: [overview.latest_order],
  fills: stages.find((stage) => stage.id === "paper_fills")?.artifacts ?? [],
  summary_metrics: [
    { label: "Equity", value: 1000000, unit: "INR", tone: "neutral" },
    { label: "Orders", value: 1, tone: "neutral" },
    { label: "Fills", value: 1, tone: "neutral" },
  ],
};

const history = {
  runs: [runSummary],
  status_counts: { COMPLETED: 1 },
  filters_metadata: {
    statuses: ["COMPLETED"],
    symbols: ["INFY"],
    date_range: { start: "2026-05-21T15:00:00Z", end: "2026-05-21T15:00:00Z" },
  },
};

describe("M16.4 screen states", () => {
  it("renders loading state while overview is pending", () => {
    vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>(() => undefined)));
    renderRoute("/");

    expect(screen.getByText("Loading overview")).toBeInTheDocument();
  });

  it("renders empty overview commands", async () => {
    stubFetch({ overview: emptyOverview });
    renderRoute("/");

    expect(await screen.findByText("No run data")).toBeInTheDocument();
    expect(screen.getByText("make paper-loop-kite")).toBeInTheDocument();
  });

  it("renders API unavailable guidance", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(JSON.stringify({ detail: "service down" }), {
          status: 503,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );
    renderRoute("/");

    expect(await screen.findAllByText("make api")).not.toHaveLength(0);
  });

  it("renders overview run-count and selection summaries", async () => {
    stubFetch({ overview });
    renderRoute("/");

    expect(await screen.findByText("Full-Universe Run Summary")).toBeInTheDocument();
    expect(screen.getByText("Latest Selection Preview")).toBeInTheDocument();
    expect(screen.getByText("1 selected / 1 executed")).toBeInTheDocument();
    expect(screen.getByText("3 analyzed / 3 ranked")).toBeInTheDocument();
    expect(screen.getByText("not_selected_by_run_allocation:open_positions")).toBeInTheDocument();
    expect(screen.getByText("allocation_rejected_by_run_allocation:strategy_unmapped")).toBeInTheDocument();
    expect(screen.getByText("Portfolio Plan")).toBeInTheDocument();
    expect(screen.getByText("m61_rebalance_policy")).toBeInTheDocument();
    expect(screen.getByText("Spendable same-run proceeds")).toBeInTheDocument();
    expect(screen.getAllByText("Borrowed by").length).toBeGreaterThan(0);
    expect(screen.getAllByText("threshold_exit").length).toBeGreaterThan(0);
    expect(screen.getAllByText("core_shariah_basket_v1").length).toBeGreaterThan(0);
    expect(screen.getAllByText("technical_ohlcv_v2").length).toBeGreaterThan(0);
    expect(screen.getAllByText(/63d return/).length).toBeGreaterThan(0);
  });

  it("renders the run-detail selection ledger empty state for legacy runs", async () => {
    stubFetch({ overview, runDetail: { ...runDetail, selection_ledger: [] } });
    renderRoute("/runs/pr-test");

    expect(await screen.findByText("Selection Ledger")).toBeInTheDocument();
    expect(screen.getByText("No run-level selection ledger is available for this run")).toBeInTheDocument();
  });

  it("renders a populated decision trail with missing stages and replay link", async () => {
    stubFetch({ overview, runDetail, trail });
    renderRoute("/runs/pr-test/symbols/INFY");

    expect(await screen.findByText("Open replay")).toBeInTheDocument();
    expect(screen.getByText("Run Selection Decision")).toBeInTheDocument();
    expect(screen.getAllByText("executed_by_paper_order:filled").length).toBeGreaterThan(0);
    expect(screen.getByText("Allocation Decision")).toBeInTheDocument();
    expect(screen.getByText("Selection Technical V2A")).toBeInTheDocument();
    expect(screen.getByText("Allocation Technical V2A")).toBeInTheDocument();
    expect(screen.getAllByText("technical_ohlcv_v2").length).toBeGreaterThan(0);
    expect(screen.getAllByText("turnover_z_score_20").length).toBeGreaterThan(0);
    expect(screen.getAllByText("cash_buffer").length).toBeGreaterThan(0);
    expect(screen.getByText("Analyst Roster")).toBeInTheDocument();
    expect(screen.getByText("technical")).toBeInTheDocument();
    expect(screen.getByText("fundamentals")).toBeInTheDocument();
    expect(screen.getByText("No debate report is stored for this run and symbol.")).toBeInTheDocument();
    expect(screen.getByText("Paper Fills")).toBeInTheDocument();
  });

  it("renders replay technical v2 evidence", async () => {
    stubFetch({ overview, replay });
    renderRoute("/replay/dec-test");

    expect(await screen.findByText("Open Replay")).toBeInTheDocument();
    expect(screen.getByText("Strategy Ranking")).toBeInTheDocument();
    expect(screen.getByText("Allocation Ledger")).toBeInTheDocument();
    expect(screen.getAllByText("technical_ohlcv_v2").length).toBeGreaterThan(0);
    expect(screen.getAllByText(/63d return/).length).toBeGreaterThan(0);
    expect(screen.getAllByText("cash_buffer").length).toBeGreaterThan(0);
  });

  it("highlights blocked and reduced risk reviews", async () => {
    stubFetch({ overview, risk });
    renderRoute("/risk");

    expect(await screen.findByText("Risk And Controls")).toBeInTheDocument();
    expect(await screen.findByText("Sleeve Allocation")).toBeInTheDocument();
    expect(screen.getAllByText("Active Strategy").length).toBeGreaterThan(0);
    expect((await screen.findAllByText("Blocked")).length).toBeGreaterThan(0);
    expect((await screen.findAllByText("Reduced")).length).toBeGreaterThan(0);
  });

  it("shows portfolio account, positions, orders, and fills", async () => {
    stubFetch({ overview, portfolio });
    renderRoute("/portfolio");

    expect(await screen.findByText("Latest Account")).toBeInTheDocument();
    expect(screen.getByText("Core Basket Composition")).toBeInTheDocument();
    expect(screen.getByText("Portfolio Plan")).toBeInTheDocument();
    expect(screen.getByText("Spendable same-run proceeds")).toBeInTheDocument();
    expect(screen.getByText("Core Shariah")).toBeInTheDocument();
    expect(screen.getAllByText("TCS").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Positions").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Orders").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Fills").length).toBeGreaterThan(0);
    expect(screen.getByText("fill-1")).toBeInTheDocument();
  });

  it("filters history by run text", async () => {
    const user = userEvent.setup();
    stubFetch({ overview, history });
    renderRoute("/history");

    expect(await screen.findByText("pr-test")).toBeInTheDocument();
    await user.type(screen.getByPlaceholderText("Search run ID or symbol"), "missing");

    expect(screen.getByText("No runs match the selected filters")).toBeInTheDocument();
  });
});

function renderRoute(path: string) {
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  const queryClient = createTaurusQueryClient();

  render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
}

function stubFetch(payloads: {
  overview?: object;
  runDetail?: object;
  trail?: object;
  replay?: object;
  risk?: object;
  portfolio?: object;
  history?: object;
}) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/profiles")) {
        return new Response(JSON.stringify([profile]), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      const payload =
        url.includes("/ui/runs/pr-test/symbols/INFY/decision-trail")
          ? payloads.trail
          : url.includes("/ui/runs/pr-test")
            ? payloads.runDetail
            : url.includes("/ui/replay/dec-test")
              ? payloads.replay
              : url.includes("/ui/risk")
                ? payloads.risk
                : url.includes("/ui/portfolio")
                  ? payloads.portfolio
                  : url.includes("/ui/history")
                    ? payloads.history
                    : payloads.overview;

      return new Response(JSON.stringify(payload ?? emptyOverview), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }),
  );
}
