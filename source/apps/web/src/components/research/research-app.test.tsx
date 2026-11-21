import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { StreamEvent } from "@shopping-assistant/api-client";

import { AT_CONFIRMATION, detail } from "@/test/fixtures";

import { ResearchApp } from "./research-app";

const research = vi.hoisted(() => ({
  listThreads: vi.fn(),
  newThread: vi.fn(),
  getThread: vi.fn(),
  confirm: vi.fn(),
  send: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  research,
  errorMessage: (e: unknown) => (e instanceof Error ? e.message : "Something went wrong."),
}));

/** A stream the test feeds event by event. */
function controlledStream() {
  const queue: (StreamEvent | null)[] = [];
  let wake: (() => void) | null = null;
  async function* gen(): AsyncGenerator<StreamEvent> {
    for (;;) {
      while (!queue.length) await new Promise<void>((r) => (wake = r));
      const next = queue.shift()!;
      if (next === null) return;
      yield next;
    }
  }
  const push = (e: StreamEvent | null) => {
    queue.push(e);
    wake?.();
  };
  return { gen: gen(), push };
}

const RESULT: StreamEvent = {
  event: "result",
  data: { thread_id: "t1", reply: "", last_action: "researched", comparison: null, finalized_product: null, pending_confirmation: null, saved_item_ids: [] },
};

beforeEach(() => {
  vi.clearAllMocks();
  window.history.replaceState(null, "", "/research");
  research.listThreads.mockResolvedValue([]);
  research.newThread.mockResolvedValue("t1");
});

describe("ResearchApp (US-37)", () => {
  it("streams progress, disables the input, then shows the comparison as cards", async () => {
    const stream = controlledStream();
    research.send.mockReturnValue(stream.gen);
    research.getThread.mockResolvedValue(detail());
    render(<ResearchApp />);

    const input = screen.getByLabelText("Message");
    await userEvent.type(input, "noise cancelling headphones{Enter}");

    expect(await screen.findByText("noise cancelling headphones")).toBeInTheDocument();
    stream.push({ event: "progress", data: { step: "research_and_compare", message: "Searching independent reviews" } });
    expect(await screen.findByText("Searching independent reviews…")).toBeInTheDocument();
    expect(input).toBeDisabled();
    expect(window.location.search).toBe("?thread=t1");

    stream.push(RESULT);
    stream.push(null);
    expect(await screen.findByRole("article", { name: /Option 1: Sony/ })).toBeInTheDocument();
    expect(input).toBeEnabled();
    expect(research.send).toHaveBeenCalledWith("t1", "noise cancelling headphones");
  });

  it("chooses an option with the button", async () => {
    window.history.replaceState(null, "", "/research?thread=t1");
    research.getThread.mockResolvedValue(detail());
    const stream = controlledStream();
    research.send.mockReturnValue(stream.gen);
    render(<ResearchApp />);

    const bose = await screen.findByRole("article", { name: /Option 2/ });
    await userEvent.click(within(bose).getByRole("button", { name: "Choose this" }));
    expect(research.send).toHaveBeenCalledWith("t1", "I'll go with option 2: Bose QuietComfort Ultra");
  });

  it("shows an error inline, keeps the message, and retries it", async () => {
    const first = controlledStream();
    const second = controlledStream();
    research.send.mockReturnValueOnce(first.gen).mockReturnValueOnce(second.gen);
    research.getThread.mockResolvedValue(detail());
    render(<ResearchApp />);

    await userEvent.type(screen.getByLabelText("Message"), "noise cancelling headphones{Enter}");
    first.push({ event: "error", data: { code: "internal_error", message: "The AI service is busy.", details: null } });
    first.push(null);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("The AI service is busy.");
    expect(screen.getByText("noise cancelling headphones")).toBeInTheDocument();

    await userEvent.click(within(alert).getByRole("button", { name: "Retry" }));
    expect(research.send).toHaveBeenLastCalledWith("t1", "noise cancelling headphones");
    second.push(RESULT);
    second.push(null);
    expect(await screen.findByRole("article", { name: /Option 1/ })).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("shows a refusal before streaming (e.g. busy) as an error", async () => {
    research.send.mockImplementation(() => {
      throw new Error("The assistant is still working on this conversation.");
    });
    render(<ResearchApp />);
    await userEvent.type(screen.getByLabelText("Message"), "hi{Enter}");
    expect(await screen.findByRole("alert")).toHaveTextContent("still working");
  });

  it("lists conversations and opens one", async () => {
    research.listThreads.mockResolvedValue([detail().thread]);
    research.getThread.mockResolvedValue(detail());
    render(<ResearchApp />);
    const nav = screen.getByRole("navigation", { name: "Conversations" });
    await userEvent.click(await within(nav).findByRole("button", { name: /noise cancelling headphones/ }));
    expect(research.getThread).toHaveBeenCalledWith("t1");
    expect(await screen.findByRole("article", { name: /Option 1/ })).toBeInTheDocument();
  });
});

describe("ResearchApp tracking confirmation (US-38)", () => {
  it("shows the pending form again when the thread is reopened", async () => {
    window.history.replaceState(null, "", "/research?thread=t1");
    research.getThread.mockResolvedValue(AT_CONFIRMATION);
    render(<ResearchApp />);
    expect(await screen.findByRole("form", { name: /Track the price of Bose/ })).toBeInTheDocument();
    // The listings appear once (in the form), and the chosen card is marked.
    expect(screen.queryByRole("list", { name: "Retailer listings" })).not.toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /View at Amazon.ca/ })).toHaveLength(1);
    expect(screen.getByText("✓ Your choice")).toBeInTheDocument();
  });

  it("confirms, then links to the watchlist", async () => {
    window.history.replaceState(null, "", "/research?thread=t1");
    research.getThread.mockResolvedValueOnce(AT_CONFIRMATION).mockResolvedValueOnce({
      ...AT_CONFIRMATION,
      pending_confirmation: null,
      messages: [
        ...AT_CONFIRMATION.messages,
        { role: "assistant", text: "Tracking is set up for Bose QuietComfort Ultra:\n- Amazon.ca: …", comparison: null, listings: null },
      ],
    });
    research.confirm.mockResolvedValue({ ...RESULT.data, saved_item_ids: [7] });
    render(<ResearchApp />);

    await userEvent.click(await screen.findByRole("checkbox", { name: /Amazon.ca/ }));
    await userEvent.click(screen.getByRole("button", { name: "Start tracking (1)" }));

    expect(research.confirm).toHaveBeenCalledWith("t1", { action: "track", selected: [1], target_price: 359.1 });
    expect(await screen.findByRole("link", { name: "Go to your watchlist" })).toHaveAttribute("href", "/watchlist");
    expect(screen.getByText(/Tracking is set up for Bose/)).toBeInTheDocument();
    expect(screen.queryByRole("form", { name: /Track the price/ })).not.toBeInTheDocument();
  });

  it("keeps the form open with the server's message when a choice is rejected", async () => {
    window.history.replaceState(null, "", "/research?thread=t1");
    research.getThread.mockResolvedValue(AT_CONFIRMATION);
    research.confirm.mockRejectedValue(new Error("Listing number(s) [3] don't exist."));
    render(<ResearchApp />);
    await userEvent.click(await screen.findByRole("checkbox", { name: /Amazon.ca/ }));
    await userEvent.click(screen.getByRole("button", { name: /Start tracking/ }));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("[3] don't exist"));
    expect(screen.getByRole("form", { name: /Track the price/ })).toBeInTheDocument();
  });
});

describe("The web app never buys anything (US-42)", () => {
  it("only links out, in a new tab, with no buy/cart/checkout wording", async () => {
    window.history.replaceState(null, "", "/research?thread=t1");
    research.getThread.mockResolvedValue(AT_CONFIRMATION);
    const { container } = render(<ResearchApp />);
    await screen.findByRole("form", { name: /Track the price/ });

    const external = [...container.querySelectorAll("a")].filter((a) => a.getAttribute("href")?.startsWith("http"));
    expect(external.length).toBeGreaterThan(0);
    for (const a of external) {
      expect(a).toHaveAttribute("target", "_blank");
      expect(a.getAttribute("rel")).toBe("noopener noreferrer");
    }
    const actions = [...container.querySelectorAll("a, button")].map((el) => el.textContent ?? "");
    expect(actions.filter((t) => /\b(buy|cart|checkout|purchase|order)\b/i.test(t))).toEqual([]);
  });

  it("shows the decline message when asked to buy", async () => {
    const stream = controlledStream();
    research.send.mockReturnValue(stream.gen);
    const decline = "I can't make purchases, but I can track the price and alert you when it drops.";
    research.getThread.mockResolvedValue(
      detail({
        messages: [
          { role: "user", text: "buy it for me", comparison: null, listings: null },
          { role: "assistant", text: decline, comparison: null, listings: null },
        ],
        comparison: null,
      }),
    );
    render(<ResearchApp />);
    await userEvent.type(screen.getByLabelText("Message"), "buy it for me{Enter}");
    stream.push(RESULT);
    stream.push(null);
    expect(await screen.findByText(decline)).toBeInTheDocument();
  });
});
