"""Logging writes records and does not need a secret to do so."""

from __future__ import annotations

from pathlib import Path

from config.settings import Settings
from monitoring.logging import configure_logging


def test_log_file_receives_records(tmp_path: Path) -> None:
    settings = Settings(_env_file=None, log_dir=tmp_path, log_level="INFO")
    logger = configure_logging(settings)
    logger.info("foundation ready")
    text = (tmp_path / "cyvora.log").read_text(encoding="utf-8")
    assert "foundation ready" in text
    assert "INFO" in text
