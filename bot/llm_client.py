import re
import json
import time
import os
import urllib.request
import urllib.error

BASE_URL = os.environ.get("LLM_BASE_URL", "https://openrouter.ai/api/v1")
MODEL    = os.environ.get("LLM_MODEL", "nvidia/nemotron-3-nano-30b-a3b:free")
API_KEY  = os.environ.get("LLM_API_KEY") or os.environ.get("OPENROUTER_API_KEY") or os.environ.get("GITHUB_TOKEN", "")


class RateLimited(Exception):
    def __init__(self, retry_after: int):
        self.retry_after = retry_after


class _Response:
    def __init__(self, text: str):
        self.text = text


class _Model:
    """Thin shim so tests can patch `bot.llm_client.model` unchanged."""
    def generate_content(self, prompt: str) -> _Response:
        body = json.dumps({
            "model": MODEL,
            "messages": [{"role": "user", "content": prompt}],
        }).encode()
        req = urllib.request.Request(
            f"{BASE_URL}/chat/completions",
            data=body,
            headers={
                "Authorization": f"Bearer {API_KEY}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req) as resp:
                data = json.load(resp)
        except urllib.error.HTTPError as e:
            if e.code == 429:
                raise RateLimited(int(e.headers.get("Retry-After", 35)) + 5)
            raise
        return _Response(data["choices"][0]["message"]["content"] or "")


model = _Model()


def _extract_json(text: str) -> str:
    """Strip markdown fences then find the outermost JSON array."""
    text = text.strip()
    text = re.sub(r'^```(?:json)?\s*', '', text)
    text = re.sub(r'\s*```$', '', text)
    start, end = text.find('['), text.rfind(']') + 1
    return text[start:end] if start != -1 else text


def build_prompt(scenario: str, params: dict[str, str], pr_title: str = "") -> str:
    vars_text = "\n".join(f"{k}={v}" for k, v in params.items())
    context = f"\nPR context: {pr_title}" if pr_title else ""
    return (
        f"You are a technical writer for krkn-chaos, a Kubernetes chaos engineering tool.\n"
        f"Given these bash environment variables from the '{scenario}' chaos scenario,\n"
        f"generate a JSON array describing each parameter for end-user documentation.\n\n"
        f"Variables (user-configurable name=default):\n{vars_text}{context}\n\n"
        f"Return ONLY valid JSON. No markdown fences, no explanation, no prose.\n"
        f'Schema: [{{"parameter": "VAR_NAME", "description": "one sentence", '
        f'"type": "string|int|bool", "default": "value"}}]'
    )


def call_llm_with_retry(prompt: str, max_retries: int = 3) -> list[dict]:
    for attempt in range(max_retries):
        try:
            response = model.generate_content(prompt)
            return json.loads(_extract_json(response.text))
        except (ValueError, json.JSONDecodeError) as e:
            if attempt == max_retries - 1:
                raise RuntimeError(
                    f"LLM returned invalid JSON after {max_retries} attempts: {e}"
                )
            time.sleep(2 ** attempt)
        except RateLimited as e:
            if attempt < max_retries - 1:
                time.sleep(e.retry_after)
            else:
                return []
    return []
