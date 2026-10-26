"""Exercise the actual page script against a small DOM/API stub, without a model."""
from pathlib import Path
import shutil
import subprocess

import pytest


@pytest.mark.skipif(not shutil.which("node"), reason="Node.js required for page script checks")
def test_context_meter_and_full_reset_controls():
    project = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [shutil.which("node"), str(project / "tests/ui/challenge_b_controls.cjs"),
         str(project / "src/memory_agent/ui/challenge_b_chat.html")],
        capture_output=True, text=True, encoding="utf-8", timeout=15,
    )
    assert result.returncode == 0, result.stdout + result.stderr
