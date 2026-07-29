from bot.parser import ParamRecord
from bot.descriptions import resolve_descriptions


def fake_llm(scenario, names):
    return {n: f"LLM desc for {n}." for n in names}


def test_source_wins_over_the_committed_file():
    """THE regression this file exists for.

    The old order was existing -> source, which froze descriptions at first
    generation: improving the wording upstream changed nothing, because the
    committed data file always won. That makes a generated artifact
    authoritative over its own source, which defeats the point of a sync bot.
    """
    recs = [ParamRecord(name="P", description="improved upstream wording")]
    existing = {"P": "whatever was generated last time"}
    out, _ = resolve_descriptions("scn", recs, existing, fake_llm)
    assert out["P"] == "improved upstream wording"


def test_existing_is_the_fallback_when_the_source_says_nothing():
    """Six global params have no description in either source. A value already in
    the file is better than nothing, so it still fills the gap."""
    recs = [ParamRecord(name="PORT")]
    out, called = resolve_descriptions("scn", recs, {"PORT": "kept"}, fake_llm)
    assert out["PORT"] == "kept"
    assert called == []


def test_llm_only_for_params_nothing_describes():
    recs = [ParamRecord(name="SRC", description="from src"),
            ParamRecord(name="NEW")]
    out, called = resolve_descriptions("scn", recs, {}, fake_llm)
    assert out["SRC"] == "from src"
    assert out["NEW"] == "LLM desc for NEW."
    assert called == ["NEW"]


def test_no_llm_call_when_all_resolved():
    recs = [ParamRecord(name="A", description="d")]
    out, called = resolve_descriptions("scn", recs, {}, fake_llm)
    assert called == []


def test_an_undescribed_param_is_left_blank_not_papered_over():
    """The old fallback wrote "Configures port." which reads as finished and says
    nothing, hiding the gap. An empty cell shows a human there is work to do."""
    recs = [ParamRecord(name="PORT")]
    out, called = resolve_descriptions("scn", recs, {}, lambda s, n: {})
    assert out["PORT"] == ""
    assert called == ["PORT"]
