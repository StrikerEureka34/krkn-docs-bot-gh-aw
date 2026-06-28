import importlib
import json
import pytest
from unittest.mock import MagicMock, patch
import bot.llm_client as llm
from bot.llm_client import _extract_json, build_prompt, call_llm_with_retry


def test_base_url_and_model_come_from_env(monkeypatch):
    monkeypatch.setenv("LLM_BASE_URL", "https://example.test/v1")
    monkeypatch.setenv("LLM_MODEL", "vendor/some-model")
    monkeypatch.setenv("LLM_API_KEY", "k-123")
    importlib.reload(llm)
    assert llm.BASE_URL == "https://example.test/v1"
    assert llm.MODEL == "vendor/some-model"
    assert llm.API_KEY == "k-123"


def test_defaults_when_env_absent(monkeypatch):
    for v in ("LLM_BASE_URL", "LLM_MODEL", "LLM_API_KEY", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(v, raising=False)
    # SDK credential check requires a non-empty key at init time; dummy satisfies it.
    monkeypatch.setenv("OPENAI_API_KEY", "test-dummy-key")
    importlib.reload(llm)
    assert llm.BASE_URL == "https://openrouter.ai/api/v1"
    assert "nemotron" in llm.MODEL


def test_extract_json_plain_array():
    text = '[{"parameter": "FOO", "description": "bar", "type": "string", "default": ""}]'
    assert json.loads(_extract_json(text))[0]["parameter"] == "FOO"


def test_extract_json_strips_json_fence():
    text = '```json\n[{"parameter": "FOO"}]\n```'
    assert json.loads(_extract_json(text))[0]["parameter"] == "FOO"


def test_extract_json_strips_plain_fence():
    text = '```\n[{"parameter": "FOO"}]\n```'
    assert json.loads(_extract_json(text))[0]["parameter"] == "FOO"


def test_extract_json_finds_embedded_array():
    text = 'Here is the output: [{"parameter": "X"}] - end.'
    assert json.loads(_extract_json(text))[0]["parameter"] == "X"


def test_extract_json_returns_text_unchanged_if_no_bracket():
    text = "not json"
    assert _extract_json(text) == "not json"


def test_build_prompt_contains_variable_names():
    prompt = build_prompt("my-scenario", {"SERVICE_ACCOUNT": "", "RECOVERY_TIME": "0"})
    assert "SERVICE_ACCOUNT" in prompt
    assert "RECOVERY_TIME" in prompt


def test_build_prompt_contains_scenario_name():
    prompt = build_prompt("node-interface-down", {"FOO": "bar"})
    assert "node-interface-down" in prompt


def test_build_prompt_includes_pr_title_when_provided():
    prompt = build_prompt("s", {"V": "1"}, pr_title="feat: add new chaos param")
    assert "feat: add new chaos param" in prompt


def test_build_prompt_omits_pr_context_when_empty():
    prompt = build_prompt("s", {"V": "1"}, pr_title="")
    assert "PR context" not in prompt


def test_build_prompt_instructs_json_only():
    prompt = build_prompt("s", {"V": "1"})
    assert "ONLY valid JSON" in prompt


def test_call_llm_success_on_first_attempt():
    valid = '[{"parameter": "FOO", "description": "d", "type": "string", "default": ""}]'
    mock_resp = MagicMock()
    mock_resp.text = valid
    with patch("bot.llm_client.model") as mock_model:
        mock_model.generate_content.return_value = mock_resp
        result = call_llm_with_retry("test prompt")
    assert result[0]["parameter"] == "FOO"
    assert mock_model.generate_content.call_count == 1


def test_call_llm_retries_on_invalid_json():
    invalid = MagicMock(text="not json at all")
    valid = MagicMock(text='[{"parameter": "FOO", "description": "d", "type": "string", "default": ""}]')
    with patch("bot.llm_client.model") as mock_model, \
         patch("bot.llm_client.time.sleep"):
        mock_model.generate_content.side_effect = [invalid, valid]
        result = call_llm_with_retry("prompt", max_retries=3)
    assert result[0]["parameter"] == "FOO"
    assert mock_model.generate_content.call_count == 2


def test_call_llm_raises_after_max_retries():
    mock_resp = MagicMock(text="not json")
    with patch("bot.llm_client.model") as mock_model, \
         patch("bot.llm_client.time.sleep"):
        mock_model.generate_content.return_value = mock_resp
        with pytest.raises(RuntimeError, match="invalid JSON"):
            call_llm_with_retry("prompt", max_retries=2)


def test_call_llm_handles_fence_wrapped_on_retry():
    """Fenced JSON should succeed without needing a retry."""
    fenced = MagicMock(text='```json\n[{"parameter": "X", "description": "d", "type": "string", "default": ""}]\n```')
    with patch("bot.llm_client.model") as mock_model:
        mock_model.generate_content.return_value = fenced
        result = call_llm_with_retry("prompt")
    assert result[0]["parameter"] == "X"
