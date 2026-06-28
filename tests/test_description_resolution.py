from bot.parser import ParamRecord
from bot.descriptions import resolve_descriptions


def fake_llm(scenario, names):
    return {n: f"LLM desc for {n}." for n in names}


def test_existing_wins_then_source_then_llm():
    recs = [
        ParamRecord(name="KEEP"),
        ParamRecord(name="SRC", description="from src"),
        ParamRecord(name="NEW"),
    ]
    existing = {"KEEP": "human edited"}
    out, called = resolve_descriptions("scn", recs, existing, fake_llm)
    assert out["KEEP"] == "human edited"
    assert out["SRC"] == "from src"
    assert out["NEW"] == "LLM desc for NEW."
    assert called == ["NEW"]


def test_no_llm_call_when_all_resolved():
    recs = [ParamRecord(name="A", description="d")]
    out, called = resolve_descriptions("scn", recs, {}, fake_llm)
    assert called == []
