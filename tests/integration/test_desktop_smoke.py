"""Offscreen launch of CYVORA Terminal."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_desktop_smoke_offscreen() -> None:
    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "offscreen"
    env.pop("GMGN_PRIVATE_KEY", None)
    result = subprocess.run(
        [sys.executable, "-m", "apps.desktop.main", "--smoke"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "CYVORA_DESKTOP_SMOKE_OK" in result.stdout
    assert "CYVORA_DESKTOP_SMOKE_FAIL" not in result.stdout
