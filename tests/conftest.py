import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
os.environ.setdefault("OPENROUTER_API_KEY", "test-key-for-tests")
os.environ.setdefault("GITHUB_TOKEN", "test-token-for-tests")


@pytest.fixture(autouse=True)
def _no_live_model_calls(monkeypatch):
    """describe() falls back to the real endpoint when a key is present, so a
    developer with OPENAI_API_KEY set would otherwise have the suite call out."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
