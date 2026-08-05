"""Descriptions for params no source and no published page describes.
Python calls the model and writes the result, so nothing untrusted edits a file."""
import json
import os
import re
import urllib.request

MAX_LEN = 120
_TIMEOUT = 30
_NUMBER_OR_QUOTED = re.compile(r'"[^"]+"|\b\d+\b')
_PLACEHOLDER = re.compile(r'^(configures?|sets?|specifies|controls?) (the )?\w+\.?$', re.I)

_SYSTEM = (
    "Write one plain sentence describing each parameter, for a documentation "
    "table. One sentence, at most 120 characters, no markdown. Describe only what "
    "the context states. Never state a default, range or unit that is not in that "
    "parameter's own record. If unsure, return an empty string for that parameter. "
    "Match the voice of the examples. Return JSON only: an object mapping each "
    "parameter name to its sentence."
)


def validate(text, record):
    """None if the text is usable, otherwise the reason it is not. The literal
    check is the important one: a confident wrong default is worse than a blank."""
    text = (text or "").strip()
    if not text:
        return "no description produced"
    if "\n" in text:
        return "rejected: contains a newline"
    if len(text) > MAX_LEN:
        return f"rejected: too long ({len(text)} > {MAX_LEN})"
    if _PLACEHOLDER.match(text):
        return "rejected: says nothing"
    # Substring, so "12" passes against a default of "120". Harmless: the point
    # is catching an invented value, not a narrower one.
    known = " ".join(str(v) for v in record.values() if v is not None)
    for lit in _NUMBER_OR_QUOTED.findall(text):
        if lit.strip('"') not in known:
            return f'rejected: contains a value not in the source ("{lit.strip(chr(34))}")'
    return None


def build_prompt(scenario, names, ctx):
    """The user message. Assembled the same way every run so the call is as
    reproducible as the model allows."""
    out = [f"Scenario: {scenario}", ""]
    if ctx.get("readme"):
        out += ["Overview:", ctx["readme"], ""]
    out.append("Parameters to describe:")
    for n in names:
        p = (ctx.get("params") or {}).get(n, {})
        out.append(f"- {n}")
        for label in ("line", "type", "allowed", "required"):
            if p.get(label):
                out.append(f"    {label}: {p[label]}")
    if ctx.get("examples"):
        out += ["", "Examples from the same scenario, for voice:"]
        out += [f"- {n}: {d}" for n, d in ctx["examples"]]
    return "\n".join(out)


def _post(url, key, body):
    req = urllib.request.Request(
        url, data=json.dumps(body).encode("utf-8"), method="POST",
        headers={"Authorization": f"Bearer {key}",
                 "Content-Type": "application/json",
                 # Copilot rejects the call without these; other OpenAI-compatible
                 # endpoints ignore them, so switching stays two env vars.
                 "Copilot-Integration-Id": "vscode-chat",
                 "Editor-Version": "krkn-docs-bot/1.0"})
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
        return json.loads(r.read())


def describe(scenario, names, ctx, transport=None):
    """{name: sentence} for the names that produced text.

    Returns {} on any failure: non-200, malformed JSON, timeout, unreachable
    endpoint, missing credentials. A blank cell is already legal and already
    reported, so a failed call never fails the run."""
    if not names:
        return {}
    base = os.environ.get("OPENAI_BASE_URL", "https://api.githubcopilot.com")
    key = os.environ.get("OPENAI_API_KEY")
    if transport is None:
        if not key:
            return {}
        url = base.rstrip("/") + "/chat/completions"
        transport = lambda body: _post(url, key, body)  # noqa: E731
    body = {"model": os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": _SYSTEM},
                         {"role": "user",
                          "content": build_prompt(scenario, names, ctx)}]}
    try:
        raw = json.loads(transport(body)["choices"][0]["message"]["content"])
    except Exception:
        return {}
    if not isinstance(raw, dict):
        return {}
    return {n: raw[n].strip() for n in names
            if isinstance(raw.get(n), str) and raw[n].strip()}
