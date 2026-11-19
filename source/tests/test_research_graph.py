"""Graph 1 tests with fake LLM + search (no network)."""

from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.checkpoint.memory import InMemorySaver

from shopping_assistant.graphs.research_graph import (
    LLMOutputError,
    build_research_graph,
    call_structured,
    render_comparison,
    resolve_choice,
)
from shopping_assistant.models import FollowUpAnswer, IntentDecision, ProductCandidate, ResearchComparison
from shopping_assistant.research import ResearchSession
from shopping_assistant.tools.search import SearchResult

# --- fakes ---------------------------------------------------------------------


class FakeLLM:
    """Returns queued objects per schema; records every call."""

    def __init__(self, *responses):
        self.queue = list(responses)
        self.calls: list[tuple[type, list]] = []
        self.kwargs: list[dict] = []

    def with_structured_output(self, schema, **kwargs):
        self.kwargs.append(kwargs)
        llm = self

        class Runnable:
            def invoke(self, messages):
                llm.calls.append((schema, messages))
                item = llm.queue.pop(0)
                if isinstance(item, Exception):
                    raise item
                if isinstance(item, dict):  # raw include_raw-style result
                    return item
                assert isinstance(item, schema), f"expected {schema.__name__}, got {type(item).__name__}"
                return {"parsed": item, "raw": AIMessage("", response_metadata={"stop_reason": "end_turn"}), "parsing_error": None}

        return Runnable()


class FakeSearch:
    def __init__(self, results=None, error=None):
        self.results = results if results is not None else [
            SearchResult(title="Best ANC headphones", url="https://www.rtings.com/headphones/best", content="Sony XM5 tops..."),
            SearchResult(title="Wirecutter picks", url="https://www.nytimes.com/wirecutter/x", content="Bose QC Ultra..."),
        ]
        self.error = error
        self.queries: list[str] = []

    def research_products(self, query, max_results=8):
        self.queries.append(query)
        if self.error:
            raise self.error
        return self.results


def candidate(name, brand, price):
    return ProductCandidate(
        name=name, brand=brand, estimated_price=price, rating_summary="Highly rated",
        key_specs=["ANC", "30h battery"], pros=["Great sound"], cons=["Pricey"], best_for="Travel",
    )


COMPARISON = ResearchComparison(
    candidates=[
        candidate("Sony WH-1000XM5", "Sony", 449.99),
        candidate("Bose QuietComfort Ultra", "Bose", 429.0),
        candidate("Sennheiser Momentum 4", "Sennheiser", 379.95),
    ],
    recommendation_summary="The Sony is the best all-rounder.",
    clarifying_question="Do you mostly use them on flights?",
    sources=["https://www.rtings.com/headphones/best"],
)


def explore(query):
    return IntentDecision(intent="explore_or_refine", search_query=query)


def run(graph, text, thread="t1"):
    return graph.invoke({"messages": [HumanMessage(text)]}, {"configurable": {"thread_id": thread}})


def make_graph(intent_llm, research_llm=None, search=None, checkpointer=None):
    return build_research_graph(
        intent_llm, research_llm or intent_llm, search or FakeSearch(), checkpointer or InMemorySaver()
    )


# --- US-01: researched comparison ---------------------------------------------


def test_explore_turn_produces_grounded_comparison():
    intent = FakeLLM(explore("noise cancelling headphones under CA$500"))
    research = FakeLLM(COMPARISON)
    search = FakeSearch()
    state = run(make_graph(intent, research, search), "I need noise cancelling headphones under $500")

    assert search.queries == ["noise cancelling headphones under CA$500"]
    assert state["last_action"] == "researched"
    assert len(state["last_comparison"]["candidates"]) == 3
    reply = state["messages"][-1].content
    assert "1. Sony WH-1000XM5 (Sony) - about CA$450" in reply
    assert "Do you mostly use them on flights?" in reply
    assert "rtings.com" in reply

    # The research prompt includes search results as data and the safety rule.
    _, messages = research.calls[0]
    assert isinstance(messages[0], SystemMessage) and "never purchase" in messages[0].content
    assert "<search_results>" in messages[-1].content and "rtings.com" in messages[-1].content


def test_structured_output_uses_json_schema_not_forced_tools():
    intent = FakeLLM(explore("q"))
    run(make_graph(intent, FakeLLM(COMPARISON)), "hi")
    assert intent.kwargs[0] == {"method": "json_schema", "include_raw": True}


def test_search_failure_gives_clear_error_and_conversation_continues():
    intent = FakeLLM(explore("headphones"), explore("headphones"))
    research = FakeLLM(COMPARISON)
    search = FakeSearch(error=ConnectionError("tavily down"))
    graph = make_graph(intent, research, search)

    state = run(graph, "headphones please")
    assert state["last_action"] == "error"
    assert "couldn't complete the research" in state["messages"][-1].content

    search.error = None  # retry works, history kept
    state = run(graph, "try again")
    assert state["last_action"] == "researched"
    assert len(state["messages"]) == 4


def test_no_search_results_asks_for_more_detail():
    state = run(make_graph(FakeLLM(explore("zzz")), search=FakeSearch(results=[])), "zzz")
    assert state["last_action"] == "asked"
    assert "couldn't find reviews" in state["messages"][-1].content


# --- US-02: refine over turns ---------------------------------------------------


def test_refinement_sends_history_and_combined_query():
    intent = FakeLLM(
        explore("noise cancelling headphones under CA$500"),
        explore("noise cancelling headphones under CA$500 for flights, long battery life"),
    )
    research = FakeLLM(COMPARISON, COMPARISON)
    search = FakeSearch()
    graph = make_graph(intent, research, search)
    run(graph, "noise cancelling headphones under $500")
    run(graph, "I mostly use them on flights, battery life matters most")

    assert search.queries[1] == "noise cancelling headphones under CA$500 for flights, long battery life"
    # The intent model saw the whole conversation plus the numbered options.
    _, messages = intent.calls[1]
    assert "1. Sony WH-1000XM5" in messages[0].content
    texts = [m.content for m in messages[1:]]
    assert texts[0] == "noise cancelling headphones under $500"
    assert texts[-1] == "I mostly use them on flights, battery life matters most"


# --- US-04: finalize ------------------------------------------------------------


def _graph_with_comparison(*decisions):
    intent = FakeLLM(explore("headphones"), *decisions)
    graph = make_graph(intent, FakeLLM(COMPARISON))
    run(graph, "headphones")
    return graph


def test_finalize_by_option_number():
    graph = _graph_with_comparison(
        IntentDecision(intent="finalize_product", candidate_number=2, search_query="headphones")
    )
    state = run(graph, "Option 2")
    assert state["last_action"] == "finalized"
    assert state["finalized_product"]["name"] == "Bose QuietComfort Ultra"
    assert "Great choice: Bose QuietComfort Ultra (about CA$429)" in state["messages"][-1].content


def test_finalize_by_name():
    graph = _graph_with_comparison(
        IntentDecision(intent="finalize_product", product_name="sony wh-1000xm5", search_query="headphones")
    )
    state = run(graph, "Let's go with the Sony WH-1000XM5")
    assert state["finalized_product"]["brand"] == "Sony"


def test_out_of_range_option_asks_instead_of_guessing():
    graph = _graph_with_comparison(
        IntentDecision(intent="finalize_product", candidate_number=7, search_query="headphones")
    )
    state = run(graph, "option 7")
    assert state["last_action"] == "asked"
    assert state.get("finalized_product") is None
    assert "number from 1 to 3" in state["messages"][-1].content


def test_ambiguous_choice_asks_to_confirm_without_searching():
    intent = FakeLLM(
        explore("headphones"),
        IntentDecision(intent="confirm_choice", search_query="headphones", clarification="Did you mean the Sony or the Bose?"),
    )
    search = FakeSearch()
    graph = make_graph(intent, FakeLLM(COMPARISON), search)
    run(graph, "headphones")
    state = run(graph, "that one")
    assert state["messages"][-1].content == "Did you mean the Sony or the Bose?"
    assert len(search.queries) == 1  # no new search


def test_question_about_option_does_not_finalize():
    graph = _graph_with_comparison(explore("Sony WH-1000XM5 battery life"))
    state = run(graph, "what about battery life on the Sony?")
    assert state["last_action"] != "finalized"


def test_followup_question_keeps_numbering_then_option_2_means_original_2():
    """Regression for the 2026-11-18 live run: a follow-up re-ranked the list."""
    followup = FollowUpAnswer(
        answer="Option 2, the Bose QuietComfort Ultra, is rated more comfortable for long wear than option 1.",
        sources=["https://www.tomsguide.com/x"],
    )
    intent = FakeLLM(
        explore("headphones"),
        IntentDecision(intent="ask_followup", search_query="Sony WH-1000XM5 vs Bose QuietComfort Ultra comfort"),
        IntentDecision(intent="finalize_product", candidate_number=2, search_query="headphones"),
    )
    search = FakeSearch()
    graph = make_graph(intent, FakeLLM(COMPARISON, followup), search)
    run(graph, "headphones")

    state = run(graph, "how does comfort compare between options 1 and 2?")
    assert state["last_action"] == "answered"
    assert state["last_comparison"] == COMPARISON.model_dump()  # list untouched
    reply = state["messages"][-1].content
    assert reply.startswith("Option 2, the Bose")
    assert "Your options are unchanged: 1. Sony WH-1000XM5  2. Bose QuietComfort Ultra" in reply
    assert search.queries[-1] == "Sony WH-1000XM5 vs Bose QuietComfort Ultra comfort"

    state = run(graph, "ok let's go with option 2")
    assert state["finalized_product"]["name"] == "Bose QuietComfort Ultra"


def test_followup_without_comparison_runs_research():
    intent = FakeLLM(IntentDecision(intent="ask_followup", search_query="is the Sony XM5 comfortable"))
    state = run(make_graph(intent, FakeLLM(COMPARISON)), "is the Sony XM5 comfortable?")
    assert state["last_action"] == "researched"


def test_followup_failure_keeps_list():
    intent = FakeLLM(explore("headphones"), IntentDecision(intent="ask_followup", search_query="comfort"))
    graph = make_graph(intent, FakeLLM(COMPARISON, LLMOutputError("refused")))
    run(graph, "headphones")
    state = run(graph, "which is comfier?")
    assert state["last_action"] == "error"
    assert len(state["last_comparison"]["candidates"]) == 3


def test_intent_failure_falls_back_to_research():
    intent = FakeLLM(LLMOutputError("refused"))
    search = FakeSearch()
    state = run(make_graph(intent, FakeLLM(COMPARISON), search), "budget laptop for school")
    assert search.queries == ["budget laptop for school"]
    assert state["last_action"] == "researched"


# --- helpers ------------------------------------------------------------------


@pytest.mark.parametrize(
    "number, name, expected",
    [
        (1, None, "Sony WH-1000XM5"),
        (3, None, "Sennheiser Momentum 4"),
        (0, None, None),
        (4, None, None),
        (None, "Bose QuietComfort Ultra", "Bose QuietComfort Ultra"),
        (None, "momentum 4", "Sennheiser Momentum 4"),
        (None, "Apple AirPods Max", "Apple AirPods Max"),  # named product outside the list
        (None, None, None),
    ],
)
def test_resolve_choice(number, name, expected):
    result = resolve_choice(COMPARISON.model_dump(), number, name)
    assert (result or {}).get("name") == expected


def test_call_structured_detects_refusal_and_parse_errors():
    refusal = {"parsed": None, "parsing_error": None, "raw": AIMessage("", response_metadata={"stop_reason": "refusal"})}
    with pytest.raises(LLMOutputError, match="declined"):
        call_structured(FakeLLM(refusal), IntentDecision, [])
    bad = {"parsed": None, "parsing_error": ValueError("bad json"), "raw": SimpleNamespace(response_metadata={})}
    with pytest.raises(LLMOutputError, match="Unexpected"):
        call_structured(FakeLLM(bad), IntentDecision, [])


def test_render_comparison_without_optional_parts():
    c = COMPARISON.model_copy(update={"clarifying_question": None, "sources": []})
    text = render_comparison(c)
    assert "Sources:" not in text and "Reply with an option number" in text


# --- US-03: resume via ResearchSession + SqliteSaver ---------------------------


def test_session_resumes_thread_across_restarts(settings_factory):
    settings = settings_factory()

    s1 = ResearchSession(settings, intent_llm=FakeLLM(explore("headphones")), research_llm=FakeLLM(COMPARISON), search=FakeSearch())
    thread = s1.new_thread_id()
    turn = s1.send(thread, "noise cancelling headphones")
    assert turn.comparison and turn.finalized_product is None
    s1.close()

    # New process: fresh session, same DB files.
    intent2 = FakeLLM(IntentDecision(intent="finalize_product", candidate_number=1, search_query="headphones"))
    s2 = ResearchSession(settings, intent_llm=intent2, research_llm=FakeLLM(), search=FakeSearch())
    threads = s2.list_threads()
    assert [t["thread_id"] for t in threads] == [thread]
    assert threads[0]["title"] == "noise cancelling headphones"
    assert [role for role, _ in s2.history(thread)] == ["user", "assistant"]

    turn = s2.send(thread, "option 1")
    assert turn.finalized_product["name"] == "Sony WH-1000XM5"
    assert s2.list_threads()[0]["finalized_product"] == "Sony WH-1000XM5"
    # The resumed intent call saw the earlier comparison.
    assert "1. Sony WH-1000XM5" in intent2.calls[0][1][0].content
    s2.close()


def test_session_rejects_empty_message(settings_factory):
    with ResearchSession(settings_factory(), intent_llm=FakeLLM(), research_llm=FakeLLM(), search=FakeSearch()) as s:
        with pytest.raises(ValueError):
            s.send(s.new_thread_id(), "   ")


def test_session_requires_anthropic_key(settings_factory):
    from shopping_assistant.config import ConfigError

    with pytest.raises(ConfigError, match="ANTHROPIC_API_KEY"):
        ResearchSession(settings_factory(anthropic_api_key=""), search=FakeSearch())
