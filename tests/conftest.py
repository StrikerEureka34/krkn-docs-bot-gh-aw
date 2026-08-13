import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
os.environ.setdefault("OPENROUTER_API_KEY", "test-key-for-tests")
os.environ.setdefault("GITHUB_TOKEN", "test-token-for-tests")


@pytest.fixture(autouse=True)
def _no_live_model_calls(monkeypatch):
    """The base URL and model are built in, so a developer with LLM_API_KEY
    exported would otherwise have the suite call the real endpoint."""
    monkeypatch.delenv("LLM_API_KEY", raising=False)
