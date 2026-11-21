import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { PENDING } from "@/test/fixtures";

import { suggestedTarget, TrackingForm } from "./tracking-form";

function setup(props: Partial<React.ComponentProps<typeof TrackingForm>> = {}) {
  const onSubmit = vi.fn();
  render(<TrackingForm pending={PENDING} busy={false} error={null} onSubmit={onSubmit} {...props} />);
  return { onSubmit, target: screen.getByLabelText("Alert me at or below") as HTMLInputElement };
}

describe("TrackingForm (US-38)", () => {
  it("shows each listing with price, stock, verified label and a link out", () => {
    setup();
    expect(screen.getByText("CA$399.00")).toBeInTheDocument();
    expect(screen.getByText("In stock")).toBeInTheDocument();
    expect(screen.getByText("Out of stock")).toBeInTheDocument();
    expect(screen.getByText("Verified price")).toBeInTheDocument();
    expect(screen.getByText("Estimated price")).toBeInTheDocument();
    const link = screen.getByRole("link", { name: /View at Amazon.ca/ });
    expect(link).toHaveAttribute("href", PENDING.listings[0].url);
  });

  it("pre-fills the suggested target and follows the selection until edited", async () => {
    const { target } = setup();
    expect(target.value).toBe("359.10");
    await userEvent.click(screen.getByRole("checkbox", { name: /Staples Canada/ }));
    expect(target.value).toBe(suggestedTarget([429.99], 0.1).toFixed(2)); // 386.99
    await userEvent.click(screen.getByRole("checkbox", { name: /Amazon.ca/ }));
    expect(target.value).toBe("359.10");
  });

  it("requires a listing and a valid target, without submitting", async () => {
    const { onSubmit, target } = setup();
    await userEvent.click(screen.getByRole("button", { name: /Start tracking/ }));
    expect(screen.getByRole("alert")).toHaveTextContent("Tick at least one listing");

    await userEvent.click(screen.getByRole("checkbox", { name: /Amazon.ca/ }));
    await userEvent.clear(target);
    await userEvent.type(target, "0");
    await userEvent.click(screen.getByRole("button", { name: /Start tracking/ }));
    expect(screen.getByRole("alert")).toHaveTextContent("above zero");
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("submits the selected listings and a custom target", async () => {
    const { onSubmit, target } = setup();
    await userEvent.click(screen.getByRole("checkbox", { name: /Staples Canada/ }));
    await userEvent.click(screen.getByRole("checkbox", { name: /Amazon.ca/ }));
    await userEvent.clear(target);
    await userEvent.type(target, "$349.5");
    await userEvent.click(screen.getByRole("button", { name: "Start tracking (2)" }));
    expect(onSubmit).toHaveBeenCalledWith({ action: "track", selected: [1, 2], target_price: 349.5 });
  });

  it("warns when the target is at or above the current price", async () => {
    const { target } = setup();
    await userEvent.click(screen.getByRole("checkbox", { name: /Amazon.ca/ }));
    await userEvent.clear(target);
    await userEvent.type(target, "450");
    expect(screen.getByText(/at or above the current price/)).toBeInTheDocument();
  });

  it("cancels without saving anything", async () => {
    const { onSubmit } = setup();
    await userEvent.click(screen.getByRole("button", { name: "Don't track" }));
    expect(onSubmit).toHaveBeenCalledWith({ action: "cancel", selected: [] });
  });

  it("shows a server error and disables itself while saving", () => {
    setup({ busy: true, error: "Listing number(s) [3] don't exist." });
    expect(screen.getByRole("alert")).toHaveTextContent("[3] don't exist");
    expect(screen.getByRole("button", { name: "Saving…" })).toBeDisabled();
  });
});
