import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { CheckRun, WatchlistItem } from "@shopping-assistant/api-client";

import { WatchlistApp } from "./watchlist-app";

const watchlist = vi.hoisted(() => ({ list: vi.fn(), update: vi.fn(), remove: vi.fn(), history: vi.fn() }));
const checks = vi.hoisted(() => ({ start: vi.fn(), get: vi.fn(), status: vi.fn() }));

vi.mock("@/lib/api", () => ({
  watchlist,
  checks,
  errorMessage: (e: unknown) => (e instanceof Error ? e.message : "Something went wrong."),
}));

const NOW = new Date().toISOString();

function item(overrides: Partial<WatchlistItem> = {}): WatchlistItem {
  return {
    id: 1,
    product_name: "Sony WH-1000XM6",
    retailer: "Amazon.ca",
    url: "https://www.amazon.ca/dp/B0F3PQHWTZ",
    currency: "CAD",
    status: "active",
    initial_price: 498,
    target_price: 430.2,
    lowest_price_seen: 449,
    latest_price: 459,
    latest_in_stock: true,
    last_checked_at: NOW,
    last_check_error: null,
    consecutive_failures: 0,
    needs_attention: false,
    created_at: NOW,
    ...overrides,
  };
}

function run(overrides: Partial<CheckRun> = {}): CheckRun {
  return {
    id: 5, trigger: "api", status: "running", started_at: NOW, finished_at: null, active_items: null,
    checked: null, failed: null, alerts_sent: null, alerts_failed: null, error: null, ...overrides,
  };
}

const card = (name = /Sony WH-1000XM6/) => screen.findByRole("article", { name });

beforeEach(() => {
  vi.clearAllMocks();
  checks.status.mockResolvedValue({ running: null, last_finished: null, schedule: { worker_running: false } });
});

describe("WatchlistApp (US-39)", () => {
  it("shows each item's prices, status, last check and flags", async () => {
    watchlist.list.mockResolvedValue([
      item(),
      item({
        id: 2, retailer: "Walmart.com", currency: "USD", latest_in_stock: false, needs_attention: true,
        consecutive_failures: 3, last_check_error: "blocked", status: "paused", last_checked_at: null,
      }),
    ]);
    render(<WatchlistApp />);

    const [sony, walmart] = await screen.findAllByRole("article");
    expect(within(sony).getByText("CA$459.00")).toBeInTheDocument();
    expect(within(sony).getByText("CA$449.00")).toBeInTheDocument();
    expect(within(sony).getByText("CA$430.20")).toBeInTheDocument();
    expect(within(sony).getByText("Active")).toBeInTheDocument();
    expect(within(sony).getByText("Checked just now")).toBeInTheDocument();
    expect(within(sony).getByRole("link", { name: /Amazon.ca/ })).toHaveAttribute("target", "_blank");

    expect(within(walmart).getByText("Out of stock")).toBeInTheDocument();
    expect(within(walmart).getByText("Paused")).toBeInTheDocument();
    expect(within(walmart).getByText("Priced in USD")).toBeInTheDocument();
    expect(within(walmart).getByText(/The last 3 checks failed \(blocked\)/)).toBeInTheDocument();
    expect(within(walmart).getByText("Not checked yet")).toBeInTheDocument();
    expect(within(walmart).getByRole("button", { name: "Resume" })).toBeInTheDocument();
  });

  it("links to Research when empty", async () => {
    watchlist.list.mockResolvedValue([]);
    render(<WatchlistApp />);
    expect(await screen.findByRole("link", { name: "Start researching" })).toHaveAttribute("href", "/research");
  });

  it("pauses and resumes", async () => {
    watchlist.list.mockResolvedValue([item()]);
    watchlist.update.mockResolvedValue(item({ status: "paused" }));
    render(<WatchlistApp />);
    await userEvent.click(within(await card()).getByRole("button", { name: "Pause" }));
    expect(watchlist.update).toHaveBeenCalledWith(1, { status: "paused" });
    expect(await within(await card()).findByRole("button", { name: "Resume" })).toBeInTheDocument();
  });

  it("edits the target inline with validation", async () => {
    watchlist.list.mockResolvedValue([item()]);
    watchlist.update.mockResolvedValue(item({ target_price: 399.99 }));
    render(<WatchlistApp />);
    const c = await card();
    await userEvent.click(within(c).getByRole("button", { name: "Edit target" }));
    const input = within(c).getByLabelText("New target");
    expect(input).toHaveValue("430.20");

    await userEvent.clear(input);
    await userEvent.type(input, "-5");
    await userEvent.click(within(c).getByRole("button", { name: "Save" }));
    expect(within(c).getByRole("alert")).toHaveTextContent("above zero");
    expect(watchlist.update).not.toHaveBeenCalled();

    await userEvent.clear(input);
    await userEvent.type(input, "399.99");
    await userEvent.click(within(c).getByRole("button", { name: "Save" }));
    expect(watchlist.update).toHaveBeenCalledWith(1, { target_price: 399.99 });
    expect(await within(c).findByText("CA$399.99")).toBeInTheDocument();
  });

  it("asks before deleting, and Keep it cancels", async () => {
    watchlist.list.mockResolvedValue([item()]);
    watchlist.remove.mockResolvedValue(undefined);
    render(<WatchlistApp />);
    const c = await card();

    await userEvent.click(within(c).getByRole("button", { name: "Delete" }));
    expect(within(c).getByRole("alertdialog")).toHaveTextContent("can't be undone");
    await userEvent.click(within(c).getByRole("button", { name: "Keep it" }));
    expect(watchlist.remove).not.toHaveBeenCalled();

    await userEvent.click(within(c).getByRole("button", { name: "Delete" }));
    await userEvent.click(within(within(c).getByRole("alertdialog")).getByRole("button", { name: "Delete" }));
    expect(watchlist.remove).toHaveBeenCalledWith(1);
    await waitFor(() => expect(screen.queryByRole("article")).not.toBeInTheDocument());
  });

  it("shows an action's error on the item", async () => {
    watchlist.list.mockResolvedValue([item()]);
    watchlist.update.mockRejectedValue(new Error("Watchlist item not found."));
    render(<WatchlistApp />);
    const c = await card();
    await userEvent.click(within(c).getByRole("button", { name: "Pause" }));
    expect(await within(c).findByRole("alert")).toHaveTextContent("not found");
  });

  it("opens the price history chart and table", async () => {
    watchlist.list.mockResolvedValue([item()]);
    watchlist.history.mockResolvedValue({
      item_id: 1, currency: "CAD", target_price: 430.2,
      entries: [
        { id: 1, price: 498, in_stock: true, checked_at: "2026-11-16T14:00:00Z", is_lowest: false },
        { id: 2, price: 449, in_stock: true, checked_at: "2026-11-17T14:00:00Z", is_lowest: true },
      ],
    });
    render(<WatchlistApp />);
    const c = await card();
    await userEvent.click(within(c).getByRole("button", { name: "Price history" }));
    expect(await within(c).findByRole("img", { name: /Price history: 2 check/ })).toBeInTheDocument();
    expect(within(c).getByRole("table")).toBeInTheDocument();
    expect(within(c).getByRole("button", { name: "Hide history" })).toHaveAttribute("aria-expanded", "true");
  });
});

describe("Check now (US-39 / US-32)", () => {
  it("starts a check, is disabled while it runs, then shows the summary and reloads", async () => {
    watchlist.list.mockResolvedValue([item()]);
    checks.start.mockResolvedValue(run());
    checks.get
      .mockResolvedValueOnce(run())
      .mockResolvedValueOnce(run({ status: "finished", finished_at: NOW, active_items: 2, checked: 2, failed: 0, alerts_sent: 1, alerts_failed: 0 }));
    render(<WatchlistApp pollMs={10} />);
    await card();

    await userEvent.click(screen.getByRole("button", { name: "Check now" }));
    expect(screen.getByRole("button", { name: "Checking prices…" })).toBeDisabled();
    expect(await screen.findByText(/Checked 2 of 2 item\(s\): 1 alert\(s\) sent\./)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Check now" })).toBeEnabled();
    expect(watchlist.list).toHaveBeenCalledTimes(2);
  });

  it("follows a check the worker already started", async () => {
    watchlist.list.mockResolvedValue([item()]);
    checks.status.mockResolvedValue({ running: run({ id: 9, trigger: "schedule" }), last_finished: null, schedule: { worker_running: true } });
    checks.get.mockResolvedValue(run({ id: 9, trigger: "schedule" }));
    render(<WatchlistApp pollMs={10_000} />);
    expect(await screen.findByRole("button", { name: "Checking prices…" })).toBeDisabled();
    expect(screen.getByText(/by the background worker/)).toBeInTheDocument();
  });

  it("follows the running check when refused with 409", async () => {
    watchlist.list.mockResolvedValue([item()]);
    checks.start.mockRejectedValue(new Error("A price check is already running."));
    checks.status
      .mockResolvedValueOnce({ running: null, last_finished: null, schedule: { worker_running: false } })
      .mockResolvedValueOnce({ running: run({ id: 4, trigger: "cli" }), last_finished: null, schedule: { worker_running: false } });
    checks.get.mockResolvedValue(run({ id: 4, trigger: "cli" }));
    render(<WatchlistApp pollMs={10_000} />);
    await card();
    await act(() => userEvent.click(screen.getByRole("button", { name: "Check now" })));
    expect(await screen.findByText(/by the CLI/)).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("reports a failed check", async () => {
    watchlist.list.mockResolvedValue([item()]);
    checks.status.mockResolvedValue({
      running: null,
      last_finished: run({ status: "failed", finished_at: NOW, error: "Setup needed: Missing WEBHOOK_URL" }),
      schedule: { worker_running: false },
    });
    render(<WatchlistApp />);
    expect(await screen.findByText(/The price check failed: Setup needed: Missing WEBHOOK_URL/)).toBeInTheDocument();
  });
});
