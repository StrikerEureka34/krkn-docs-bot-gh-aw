import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
os.environ.setdefault("OPENROUTER_API_KEY", "test-key-for-tests")
os.environ.setdefault("GITHUB_TOKEN", "test-token-for-tests")
