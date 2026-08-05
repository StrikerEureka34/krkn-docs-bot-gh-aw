import pytest

from bot.describe import build_prompt, describe, validate

CTX = {"params": {"BLOCK_SIZE": {"line": "export BLOCK_SIZE=${BLOCK_SIZE:=512}"}}}


def reply(content):
    return lambda body: {"choices": [{"message": {"content": content}}]}


def boom(exc):
    def t(body):
        raise exc
    return t


def test_a_good_response_is_returned():
    t = reply('{"BLOCK_SIZE": "Size in bytes of each block written to the volume"}')
    assert describe("pvc-scenario", ["BLOCK_SIZE"], CTX, transport=t) == {
        "BLOCK_SIZE": "Size in bytes of each block written to the volume"}


def test_an_unreachable_endpoint_returns_nothing():
    """A blank cell is already legal and already reported, so one flaky endpoint
    must not fail the whole sync."""
    assert describe("s", ["X"], CTX, transport=boom(OSError("refused"))) == {}


def test_a_timeout_returns_nothing():
    assert describe("s", ["X"], CTX, transport=boom(TimeoutError())) == {}


def test_malformed_json_returns_nothing():
    assert describe("s", ["X"], CTX, transport=reply("here you go: not json")) == {}


def test_a_response_missing_the_choices_key_returns_nothing():
    assert describe("s", ["X"], CTX, transport=lambda b: {"error": "nope"}) == {}


def test_a_json_array_instead_of_an_object_returns_nothing():
    assert describe("s", ["X"], CTX, transport=reply('["not", "an object"]')) == {}


def test_a_name_that_was_not_asked_for_is_dropped():
    t = reply('{"X": "fine", "MADE_UP": "not asked for"}')
    assert set(describe("s", ["X"], CTX, transport=t)) == {"X"}


def test_an_empty_string_is_dropped_rather_than_stored():
    assert describe("s", ["X"], CTX, transport=reply('{"X": "   "}')) == {}


def test_no_names_makes_no_call():
    assert describe("s", [], CTX, transport=boom(AssertionError("called"))) == {}


def test_no_credentials_makes_no_call(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert describe("s", ["X"], CTX) == {}


def test_the_prompt_carries_the_source_line_and_voice_examples():
    ctx = dict(CTX, examples=[("PORT", "Port to publish kraken status to")],
               readme="Fills a PVC.")
    p = build_prompt("pvc-scenario", ["BLOCK_SIZE"], ctx)
    assert "export BLOCK_SIZE=${BLOCK_SIZE:=512}" in p
    assert "Port to publish kraken status to" in p
    assert "Fills a PVC." in p


@pytest.mark.parametrize("text,reason", [
    ("", "no description produced"),
    ("one\ntwo", "rejected: contains a newline"),
    ("x" * 121, "rejected: too long (121 > 120)"),
    ("Configures port.", "rejected: says nothing"),
])
def test_rejections(text, reason):
    assert validate(text, {"name": "PORT"}) == reason


def test_text_that_invents_a_value_is_rejected():
    """A model that writes 1024 when the source says 512 reads as authoritative
    and is wrong, which is worse than an empty cell."""
    assert validate("Block size, default 1024", {"name": "B", "default": "512"}) == \
        'rejected: contains a value not in the source ("1024")'


def test_a_value_that_is_in_the_source_is_accepted():
    assert validate("Block size in bytes, defaults to 512",
                    {"name": "B", "default": "512"}) is None


def test_the_real_model_output_for_retry_wait_passes():
    """What gpt-4o-mini actually returned for globals/RETRY_WAIT."""
    assert validate("Time to wait before retrying an operation.",
                    {"name": "RETRY_WAIT", "default": "120"}) is None
