"""Local daily data import uses the same validation for preview and commit."""
from __future__ import annotations

import base64
import sqlite3

import pytest

from server.services import data_sync_import as svc


def _payload(csv_text: str, **overrides):
    payload = {
        "name": "daily.csv", "data_type": "daily", "mode": "missing",
        "content_base64": base64.b64encode(csv_text.encode("utf-8-sig")).decode("ascii"),
    }
    payload.update(overrides)
    return payload


def test_preview_validates_without_writing_and_commit_respects_existing_rows(tmp_path, monkeypatch):
    database = tmp_path / "market.db"
    monkeypatch.setattr(svc, "DB_PATH", database)
    first = _payload("symbol,date,open,high,low,close,volume\n600519,2026-09-30,100,110,99,105,1000\n")
    preview = svc.preview_import(first)
    assert preview["ready"] is True and preview["valid_count"] == 1
    assert not database.exists()

    committed = svc.commit_import(first)
    assert committed["imported_count"] == 1 and committed["skipped_count"] == 0
    with sqlite3.connect(database) as conn:
        saved = conn.execute("SELECT close FROM daily_kline WHERE symbol = ?", ("sh600519",)).fetchone()
    assert saved == (105.0,)

    changed = _payload("symbol,date,open,high,low,close,volume\n600519,2026-09-30,100,110,99,108,1000\n")
    skipped = svc.commit_import(changed)
    assert skipped["imported_count"] == 0 and skipped["skipped_count"] == 1
    overwritten = svc.commit_import({**changed, "mode": "overwrite"})
    assert overwritten["imported_count"] == 1
    with sqlite3.connect(database) as conn:
        assert conn.execute("SELECT close FROM daily_kline WHERE symbol = ?", ("sh600519",)).fetchone() == (108.0,)


def test_invalid_rows_block_commit_and_unsupported_type_is_explicit(tmp_path, monkeypatch):
    database = tmp_path / "market.db"
    monkeypatch.setattr(svc, "DB_PATH", database)
    invalid = _payload("symbol,date,open,high,low,close,volume\n600519,2026-09-30,100,90,99,105,1000\n")
    preview = svc.preview_import(invalid)
    assert preview["ready"] is False and preview["error_count"] == 1
    with pytest.raises(ValueError, match="无效记录"):
        svc.commit_import(invalid)
    assert not database.exists()

    with pytest.raises(ValueError, match="仅支持日线"):
        svc.preview_import(_payload("symbol,date\n600519,2026-09-30\n", data_type="minute"))
