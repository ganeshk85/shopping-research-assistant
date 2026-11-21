"""HTTP API (Sprint 7: US-29, US-30, US-31, US-33). FastAPI TestClient + the offline fakes;
data goes to the local test database."""

import json

import pytest
from fastapi.testclient import TestClient

from shopping_assistant.api.app import DEFAULT_OPENAPI_PATH, create_app, openapi_json
from shopping_assistant.models import IntentDecision
from shopping_assistant.research import ResearchSession

from test_research_graph import COMPARISON, FakeLLM, explore
from test_tracking_flow import AMZ, STAPLES, FakeRetailSearch, FakeVerifier

V1 = "/api/v1"
FINALIZE_2 = IntentDecision(intent="finalize_product", candidate_number=2, search_query="headphones")


@pytest.fixture
def make_client(settings_factory, store):
    """A client whose research sessions use fakes. `decisions` feed the intent LLM in order."""

    def make(*decisions, settings=None, **session_kw):
        settings = settings or settings_factory()

        def factory(user_store):
            return ResearchSession(
                settings, store=user_store,
                intent_llm=FakeLLM(*decisions), research_llm=FakeLLM(COMPARISON, COMPARISON),
                search=session_kw.get("search") or FakeRetailSearch(),
                verify_prices=session_kw.get("verifier") or FakeVerifier(),
            )

        return TestClient(create_app(settings, session_factory=factory))

    return make


def send(client, thread, text):
    """POST a message and parse the Server-Sent Events into [(event, data), ...]."""
    with client.stream("POST", f"{V1}/threads/{thread}/messages", json={"text": text}) as r:
        assert r.status_code == 200, r.read()
        assert r.headers["content-type"].startswith("text/event-stream")
        body = r.read().decode("utf-8")
    events = []
    for block in body.strip().split("\n\n"):
        fields = dict(line.split(": ", 1) for line in block.splitlines())
        events.append((fields["event"], json.loads(fields["data"])))
    return events


def result_of(events):
    assert [e for e, _ in events].count("result") == 1 and events[-1][0] == "result", events
    return events[-1][1]


def new_thread(client):
    r = client.post(f"{V1}/threads")
    assert r.status_code == 201
    return r.json()["thread_id"]


def at_confirmation(make_client):
    """A client and thread that have researched, then finalized option 2 (Bose)."""
    client = make_client(explore("headphones"), FINALIZE_2)
    thread = new_thread(client)
    send(client, thread, "noise cancelling headphones")
    send(client, thread, "option 2")
    return client, thread


# --- system --------------------------------------------------------------------------


def test_health(make_client):
    assert make_client().get(f"{V1}/health").json() == {"status": "ok", "database": "ok"}


def test_health_reports_missing_database(settings_factory):
    client = TestClient(create_app(settings_factory(database_url="")))
    assert client.get(f"{V1}/health").json() == {"status": "ok", "database": "unavailable"}


def test_cors_allows_only_the_web_app(make_client):
    client = make_client()
    ok = client.options(f"{V1}/watchlist", headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "GET"})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:3000"
    bad = client.options(f"{V1}/watchlist", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"})
    assert "access-control-allow-origin" not in bad.headers


# --- US-29: research chat --------------------------------------------------------------


def test_research_turn_streams_progress_then_result(make_client):
    client = make_client(explore("headphones"))
    thread = new_thread(client)
    assert client.get(f"{V1}/threads").json() == []  # nothing stored before the first message

    events = send(client, thread, "noise cancelling headphones")
    progress = [d for e, d in events if e == "progress"]
    assert [p["step"] for p in progress] == ["understand_intent", "research_and_compare"]
    assert progress[1]["message"].startswith("Searching independent reviews")
    result = result_of(events)
    assert result["last_action"] == "researched" and result["thread_id"] == thread
    assert [c["name"] for c in result["comparison"]["candidates"]][:2] == ["Sony WH-1000XM5", "Bose QuietComfort Ultra"]
    assert result["finalized_product"] is None and result["pending_confirmation"] is None

    [summary] = client.get(f"{V1}/threads").json()
    assert summary["thread_id"] == thread and summary["title"] == "noise cancelling headphones"
    detail = client.get(f"{V1}/threads/{thread}").json()
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant"]
    assert detail["comparison"]["candidates"][0]["name"] == "Sony WH-1000XM5"


def test_finalize_streams_listing_lookup_and_returns_pending_confirmation(make_client):
    client, thread = at_confirmation(make_client)
    detail = client.get(f"{V1}/threads/{thread}").json()
    assert detail["thread"]["finalized_product"] == "Bose QuietComfort Ultra"
    pending = detail["pending_confirmation"]
    assert pending["product_name"] == "Bose QuietComfort Ultra" and pending["suggested_target"] == 359.1
    assert [(l["retailer"], l["current_price"], l["price_verified"]) for l in pending["listings"]] == [
        ("Amazon.ca", 399.0, True), ("Staples Canada", 429.99, True)
    ]
    assert client.get(f"{V1}/threads/{thread}/confirmation").json() == pending


def test_thread_messages_carry_comparison_and_listings_for_cards(make_client):
    """US-37/38: each message that showed a comparison or listings returns them structured."""
    client, thread = at_confirmation(make_client)
    messages = client.get(f"{V1}/threads/{thread}").json()["messages"]
    assert [m["role"] for m in messages] == ["user", "assistant", "user", "assistant", "assistant"]
    comparison_msgs = [m for m in messages if m["comparison"]]
    assert len(comparison_msgs) == 1
    assert comparison_msgs[0]["comparison"]["candidates"][1]["name"] == "Bose QuietComfort Ultra"
    [listing_msg] = [m for m in messages if m["listings"]]
    assert [l["retailer"] for l in listing_msg["listings"]] == ["Amazon.ca", "Staples Canada"]
    assert all(m["comparison"] is None and m["listings"] is None for m in messages if m["role"] == "user")


def test_attached_cards_are_never_sent_to_the_model():
    """The structured data rides in additional_kwargs, which langchain-anthropic doesn't send."""
    from langchain_anthropic.chat_models import _format_messages
    from langchain_core.messages import AIMessage, HumanMessage

    msg = AIMessage("1. Sony", additional_kwargs={"comparison": {"candidates": [{"name": "SECRET-CARD"}]},
                                                  "listings": [{"url": "SECRET-URL"}]})
    formatted = _format_messages([HumanMessage("hi"), msg, HumanMessage("option 1")], model="claude-sonnet-5-5")
    assert "SECRET" not in repr(formatted)


def test_finalize_progress_includes_the_listing_lookup(make_client):
    client = make_client(explore("headphones"), FINALIZE_2)
    thread = new_thread(client)
    send(client, thread, "noise cancelling headphones")
    events = send(client, thread, "option 2")
    steps = [d["step"] for e, d in events if e == "progress"]
    assert steps == ["understand_intent", "finalize_product", "locate_retail_listings", "confirm_tracking_terms"]
    result = result_of(events)
    assert result["finalized_product"]["name"] == "Bose QuietComfort Ultra"
    assert len(result["pending_confirmation"]["listings"]) == 2


def test_empty_message_is_a_validation_error(make_client):
    client = make_client()
    r = client.post(f"{V1}/threads/abc/messages", json={"text": "   "})
    assert r.status_code == 422
    body = r.json()
    assert body["code"] == "validation_error" and body["details"][0]["field"] == "text"


def test_turn_failure_arrives_as_an_error_event_and_frees_the_thread(make_client, monkeypatch):
    client = make_client(explore("headphones"))
    thread = new_thread(client)

    def boom(*a, **kw):
        raise RuntimeError("anthropic overloaded")

    monkeypatch.setattr(ResearchSession, "send", boom)
    events = send(client, thread, "headphones")
    assert events == [("error", {"code": "internal_error", "message": "Something went wrong. Please try again.", "details": None})]

    monkeypatch.undo()  # the thread isn't stuck as "busy": the next message works
    assert result_of(send(client, thread, "headphones"))["last_action"] == "researched"


def test_one_turn_at_a_time_per_thread(make_client):
    client = make_client(explore("headphones"))
    thread = new_thread(client)
    client.app.state.services.claim_thread(thread)  # as if a turn were running
    r = client.post(f"{V1}/threads/{thread}/messages", json={"text": "hi"})
    assert r.status_code == 409 and r.json()["code"] == "thread_busy"


def test_unknown_thread_is_404(make_client):
    client = make_client()
    for r in (client.get(f"{V1}/threads/nope"), client.get(f"{V1}/threads/nope/confirmation"),
              client.post(f"{V1}/threads/nope/confirmation", json={"action": "cancel"})):
        assert r.status_code == 404 and r.json()["code"] == "not_found"


def test_research_needs_the_anthropic_key_but_the_watchlist_does_not(settings_factory, store):
    client = TestClient(create_app(settings_factory(anthropic_api_key="")))
    r = client.post(f"{V1}/threads/t1/messages", json={"text": "headphones"})
    assert r.status_code == 503 and r.json()["code"] == "not_configured" and "ANTHROPIC_API_KEY" in r.json()["message"]
    assert client.get(f"{V1}/watchlist").status_code == 200


# --- US-30: confirm or cancel ----------------------------------------------------------


@pytest.mark.parametrize(
    "body, code",
    [
        ({"action": "track", "selected": []}, "invalid_decision"),
        ({"action": "track", "selected": [9]}, "invalid_decision"),
        ({"action": "track", "selected": [1, 1]}, "invalid_decision"),
        ({"action": "track", "selected": [1], "target_price": 0}, "validation_error"),
        ({"action": "buy", "selected": [1]}, "validation_error"),
    ],
)
def test_invalid_confirmation_keeps_it_pending(make_client, body, code):
    client, thread = at_confirmation(make_client)
    r = client.post(f"{V1}/threads/{thread}/confirmation", json=body)
    assert r.status_code == 422 and r.json()["code"] == code
    assert client.get(f"{V1}/threads/{thread}/confirmation").status_code == 200  # still pending
    assert client.get(f"{V1}/watchlist").json() == []


def test_confirm_saves_items_and_clears_the_confirmation(make_client):
    client, thread = at_confirmation(make_client)
    r = client.post(f"{V1}/threads/{thread}/confirmation", json={"action": "track", "selected": [1, 2], "target_price": 380})
    assert r.status_code == 200
    turn = r.json()
    assert turn["last_action"] == "tracking_saved" and len(turn["saved_item_ids"]) == 2
    assert "Tracking is set up for Bose QuietComfort Ultra" in turn["reply"]

    items = client.get(f"{V1}/watchlist").json()
    assert sorted(i["id"] for i in items) == sorted(turn["saved_item_ids"])
    assert {(i["retailer"], i["target_price"], i["status"]) for i in items} == {
        ("Amazon.ca", 380.0, "active"), ("Staples Canada", 380.0, "active")
    }
    r = client.get(f"{V1}/threads/{thread}/confirmation")
    assert r.status_code == 404 and r.json()["code"] == "no_pending_confirmation"
    r = client.post(f"{V1}/threads/{thread}/confirmation", json={"action": "cancel"})
    assert r.status_code == 409 and r.json()["code"] == "no_pending_confirmation"


def test_cancel_saves_nothing(make_client):
    client, thread = at_confirmation(make_client)
    turn = client.post(f"{V1}/threads/{thread}/confirmation", json={"action": "cancel"}).json()
    assert turn["last_action"] == "tracking_cancelled" and turn["saved_item_ids"] == []
    assert client.get(f"{V1}/watchlist").json() == []


def test_purchase_request_is_declined(make_client):
    client = make_client(explore("headphones"), IntentDecision(intent="purchase_request", search_query="buy"))
    thread = new_thread(client)
    send(client, thread, "headphones")
    result = result_of(send(client, thread, "just buy option 2 for me"))
    assert result["last_action"] == "declined" and "can't buy, order, or add anything to a cart" in result["reply"]
    assert client.get(f"{V1}/watchlist").json() == []


# --- US-31: watchlist ---------------------------------------------------------------------


@pytest.fixture
def seeded(store):
    a = store.add_tracked_item(product_name="Sony WH-1000XM6", retailer="Amazon.ca", url=AMZ,
                               initial_price=478.0, target_price=430.2)
    s = store.add_tracked_item(product_name="Sony WH-1000XM6", retailer="Staples Canada", url=STAPLES,
                               initial_price=479.99, target_price=430.2)
    return a, s


def test_list_and_get_items(make_client, store, seeded):
    amz, staples = seeded
    store.record_price_check(amz, 399.0, False)
    store.mark_check_ok(amz)
    store.mark_check_failed(staples, "blocked")
    store.mark_check_failed(staples, "blocked")
    client = make_client()

    items = {i["id"]: i for i in client.get(f"{V1}/watchlist").json()}
    a = items[amz]
    assert (a["latest_price"], a["latest_in_stock"], a["lowest_price_seen"]) == (399.0, False, 478.0)
    assert a["last_checked_at"] is not None and a["needs_attention"] is False and a["currency"] == "CAD"
    s = items[staples]
    assert s["needs_attention"] is True and s["consecutive_failures"] == 2 and s["last_check_error"] == "blocked"
    assert client.get(f"{V1}/watchlist/{amz}").json() == a


def test_pause_resume_and_retarget(make_client, seeded):
    amz, _ = seeded
    client = make_client()
    assert client.patch(f"{V1}/watchlist/{amz}", json={"status": "paused"}).json()["status"] == "paused"
    assert client.patch(f"{V1}/watchlist/{amz}", json={"status": "active"}).json()["status"] == "active"
    item = client.patch(f"{V1}/watchlist/{amz}", json={"target_price": 399.999}).json()
    assert item["target_price"] == 400.0


@pytest.mark.parametrize("body", [{}, {"target_price": -5}, {"status": "deleted"}])
def test_invalid_update(make_client, seeded, body):
    r = make_client().patch(f"{V1}/watchlist/{seeded[0]}", json=body)
    assert r.status_code == 422 and r.json()["code"] == "validation_error"


def test_delete_removes_item_and_history(make_client, store, seeded):
    amz, _ = seeded
    client = make_client()
    assert client.delete(f"{V1}/watchlist/{amz}").status_code == 204
    assert client.get(f"{V1}/watchlist/{amz}").status_code == 404
    assert client.get(f"{V1}/watchlist/{amz}/history").status_code == 404
    assert client.delete(f"{V1}/watchlist/{amz}").status_code == 404
    assert store.get_price_history(amz) == []


def test_history_oldest_first_with_first_lowest_in_stock_flagged(make_client, store, seeded):
    amz, _ = seeded
    store.record_price_check(amz, 350.0, False)  # cheaper but out of stock
    store.record_price_check(amz, 399.0, True)
    store.record_price_check(amz, 399.0, True)
    history = make_client().get(f"{V1}/watchlist/{amz}/history").json()
    assert history["target_price"] == 430.2 and history["currency"] == "CAD"
    assert [(e["price"], e["in_stock"], e["is_lowest"]) for e in history["entries"]] == [
        (478.0, True, False), (350.0, False, False), (399.0, True, True), (399.0, True, False)
    ]


def test_unknown_item_is_404(make_client, store):
    client = make_client()
    for r in (client.get(f"{V1}/watchlist/999"), client.patch(f"{V1}/watchlist/999", json={"status": "paused"}),
              client.delete(f"{V1}/watchlist/999"), client.get(f"{V1}/watchlist/999/history")):
        assert r.status_code == 404 and r.json() == {"code": "not_found", "message": "Watchlist item not found.", "details": None}


# --- multi-user readiness (US-26 via the API) --------------------------------------------


def test_another_users_items_and_threads_are_invisible(make_client, pg_database, store, seeded):
    alice = pg_database.for_user(pg_database.create_user("alice"))
    theirs = alice.add_tracked_item(product_name="X", retailer="Costco", url="https://www.costco.ca/p/x",
                                    initial_price=100.0, target_price=90.0)
    alice.upsert_research_thread("alice-thread", "alice's research")
    client = make_client(explore("x"))  # acts as the default admin

    assert theirs not in [i["id"] for i in client.get(f"{V1}/watchlist").json()]
    for r in (client.get(f"{V1}/watchlist/{theirs}"), client.patch(f"{V1}/watchlist/{theirs}", json={"status": "paused"}),
              client.delete(f"{V1}/watchlist/{theirs}"), client.get(f"{V1}/watchlist/{theirs}/history"),
              client.get(f"{V1}/threads/alice-thread"),
              client.post(f"{V1}/threads/alice-thread/messages", json={"text": "hijack"}),
              client.post(f"{V1}/threads/alice-thread/confirmation", json={"action": "cancel"})):
        assert r.status_code == 404, r.text
    assert [t["thread_id"] for t in client.get(f"{V1}/threads").json()] == []
    assert alice.get_tracked_item(theirs).status == "active"


# --- US-33: contract ------------------------------------------------------------------------


def test_no_endpoint_accepts_a_user_id():
    spec = json.loads(openapi_json())
    assert all(path.startswith("/api/v1/") for path in spec["paths"])
    text = json.dumps(spec["paths"])
    assert "user_id" not in text and "userId" not in text


def test_errors_and_stream_events_are_in_the_spec():
    spec = json.loads(openapi_json())
    schemas = spec["components"]["schemas"]
    assert {"ErrorBody", "StreamEvent", "StreamProgress", "StreamResult", "StreamError"} <= set(schemas)
    assert "HTTPValidationError" not in schemas
    r422 = spec["paths"]["/api/v1/watchlist/{item_id}"]["patch"]["responses"]["422"]
    assert r422["content"]["application/json"]["schema"]["$ref"] == "#/components/schemas/ErrorBody"


def test_committed_openapi_spec_is_up_to_date():
    """The TypeScript client is generated from this file: regenerate after API changes with
    `shopping-assistant api openapi`, then `npm run generate -w @shopping-assistant/api-client`."""
    assert DEFAULT_OPENAPI_PATH.exists(), "run: shopping-assistant api openapi"
    assert DEFAULT_OPENAPI_PATH.read_text(encoding="utf-8") == openapi_json(), "openapi.json is stale"
