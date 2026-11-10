"""Execution mode cannot be switched to live."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from config.settings import Settings


@pytest.mark.parametrize("mode", ["LIVE", "LIVE_LOCKED", "LIVE_AUTHORIZED", " live "])
def test_live_modes_are_rejected(mode: str) -> None:
    with pytest.raises(ValidationError, match="Live execution modes are disabled"):
        Settings(_env_file=None, execution_mode=mode)
