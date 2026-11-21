import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { PriceHistory } from "@shopping-assistant/api-client";

import { HistoryTable, niceTicks, PriceHistoryChart } from "./price-history-chart";

const HISTORY: PriceHistory = {
  item_id: 1,
  currency: "CAD",
  target_price: 430.2,
  entries: [
    { id: 1, price: 498, in_stock: true, checked_at: "2026-11-16T14:00:00Z", is_lowest: false },
    { id: 2, price: 449, in_stock: true, checked_at: "2026-11-17T14:00:00Z", is_lowest: true },
    { id: 3, price: 429, in_stock: false, checked_at: "2026-11-18T14:00:00Z", is_lowest: false },
    { id: 4, price: 459, in_stock: true, checked_at: "2026-11-19T14:00:00Z", is_lowest: false },
  ],
};

describe("PriceHistoryChart (US-40)", () => {
  it("summarises the history for screen readers", () => {
    render(<PriceHistoryChart history={HISTORY} />);
    expect(screen.getByRole("img")).toHaveAccessibleName(
      /4 check\(s\) .* latest CA\$459\.00, target CA\$430\.20, lowest in stock CA\$449\.00/,
    );
  });

  it("labels the target line and the lowest in-stock price", () => {
    render(<PriceHistoryChart history={HISTORY} />);
    expect(screen.getByText("Target CA$430.20")).toBeInTheDocument();
    expect(screen.getByText("Lowest CA$449.00")).toBeInTheDocument();
  });

  it("draws out-of-stock checks differently, with a key", () => {
    render(<PriceHistoryChart history={HISTORY} />);
    expect(screen.getAllByTestId("point-in-stock")).toHaveLength(3);
    expect(screen.getAllByTestId("point-out-of-stock")).toHaveLength(1);
    expect(screen.getByText("In stock")).toBeInTheDocument();
  });

  it("shows a tooltip for the nearest check on hover", () => {
    const { container } = render(<PriceHistoryChart history={HISTORY} />);
    const overlay = container.querySelector("rect")!;
    overlay.getBoundingClientRect = () => ({ left: 0, width: 560, top: 0, height: 172, right: 560, bottom: 172, x: 0, y: 0, toJSON() {} });
    fireEvent.pointerMove(overlay, { clientX: 999 });
    const tip = screen.getByRole("tooltip");
    expect(tip).toHaveTextContent("CA$459.00");
    expect(tip).toHaveTextContent("In stock");
    fireEvent.pointerLeave(overlay);
    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
  });

  it("handles a single check", () => {
    render(<PriceHistoryChart history={{ ...HISTORY, entries: HISTORY.entries.slice(0, 1) }} />);
    expect(screen.getByRole("img")).toHaveAccessibleName(/1 check\(s\)/);
  });
});

describe("HistoryTable (US-40)", () => {
  it("lists every check oldest first with the lowest flagged", () => {
    render(<HistoryTable history={HISTORY} />);
    const rows = screen.getAllByRole("row").slice(1);
    expect(rows.map((r) => within(r).getAllByRole("cell")[1].textContent)).toEqual([
      "CA$498.00", "CA$449.00lowest", "CA$429.00", "CA$459.00",
    ]);
    expect(within(rows[2]).getByText("Out of stock")).toBeInTheDocument();
  });
});

describe("niceTicks", () => {
  it("picks round steps", () => {
    expect(niceTicks(400, 510)).toEqual([400, 450, 500]);
    expect(niceTicks(395, 470)).toEqual([400, 420, 440, 460]);
    expect(niceTicks(5, 5)).toEqual([5]);
  });
});
