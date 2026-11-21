# Business Requirements Document (BRD)
## Shopping Research Assistant

| Field | Value |
|---|---|
| Version | 1.1 (v2 scope added) |
| Date | 2026-11-21 (v1.0: 2026-11-15) |
| Source | [project-proposal.md](project-proposal.md) |
| Related | [FRD.md](FRD.md) |

---

## 1. Purpose
Define the business need, scope, and high-level requirements for an AI shopping assistant that helps a shopper pick the best product for their need and then watches its price so they can buy at a good moment, on their own terms.

## 2. Problem statement
Choosing a product means reading many reviews, comparing specs, and then checking several retailer sites repeatedly to catch a price drop. This is slow, repetitive, and easy to forget. Shoppers either overpay or spend hours researching.

## 3. Business goals
| ID | Goal |
|---|---|
| G-1 | Reduce the time to reach a confident product decision. |
| G-2 | Help the shopper buy at or below a price they consider fair. |
| G-3 | Remove the need to manually re-check retailer prices. |
| G-4 | Keep the shopper fully in control; the assistant never spends money. |

## 4. Success metrics
| Metric | Target (v1) |
|---|---|
| Turns to finalize a product | Typically ≤ 6 conversational turns |
| Comparison quality | 3–4 relevant candidates per research turn, each with specs, pros, cons, price range |
| Price-check cadence | Every 6 hours (configurable) while the monitor is running |
| Duplicate alerts | Zero alerts repeated for the same or higher price |
| Scrape success | ≥ 80% of checks on supported retailers return a price |
| Cost of monitoring | No LLM usage on price checks that do not produce an alert |

## 5. Stakeholders & users
| Role | Description |
|---|---|
| Primary user | An individual Canadian shopper on their own machine, using the web app (v2) or the CLI |
| Owner / developer | Project maintainer who configures API keys and notification channels |

**Persona:** A busy shopper who knows roughly what they need (e.g. "noise-cancelling headphones under $400") but not which model, and wants a nudge when the price drops.

## 6. Scope

### In scope (v1)
- Multi-turn conversational product research and comparison.
- User finalizes a single product per research session.
- Lookup of live listings at Canadian retailers: Amazon.ca, Walmart.ca, Staples.ca, Costco.ca, Dell Canada (dell.com/en-ca), Newegg.ca, Canada Computers, Canadian Tire, and official brand stores (Canadian storefronts).
- User confirms which listings to track and a target price.
- Persistent watchlist and price history on the local machine.
- Scheduled and manual background price checks.
- Price-drop alerts via console, webhook (Discord/Slack/Telegram), or email.
- Interactive CLI to research, view/manage the watchlist, and run checks.

### In scope (v2, added 2026-11-20)
- A browser web app (Next.js) for research, tracking confirmation, the watchlist with price-history charts, and alert settings, for a single local user. See [v2-user-stories.md](v2-user-stories.md).
- Local PostgreSQL storage with a data model ready for multiple users; the CLI keeps working on the same data.
- A background worker so scheduled checks run without the CLI open, while the laptop is on.
- Alert channel chosen and tested in the app; server secrets stay in local configuration.
- One-time import of a v1 watchlist.

### Out of scope
- Purchasing, checkout, payment handling, or adding items to carts (**prohibited**, not just deferred).
- Retailer accounts, logins, coupons, or loyalty programs.
- Non-Canadian retailers and currency conversion.
- Best Buy Canada (blocks automated price checks; excluded from v1, decided 2026-11-16).
- RONA (blocks automated price checks with DataDome; excluded from v1, decided 2026-11-16).
- ~~Web UI~~ (in scope for v2). Mobile apps, sign-in and multi-user accounts remain out of scope; the architecture allows adding them later ([backlog](backlog.md) BL-01, BL-02, BL-05).
- Hosted/always-on deployment (BL-08).

## 7. Business rules
| ID | Rule |
|---|---|
| BRL-1 | The assistant must never execute a purchase, handle payment details, or add to cart. |
| BRL-2 | Default currency is CAD. |
| BRL-3 | If the user does not specify a target price, suggest 10% below the current price. |
| BRL-4 | Alert only when the item is in stock. |
| BRL-5 | Never alert twice for the same or a higher price on the same item. |
| BRL-6 | Nothing is tracked without explicit user confirmation. |
| BRL-7 | Tracked items can be paused and resumed by the user. |

## 8. High-level business requirements
| ID | Requirement | Goal |
|---|---|---|
| BR-1 | The user can describe a need in natural language and receive a researched comparison of top candidates backed by independent reviews. | G-1 |
| BR-2 | The user can refine criteria (budget, specs, use case) over multiple turns, and the conversation is remembered across sessions. | G-1 |
| BR-3 | The user can explicitly choose a winning product. | G-1 |
| BR-4 | The system finds current retailer listings and prices for the chosen product. | G-2 |
| BR-5 | The user confirms which listings to track and the target alert price before anything is saved. | G-2, G-4 |
| BR-6 | The system checks tracked prices automatically on a schedule and on demand. | G-3 |
| BR-7 | The system keeps a price history and the lowest price seen per listing. | G-2 |
| BR-8 | The user is notified through their chosen channel when a meaningful price drop occurs. | G-2, G-3 |
| BR-9 | The user can view, pause, resume, and remove tracked items. | G-4 |
| BR-10 | The system never purchases or handles payment. | G-4 |

## 9. Assumptions
- The user supplies their own Anthropic and Tavily API keys.
- The user runs the application on their own machine with internet access.
- Retailer product pages are publicly accessible without login.

## 10. Constraints
- Python 3.11+; v1: local SQLite storage and a CLI; v2: local PostgreSQL, a local HTTP API and a web app (Node.js 20.9+).
- Background checks run only while a process is running: in v1 the CLI's monitor, in v2 the worker (no system service or hosting yet).
- No sign-in in v2: the API accepts connections from the local machine only.
- Third-party API usage limits and costs (Tavily, LLM) apply.

## 11. Risks
| Risk | Impact | Mitigation |
|---|---|---|
| Retailers block headless scraping (anti-bot) | Missed price checks | Record failed checks, keep tracking, try JSON-LD then CSS fallback; surface failures to the user |
| Search results show stale/incorrect prices | Wrong baseline/target | Verify baseline by scraping the listing at confirmation time |
| Retailer page layout changes | Extraction breaks | Prefer schema.org JSON-LD; isolate selectors per retailer |
| Retailer terms of service limit automated access | Compliance | Low frequency (6h), personal use only, honest user agent |
| LLM hallucinates product facts | Poor recommendations | Ground synthesis in search results; show sources |
| Process not running when price drops | Late alert | Document limitation; manual check available |

## 12. Approval
| Role | Name | Date |
|---|---|---|
| Owner | | |
