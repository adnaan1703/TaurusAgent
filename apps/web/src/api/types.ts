export type JsonPrimitive = string | number | boolean | null;
export type JsonValue = JsonPrimitive | JsonObject | JsonValue[];
export type JsonObject = { [key: string]: JsonValue };

export type RunStatus = "RUNNING" | "COMPLETED" | "PARTIAL_FAILED" | "FAILED";
export type StageStatus =
  | "complete"
  | "running"
  | "blocked"
  | "rejected"
  | "failed"
  | "missing"
  | "skipped";
export type WarningSeverity = "info" | "warning" | "critical";
export type MetricTone = "neutral" | "success" | "caution" | "failure";

export type UiSafetyStatus = {
  taurus_mode: string;
  broker_provider: string;
  live_trading_enabled: boolean;
  alert_provider?: string | null;
};

export type UiWarning = {
  id: string;
  severity: WarningSeverity;
  title: string;
  message: string;
  run_id?: string | null;
  symbol?: string | null;
  created_at?: string | null;
};

export type UiMetric = {
  label: string;
  value: string | number | boolean | null;
  unit?: string | null;
  tone: MetricTone;
};

export type UiRunUniverse = {
  source: string;
  provider?: string | null;
  universe_name?: string | null;
  yaml_path?: string | null;
  available_symbol_count?: number | null;
  selected_symbol_count?: number | null;
  symbols: string[];
};

export type UiRunSummary = {
  run_id: string;
  status: RunStatus;
  schedule_name: string;
  started_at: string;
  completed_at?: string | null;
  duration_seconds?: number | null;
  timezone: string;
  run_after_market_close: boolean;
  symbols: string[];
  succeeded_symbols: string[];
  failed_symbols: string[];
  error_count: number;
  market_provider?: string | null;
  universe?: UiRunUniverse | null;
  final_status_counts: Record<string, number>;
  order_status_counts: Record<string, number>;
};

export type UiStageSummary = {
  id: string;
  label: string;
  status: StageStatus;
  summary: string;
  timestamp?: string | null;
  artifact_ids: string[];
};

export type UiAnalystRoster = {
  enabled: string[];
  skipped: string[];
  report_count: number;
  min_required: number;
  status: string;
};

export type UiSymbolPipelineRow = {
  symbol: string;
  run_id: string;
  pipeline_status: StageStatus;
  final_status?: string | null;
  final_action?: string | null;
  order_status?: string | null;
  decision_id?: string | null;
  analyst_roster?: UiAnalystRoster | null;
  stages: UiStageSummary[];
  errors: string[];
};

export type UiTimelineStage = {
  id: string;
  label: string;
  status: StageStatus;
  timestamp?: string | null;
  summary: string;
  metrics: Record<string, JsonPrimitive>;
  artifact_ids: string[];
  artifacts: JsonObject[];
  raw?: JsonObject | JsonObject[] | null;
};

export type UiOverviewResponse = {
  safety: UiSafetyStatus;
  latest_account?: JsonObject | null;
  latest_run?: UiRunSummary | null;
  latest_final_decision?: JsonObject | null;
  latest_order?: JsonObject | null;
  recent_runs: UiRunSummary[];
  positions: JsonObject[];
  warnings: UiWarning[];
};

export type UiRunDetailResponse = {
  safety: UiSafetyStatus;
  run: UiRunSummary;
  symbols: UiSymbolPipelineRow[];
  market_data_summary: JsonObject;
  strategy_summary: JsonObject;
  errors: JsonObject[];
  artifacts: JsonObject;
  warnings: UiWarning[];
};

export type UiDecisionTrailResponse = {
  run: UiRunSummary;
  symbol: string;
  company_name?: string | null;
  decision_id?: string | null;
  final_status?: string | null;
  final_action?: string | null;
  can_send_to_broker?: boolean | null;
  analyst_roster?: UiAnalystRoster | null;
  selected_stage_id: string;
  stages: UiTimelineStage[];
  warnings: UiWarning[];
};

export type UiReplayResponse = {
  decision_id: string;
  run_id: string;
  symbol: string;
  status: string;
  generated_at: string;
  note: string;
  stages: UiTimelineStage[];
};

export type UiRiskResponse = {
  safety: UiSafetyStatus;
  latest_risk_reviews: JsonObject[];
  hard_rule_results: JsonObject[];
  persona_reviews: JsonObject[];
  latest_final_decisions: JsonObject[];
  status_counts: Record<string, number>;
};

export type UiPortfolioResponse = {
  safety: UiSafetyStatus;
  latest_account?: JsonObject | null;
  positions: JsonObject[];
  orders: JsonObject[];
  fills: JsonObject[];
  summary_metrics: UiMetric[];
};

export type UiHistoryResponse = {
  runs: UiRunSummary[];
  status_counts: Record<string, number>;
  filters_metadata: JsonObject;
};

export type ShariahStatusFilter = "all" | "halal" | "haram";

export type UiPagination = {
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
};

export type UiShariahRow = {
  name: string;
  nse_code: string;
  bse_code: string;
  industry: string;
  compliance_status: string;
  active: boolean;
  first_seen_at: string;
  last_seen_at: string;
  status_changed_at: string;
  details_url: string;
  source_url: string;
};

export type UiShariahCounts = {
  active_total: number;
  halal: number;
  haram: number;
};

export type UiHalalStockLatestImport = {
  import_id: string;
  source_url: string;
  source_checksum: string;
  fetched_at: string;
  imported_at: string;
  rows_seen: number;
  rows_imported: number;
  halal_count: number;
  haram_count: number;
  unknown_count: number;
  duplicate_count: number;
  generated_yaml_path: string;
  status: string;
};

export type UiHalalUniverseExport = {
  yaml_path?: string | null;
  universe_name?: string | null;
  exported_symbol_count: number;
  loaded: boolean;
  error?: string | null;
};

export type UiShariahResponse = {
  rows: UiShariahRow[];
  pagination: UiPagination;
  counts: UiShariahCounts;
  latest_import?: UiHalalStockLatestImport | null;
  halal_universe_export: UiHalalUniverseExport;
};
