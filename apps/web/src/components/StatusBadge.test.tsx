import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { renderWithQueryClient } from "../test/test-utils";
import { StatusBadge } from "./StatusBadge";

describe("StatusBadge", () => {
  it("renders a known status label", () => {
    renderWithQueryClient(<StatusBadge status="APPROVED_FOR_PAPER" />);

    expect(screen.getByText("Approved for paper")).toBeInTheDocument();
  });

  it("renders pending next-open orders as queued", () => {
    renderWithQueryClient(<StatusBadge status="PENDING_NEXT_OPEN" />);

    expect(screen.getByText("Queued next open")).toBeInTheDocument();
  });

  it("humanizes unknown statuses", () => {
    renderWithQueryClient(<StatusBadge status="CUSTOM_STATUS" />);

    expect(screen.getByText("Custom Status")).toBeInTheDocument();
  });
});
