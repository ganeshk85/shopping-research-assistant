import type { PendingConfirmation, ResearchComparison, ThreadDetail } from "@shopping-assistant/api-client";

export const COMPARISON: ResearchComparison = {
  candidates: [
    {
      name: "Sony WH-1000XM5",
      brand: "Sony",
      estimated_price: 449.99,
      currency: "CAD",
      rating_summary: "Top-rated by RTINGS for noise cancelling.",
      key_specs: ["30 h battery", "LDAC"],
      pros: ["Best-in-class ANC"],
      cons: ["Doesn't fold flat"],
      best_for: "Frequent flyers",
    },
    {
      name: "Bose QuietComfort Ultra",
      brand: "Bose",
      estimated_price: 429.0,
      currency: "CAD",
      rating_summary: "Most comfortable in reviews.",
      key_specs: ["24 h battery"],
      pros: ["Very comfortable"],
      cons: ["Pricey"],
      best_for: "Long wear",
    },
  ],
  recommendation_summary: "Sony for ANC, Bose for comfort.",
  clarifying_question: null,
  sources: ["https://www.rtings.com/headphones/reviews/sony", "https://www.rtings.com/other", "https://www.pcmag.com/x"],
};

export const PENDING: PendingConfirmation = {
  product_name: "Bose QuietComfort Ultra",
  suggested_target: 359.1,
  discount: 0.1,
  listings: [
    {
      product_name: "Bose QuietComfort Ultra",
      retailer: "Amazon.ca",
      url: "https://www.amazon.ca/dp/B0CCZ1L489",
      current_price: 399.0,
      currency: "CAD",
      in_stock: true,
      price_verified: true,
      note: null,
    },
    {
      product_name: "Bose QuietComfort Ultra",
      retailer: "Staples Canada",
      url: "https://www.staples.ca/products/bose-qc-ultra",
      current_price: 429.99,
      currency: "CAD",
      in_stock: false,
      price_verified: false,
      note: null,
    },
  ],
};

const SUMMARY = {
  thread_id: "t1",
  title: "noise cancelling headphones",
  finalized_product: null,
  created_at: "2026-11-21T10:00:00Z",
  updated_at: "2026-11-21T10:05:00Z",
};

export function detail(overrides: Partial<ThreadDetail> = {}): ThreadDetail {
  return {
    thread: SUMMARY,
    messages: [
      { role: "user", text: "noise cancelling headphones", comparison: null, listings: null },
      { role: "assistant", text: "Here are the top options I found: ...", comparison: COMPARISON, listings: null },
    ],
    comparison: COMPARISON,
    finalized_product: null,
    pending_confirmation: null,
    ...overrides,
  };
}

export const AT_CONFIRMATION = detail({
  thread: { ...SUMMARY, finalized_product: "Bose QuietComfort Ultra" },
  messages: [
    ...detail().messages,
    { role: "user", text: "I'll go with option 2: Bose QuietComfort Ultra", comparison: null, listings: null },
    { role: "assistant", text: "Great choice: Bose QuietComfort Ultra.", comparison: null, listings: null },
    {
      role: "assistant",
      text: "I found 2 listings for Bose QuietComfort Ultra:\n1. Amazon.ca ...",
      comparison: null,
      listings: PENDING.listings,
    },
  ],
  finalized_product: { name: "Bose QuietComfort Ultra", brand: "Bose", estimated_price: 429, currency: "CAD" },
  pending_confirmation: PENDING,
});
