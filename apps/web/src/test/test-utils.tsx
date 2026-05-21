import type { ReactElement } from "react";
import { QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";

import { createTaurusQueryClient } from "../app/providers";

export function renderWithQueryClient(ui: ReactElement) {
  const queryClient = createTaurusQueryClient();
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}
