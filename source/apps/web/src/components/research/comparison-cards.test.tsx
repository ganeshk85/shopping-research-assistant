import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { COMPARISON } from "@/test/fixtures";

import { ComparisonCards } from "./comparison-cards";

describe("ComparisonCards (US-37)", () => {
  it("shows numbered cards with the details, recommendation and sources", () => {
    render(<ComparisonCards comparison={COMPARISON} />);

    const sony = screen.getByRole("article", { name: "Option 1: Sony WH-1000XM5" });
    expect(within(sony).getByText("1")).toBeInTheDocument();
    expect(within(sony).getByText("Sony")).toBeInTheDocument();
    expect(within(sony).getByText("CA$449.99")).toBeInTheDocument();
    expect(within(sony).getByText("30 h battery")).toBeInTheDocument();
    expect(within(sony).getByText("Best-in-class ANC")).toBeInTheDocument();
    expect(within(sony).getByText("Doesn't fold flat")).toBeInTheDocument();
    expect(within(sony).getByText("Frequent flyers")).toBeInTheDocument();
    expect(screen.getByRole("article", { name: "Option 2: Bose QuietComfort Ultra" })).toBeInTheDocument();

    expect(screen.getByText("Sony for ANC, Bose for comfort.")).toBeInTheDocument();
    const links = screen.getAllByRole("link");
    expect(links.map((a) => a.textContent)).toEqual([
      "rtings.com (opens in a new tab)",
      "pcmag.com (opens in a new tab)",
    ]); // one link per site
  });

  it("calls onChoose with the option number", async () => {
    const onChoose = vi.fn();
    render(<ComparisonCards comparison={COMPARISON} onChoose={onChoose} />);
    const bose = screen.getByRole("article", { name: /Option 2/ });
    await userEvent.click(within(bose).getByRole("button", { name: "Choose this" }));
    expect(onChoose).toHaveBeenCalledWith(2, COMPARISON.candidates[1]);
  });

  it("has no Choose buttons for an older comparison and marks the chosen product", () => {
    render(<ComparisonCards comparison={COMPARISON} chosenName="Bose QuietComfort Ultra" />);
    expect(screen.queryByRole("button", { name: "Choose this" })).not.toBeInTheDocument();
    expect(within(screen.getByRole("article", { name: /Option 2/ })).getByText("✓ Your choice")).toBeInTheDocument();
  });
});
