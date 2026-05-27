import type { RouteObject } from "react-router-dom";

import { AppShell } from "../components/AppShell";
import { RouteError } from "../components/RouteError";
import { DecisionTrailPage } from "../features/DecisionTrailPage";
import {
  GraphCompanyPage,
  GraphOverviewPage,
  GraphReviewPage,
  GraphSignalsPage,
} from "../features/GraphPages";
import { HistoryPage } from "../features/HistoryPage";
import { OverviewPage } from "../features/OverviewPage";
import { PortfolioPage } from "../features/PortfolioPage";
import { ReplayPage } from "../features/ReplayPage";
import { RiskPage } from "../features/RiskPage";
import { RunDetailPage } from "../features/RunDetailPage";
import { ShariahPage } from "../features/ShariahPage";

export const routes: RouteObject[] = [
  {
    path: "/",
    element: <AppShell />,
    errorElement: <RouteError />,
    children: [
      { index: true, element: <OverviewPage /> },
      { path: "runs/:runId", element: <RunDetailPage /> },
      { path: "runs/:runId/symbols/:symbol", element: <DecisionTrailPage /> },
      { path: "replay/:decisionId", element: <ReplayPage /> },
      { path: "risk", element: <RiskPage /> },
      { path: "portfolio", element: <PortfolioPage /> },
      { path: "shariah", element: <ShariahPage /> },
      { path: "graph", element: <GraphOverviewPage /> },
      { path: "graph/company/:symbol", element: <GraphCompanyPage /> },
      { path: "graph/edges/review", element: <GraphReviewPage /> },
      { path: "graph/signals", element: <GraphSignalsPage /> },
      { path: "history", element: <HistoryPage /> },
    ],
  },
];
