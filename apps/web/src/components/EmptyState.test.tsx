import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { renderWithQueryClient } from "../test/test-utils";
import { EmptyState } from "./EmptyState";

describe("EmptyState", () => {
  it("renders commands when provided", () => {
    renderWithQueryClient(
      <EmptyState
        commands={["make api", "make ui"]}
        message="No local services are available."
        title="Start services"
      />,
    );

    expect(screen.getByText("Start services")).toBeInTheDocument();
    expect(screen.getByText("make api")).toBeInTheDocument();
    expect(screen.getByText("make ui")).toBeInTheDocument();
  });
});
