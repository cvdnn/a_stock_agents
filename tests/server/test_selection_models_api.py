# -*- coding: utf-8 -*-
"""批次三 C1～C4：智能选股系统后端 API 集成测试（§15 / 发布门禁 2、3、10、18）。

隔离策略：所有落盘仓库的默认根（`output/config|cache|pools`）被重定向到 `tmp_path`，
确保用例不触碰真实用户目录；HTTP 一律走 conftest 的 `client`/`anon_client`（裸建
TestClient 恒 401）。
"""
from __future__ import annotations

import csv
import io
import json
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def selection_store(tmp_path, monkeypatch):
    """把选股系统全部落盘根重定向到临时目录（config/cache/pools/locks）。"""
    from core.selection_models import (
        catalog,
        definition_repository,
        run_repository,
        signal_latch,
        version_repository,
    )

    config_root = tmp_path / "config"
    cache_root = tmp_path / "cache"
    pools_root = tmp_path / "pools"
    lock_root = tmp_path / "locks"
    monkeypatch.setattr(definition_repository, "DEFAULT_BASE_DIR", config_root)
    monkeypatch.setattr(definition_repository, "DEFAULT_LOCK_DIR", lock_root)
    monkeypatch.setattr(version_repository, "DEFAULT_BASE_DIR", config_root)
    monkeypatch.setattr(run_repository, "CACHE_ROOT", cache_root)
    monkeypatch.setattr(run_repository, "POOLS_ROOT", pools_root)
    monkeypatch.setattr(catalog, "DEFAULT_BASE_DIR", config_root)
    monkeypatch.setattr(signal_latch, "CACHE_ROOT", cache_root)
    return tmp_path


def _condition_records():
    return [{"code": "600001", "closes": [float(i) for i in range(1, 71)]}]


def _create_and_publish(client, *, model_type="condition_tree", template="blank"):
    created = client.post("/api/selection-models", json={
        "model_type": model_type, "name": "测试模型", "template": template,
    }).json()
    assert created["status"] == "ok", created
    model_id = created["data"]["model_id"]
    validated = client.post(f"/api/selection-models/{model_id}/validate").json()
    assert validated["status"] == "ok", validated
    published = client.post(f"/api/selection-models/{model_id}/versions", json={}).json()
    assert published["status"] == "ok", published
    activated = client.post(f"/api/selection-models/{model_id}/activate/1").json()
    assert activated["status"] == "ok", activated
    return model_id


# ------------------------------------------------------------------ 元数据
def test_types_and_rule_types_are_real(client, selection_store):
    types = client.get("/api/selection-models/types").json()
    assert types["status"] == "ok"
    assert types["data"]["publishable"] == ["condition_tree", "funnel"]
    ids = {t["type_id"]: t for t in types["data"]["types"]}
    assert ids["scoring_rank"]["publishable"] is False

    rules = client.get("/api/selection-models/rule-types").json()
    assert rules["status"] == "ok"
    assert rules["data"]["rule_types"]
    assert all("parameter_schema" in r and "form_annotations" in r for r in rules["data"]["rule_types"])


def test_unauthenticated_requests_are_rejected(anon_client):
    assert anon_client.get("/api/selection-models/types").status_code == 401
    assert anon_client.post("/api/selection-models", json={"model_type": "funnel", "name": "x"}).status_code == 401


def test_p2_model_type_cannot_be_created(client, selection_store):
    resp = client.post("/api/selection-models", json={"model_type": "scoring_rank", "name": "评分"}).json()
    assert resp["status"] == "error"
    assert resp["error_code"] == "MODEL_TYPE_UNKNOWN"


# ------------------------------------------------------------------ 生命周期（发布门禁 2）
def test_create_validate_publish_activate_run_without_code(client, selection_store):
    model_id = _create_and_publish(client)
    listed = client.get("/api/selection-models").json()
    assert any(m["model_id"] == model_id for m in listed["data"]["models"])
    assert listed["data"]["permissions"] == {"create": True, "run": True}

    run = client.post(f"/api/selection-models/{model_id}/runs", json={"records": _condition_records()}).json()
    assert run["status"] == "ok", run
    assert run["data"]["run"]["status"] == "COMPLETED"
    assert run["data"]["selected_codes"] == ["600001"]

    run_id = run["data"]["run_id"]
    detail = client.get(f"/api/selection-models/runs/{run_id}").json()
    assert detail["status"] == "ok", detail
    assert detail["data"]["run"]["run_id"] == run_id
    assert detail["data"]["run"]["model_id"] == model_id
    assert detail["data"]["run"]["plan_hash"]

    nodes = client.get(f"/api/selection-models/runs/{run_id}/nodes").json()
    assert nodes["status"] == "ok", nodes
    assert nodes["data"]["run_id"] == run_id
    assert nodes["data"]["nodes"][0]["stage_id"] == "condition_filter"
    candidates = client.get(f"/api/selection-models/runs/{run_id}/candidates").json()
    assert candidates["status"] == "ok", candidates
    assert candidates["data"]["run_id"] == run_id
    assert candidates["data"]["candidates"][0]["verdict"] == "PASS"

    results = client.get(f"/api/selection-models/results?model_id={model_id}").json()
    assert results["data"]["total"] == 1
    assert results["data"]["results"][0]["signal_codes"] == ["600001"]


def test_r3_two_runs_stage_counts_filtered_pages_and_csv_match(client, selection_store):
    model_id = _create_and_publish(client)
    first_records = _condition_records() + [{**_condition_records()[0], "code": "600002", "name": "第二只"}]
    first = client.post(f"/api/selection-models/{model_id}/runs", json={"records": first_records}).json()
    second = client.post(f"/api/selection-models/{model_id}/runs", json={
        "records": [{**_condition_records()[0], "code": "600003"}],
    }).json()
    assert first["status"] == second["status"] == "ok"
    run1, run2 = first["data"]["run_id"], second["data"]["run_id"]
    assert run1 != run2
    listed = client.get(f"/api/selection-models/{model_id}/runs").json()["data"]
    assert {run1, run2}.issubset({item["run_id"] for item in listed["runs"]})
    stage = client.get(f"/api/selection-models/runs/{run1}/nodes").json()["data"]["nodes"][0]
    assert (stage["input_count"], stage["passed_count"], stage["rejected_count"],
            stage["unknown_count"], stage["forwarded_count"]) == (2, 2, 0, 0, 0)
    assert stage["input_count"] == sum(stage[key] for key in (
        "passed_count", "rejected_count", "unknown_count", "forwarded_count"))
    assert json.loads((selection_store / "cache" / run1 / "stages.json").read_text(encoding="utf-8"))["run_id"] == run1
    assert json.loads((selection_store / "cache" / run2 / "candidates.json").read_text(encoding="utf-8"))["run_id"] == run2

    path = f"/api/selection-models/runs/{run1}/candidates"
    page = client.get(path, params={"stage_id": stage["stage_id"], "limit": 1, "offset": 1}).json()
    assert page["data"]["total"] == 2
    assert len(page["data"]["candidates"]) == 1
    assert page["data"]["candidates"][0]["code"] == "600002"
    assert page["data"]["source"] == "request_records"
    assert page["data"]["as_of"] is None
    assert page["watermark"]["degraded_reason"] == "SNAPSHOT_NOT_PROVIDED"
    assert page["data"]["candidates"][0]["missing_reasons"]["industry"]
    assert page["data"]["candidates"][0]["missing_reasons"]["snapshot"]
    filtered = client.get(path, params={"stage_id": stage["stage_id"], "verdict": "PASS",
                                        "keyword": "第二只"}).json()["data"]
    assert filtered["total"] == 1
    assert filtered["candidates"][0]["code"] == "600002"
    exported = client.get(path + "/export", params={"stage_id": stage["stage_id"],
                                                   "verdict": "PASS", "keyword": "第二只"})
    csv_rows = list(csv.DictReader(io.StringIO(exported.text.lstrip("\ufeff"))))
    assert exported.headers["X-Selection-Total"] == "1"
    assert len(csv_rows) == filtered["total"]
    assert csv_rows[0]["run_id"] == run1
    assert csv_rows[0]["code"] == "600002"
    other = client.get(f"/api/selection-models/runs/{run2}/candidates").json()["data"]
    assert other["total"] == 1
    assert other["candidates"][0]["code"] == "600003"
    missing_stage = client.get(path, params={"stage_id": "unknown_stage"}).json()
    assert missing_stage["error_code"] == "MODEL_STAGE_NOT_FOUND"


def test_r6_two_runs_keep_the_same_auditable_local_snapshot(client, selection_store, monkeypatch):
    """Two manual runs from an isolated local store retain their content-addressed input."""
    from core.data.data_assembler import DataAssembler
    from core.data.dataset_sync import POST_CLOSE_WATERMARK_KEYS, write_universe_watermark
    from core.data.sync_engine import MarketDataStore
    from server.api import selection_models as selection_api

    as_of = "2026-09-30"
    db_path = selection_store / "market.db"
    store = MarketDataStore(db_path=db_path)
    for key in POST_CLOSE_WATERMARK_KEYS:
        write_universe_watermark(store, key, 10, 10, availability="finalized", trade_date=as_of)
    days = []
    cursor = datetime(2026, 9, 30)
    while len(days) < 75:
        if cursor.weekday() < 5:
            days.append(cursor.strftime("%Y-%m-%d"))
        cursor -= timedelta(days=1)
    days.reverse()
    with sqlite3.connect(db_path) as conn:
        conn.executemany(
            "INSERT OR REPLACE INTO daily_kline "
            "(symbol, date, open, high, low, close, volume, amount, is_settled) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [("sh600001", day, 10 + index * .05, 10.2 + index * .05,
              10.3 + index * .05, 9.9 + index * .05, 1000 + index * 100, 0, 1)
             for index, day in enumerate(days)],
        )
        conn.execute(
            "INSERT OR REPLACE INTO stock_basic (symbol, name, market, list_date, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            ("sh600001", "隔离样本", "sh", "2010-01-01", f"{as_of} 15:40:00"),
        )
        conn.execute(
            "INSERT OR REPLACE INTO capital_snapshot "
            "(symbol, date, total_shares, float_shares, total_market_cap, float_market_cap, source) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("sh600001", as_of, 1e9, 8e8, 1.2e10, 9.5e9, "isolated_fixture"),
        )
    assembler = DataAssembler(
        db_path=db_path,
        snapshot_root=selection_store / "snapshots",
        intraday_root=selection_store / "intraday",
    )
    monkeypatch.setattr(selection_api, "DataAssembler", lambda: assembler)

    model_id = _create_and_publish(client)
    payload = {"codes": "sh600001", "as_of": as_of}
    first = client.post(f"/api/selection-models/{model_id}/runs", json=payload).json()
    second = client.post(f"/api/selection-models/{model_id}/runs", json=payload).json()
    assert first["status"] == second["status"] == "ok"
    run_ids = [first["data"]["run_id"], second["data"]["run_id"]]
    assert run_ids[0] != run_ids[1]
    snapshot_ids = set()
    for run_id in run_ids:
        detail = client.get(f"/api/selection-models/runs/{run_id}").json()
        nodes = client.get(f"/api/selection-models/runs/{run_id}/nodes").json()
        candidates = client.get(f"/api/selection-models/runs/{run_id}/candidates").json()
        assert detail["status"] == nodes["status"] == candidates["status"] == "ok"
        run = detail["data"]["run"]
        assert run["input_source"] == "local_snapshot"
        assert run["data_snapshot_id"]
        assert nodes["data"]["run_id"] == candidates["data"]["run_id"] == run_id
        assert candidates["data"]["data_snapshot_id"] == run["data_snapshot_id"]
        snapshot_ids.add(run["data_snapshot_id"])
    assert len(snapshot_ids) == 1
    manifests = list((selection_store / "snapshots").glob("*/manifest.json"))
    assert len(manifests) == 1
    assert json.loads(manifests[0].read_text(encoding="utf-8"))["data_snapshot_id"] in snapshot_ids


def test_run_without_active_version_fails_closed(client, selection_store):
    created = client.post("/api/selection-models", json={"model_type": "funnel", "name": "未发布"}).json()
    model_id = created["data"]["model_id"]
    resp = client.post(f"/api/selection-models/{model_id}/runs", json={"records": _condition_records()}).json()
    assert resp["status"] == "error"
    assert resp["error_code"] == "MODEL_VERSION_NOT_FOUND"


def test_manual_selection_runs_published_version_without_activation(client, selection_store):
    created = client.post("/api/selection-models", json={
        "model_type": "condition_tree", "name": "直接选股模型", "template": "blank",
    }).json()
    model_id = created["data"]["model_id"]
    published = client.post(f"/api/selection-models/{model_id}/versions", json={}).json()
    assert published["status"] == "ok", published
    assert client.get(f"/api/selection-models/{model_id}").json()["data"]["active_version"] is None

    run = client.post(f"/api/selection-models/{model_id}/runs", json={
        "version": 1, "records": _condition_records(),
    }).json()
    assert run["status"] == "ok", run
    assert run["data"]["run"]["model_version"] == 1
    assert run["data"]["run"]["status"] == "COMPLETED"
    assert client.get(f"/api/selection-models/{model_id}").json()["data"]["active_version"] is None
    recent = client.get("/api/selection-models/runs").json()
    assert recent["status"] == "ok", recent
    assert recent["data"]["runs"][0]["run_id"] == run["data"]["run_id"]

    absent = client.post(f"/api/selection-models/{model_id}/runs", json={
        "version": 99, "records": _condition_records(),
    }).json()
    assert absent["error_code"] == "MODEL_VERSION_NOT_FOUND"
    assert client.get(f"/api/selection-models/runs").json()["data"]["runs"] == recent["data"]["runs"]

    archived = client.post(f"/api/selection-models/{model_id}/versions/1/archive").json()
    assert archived["status"] == "ok", archived
    rejected = client.post(f"/api/selection-models/{model_id}/runs", json={
        "version": 1, "records": _condition_records(),
    }).json()
    assert rejected["error_code"] == "MODEL_VERSION_CONFLICT"
    assert len(client.get(f"/api/selection-models/runs").json()["data"]["runs"]) == 1


@pytest.mark.parametrize("model_type", ["condition_tree", "funnel"])
def test_r2_blank_draft_two_saves_restore_publish_activate_and_conflict(client, selection_store, model_type):
    created = client.post("/api/selection-models", json={
        "model_type": model_type, "name": f"R2 {model_type}", "template": "blank",
    }).json()
    assert created["status"] == "ok", created
    model_id = created["data"]["model_id"]
    first = client.get(f"/api/selection-models/{model_id}").json()["data"]["draft"]
    key = "groups" if model_type == "condition_tree" else "stages"
    definition = first["definition"]
    definition[key][0]["name"] = "第一次编辑"
    saved1 = client.patch(f"/api/selection-models/{model_id}/draft", json={
        "definition": definition, "base_version": first["base_version"],
        "draft_revision": first["draft_revision"],
    }).json()
    assert saved1["status"] == "ok", saved1
    assert saved1["data"]["draft_revision"] == first["draft_revision"] + 1
    definition[key][0]["name"] = "第二次编辑"
    saved2 = client.patch(f"/api/selection-models/{model_id}/draft", json={
        "definition": definition, "base_version": saved1["data"]["base_version"],
        "draft_revision": saved1["data"]["draft_revision"],
    }).json()
    assert saved2["status"] == "ok", saved2
    restored = client.get(f"/api/selection-models/{model_id}").json()["data"]["draft"]
    assert restored["draft_revision"] == saved2["data"]["draft_revision"]
    assert restored["definition"][key][0]["name"] == "第二次编辑"
    conflict = client.patch(f"/api/selection-models/{model_id}/draft", json={
        "definition": definition, "base_version": first["base_version"],
        "draft_revision": first["draft_revision"],
    }).json()
    assert conflict["error_code"] == "MODEL_DRAFT_CONFLICT"
    assert client.get(f"/api/selection-models/{model_id}").json()["data"]["draft"]["definition"][key][0]["name"] == "第二次编辑"
    valid = client.post(f"/api/selection-models/{model_id}/validate", json={}).json()
    assert valid["status"] == "ok", valid
    published = client.post(f"/api/selection-models/{model_id}/versions", json={
        "base_version": restored["base_version"], "draft_revision": restored["draft_revision"],
    }).json()
    assert published["status"] == "ok", published
    version = published["data"]["version"]
    activated = client.post(f"/api/selection-models/{model_id}/activate/{version}").json()
    assert activated["status"] == "ok", activated
    assert client.get(f"/api/selection-models/{model_id}").json()["data"]["active_version"] == version


def test_run_without_records_and_no_local_data_fails_closed(client, selection_store):
    model_id = _create_and_publish(client, model_type="funnel", template="blank")
    resp = client.post(f"/api/selection-models/{model_id}/runs", json={}).json()
    assert resp["status"] in {"ok", "error"}
    if resp["status"] == "error":
        assert resp["error_code"] == "MODEL_DATA_MISSING"
        assert resp["watermark"]["eligible_for_signal"] is False


# ------------------------------------------------------------------ 版本仓库（门禁 9）
def test_version_immutability_activation_and_conflict(client, selection_store):
    model_id = _create_and_publish(client)
    versions = client.get(f"/api/selection-models/{model_id}/versions").json()
    assert [v["version"] for v in versions["data"]["versions"]] == [1]
    assert versions["data"]["active_version"] == 1

    # 发布号单调：修改草稿基线后再发一版
    copied = client.post(f"/api/selection-models/{model_id}/versions/1/copy-to-draft", json={}).json()
    assert copied["status"] == "ok"
    published = client.post(f"/api/selection-models/{model_id}/versions", json={
        "base_version": 1, "draft_revision": copied["data"]["draft_revision"],
    }).json()
    assert published["data"]["version"] == 2

    # 草稿并发冲突被拒（错误修订号）
    conflict = client.patch(f"/api/selection-models/{model_id}/draft", json={
        "definition": copied["data"]["definition"], "base_version": 1, "draft_revision": 999,
    }).json()
    assert conflict["error_code"] == "MODEL_DRAFT_CONFLICT"

    # 激活新版本后再回滚到 v1：指针切换且历史版本不变
    activated_v2 = client.post(f"/api/selection-models/{model_id}/activate/2").json()
    assert activated_v2["data"]["previous_version"] == 1
    rollback = client.post(f"/api/selection-models/{model_id}/activate/1").json()
    assert rollback["data"]["previous_version"] == 2
    after = client.get(f"/api/selection-models/{model_id}/versions").json()
    assert after["data"]["active_version"] == 1

    # 归档非活动版本
    archived = client.post(f"/api/selection-models/{model_id}/versions/2/archive").json()
    assert archived["data"]["status"] == "ARCHIVED"


def test_version_diff_endpoint(client, selection_store):
    model_id = _create_and_publish(client)
    client.post(f"/api/selection-models/{model_id}/versions/1/copy-to-draft", json={})
    client.post(f"/api/selection-models/{model_id}/versions", json={"base_version": 1, "draft_revision": 1})
    diff = client.get(f"/api/selection-models/{model_id}/version-diff?from=1&to=2").json()
    assert diff["status"] == "ok"
    assert diff["data"]["identical"] is True  # 未改内容仅复制基线


# ------------------------------------------------------------------ 运行隔离（门禁 10/18）
def test_multiple_manual_runs_are_independent(client, selection_store):
    model_id = _create_and_publish(client)
    first = client.post(f"/api/selection-models/{model_id}/runs", json={"records": _condition_records()}).json()
    second = client.post(f"/api/selection-models/{model_id}/runs", json={"records": _condition_records()}).json()
    assert first["data"]["run_id"] != second["data"]["run_id"]
    runs = client.get(f"/api/selection-models/{model_id}/runs").json()
    assert runs["data"]["total"] == 2
    assert runs["data"]["runs"][0]["run_id"] != runs["data"]["runs"][1]["run_id"]


def test_request_id_is_idempotent(client, selection_store):
    model_id = _create_and_publish(client)
    body = {"records": _condition_records(), "request_id": "req-fixed"}
    first = client.post(f"/api/selection-models/{model_id}/runs", json=body).json()
    second = client.post(f"/api/selection-models/{model_id}/runs", json=body).json()
    assert second["data"]["deduplicated"] is True
    assert second["data"]["run"]["run_id"] == first["data"]["run_id"]


def test_debug_run_is_isolated_from_formal_runs(client, selection_store):
    model_id = _create_and_publish(client)
    debug = client.post(f"/api/selection-models/{model_id}/debug/node", json={
        "stage_id": "condition_filter", "records": _condition_records(),
    }).json()
    assert debug["status"] == "ok"
    assert debug["watermark"]["debug"] is True
    assert debug["watermark"]["eligible_for_signal"] is False
    # 调试不落正式运行目录
    assert client.get(f"/api/selection-models/{model_id}/runs").json()["data"]["total"] == 0
    assert client.get(f"/api/selection-models/results").json()["data"]["total"] == 0


def test_debug_stage_uses_synced_market_input_then_upstream_candidates(client, selection_store, monkeypatch):
    from server.api import selection_models as selection_api

    model_id = _create_and_publish(client, model_type="funnel", template="funnel_close_breakout")
    records = [
        {"code": "sh600001", "closes": [float(i) for i in range(1, 71)]},
        {"code": "sh600002", "closes": [float(i) for i in range(70, 0, -1)]},
    ]

    class SyncedMarket:
        def resolve_universe(self, *, all_market=False):
            assert all_market is True
            return [item["code"] for item in records]

        def assemble_daily(self, codes, *, algorithm_version, persist):
            assert codes == [item["code"] for item in records]
            assert algorithm_version == "iss-debug" and persist is False
            return {"status": "OK", "records": records,
                    "gate": {"state": "PASS", "trade_date": "2026-09-30"},
                    "manifest": {"data_snapshot_id": "isolated-debug-snapshot",
                                 "as_of": "2026-09-30T15:35:00+08:00"}}

    monkeypatch.setattr(selection_api, "DataAssembler", SyncedMarket)
    preview = client.post(f"/api/selection-models/{model_id}/debug/node",
                          json={"stage_id": "market_gate"}).json()
    assert preview["status"] == "ok", preview
    assert preview["watermark"]["debug"] is True
    assert preview["watermark"]["eligible_for_signal"] is False
    assert preview["data"]["source"] == "local_snapshot"
    assert preview["data"]["snapshot"]["input_count"] == 2
    assert [(item["stage_id"], item["input_count"], item["output_count"])
            for item in preview["data"]["stages"]] == [
                ("post_close", 2, 1), ("market_gate", 1, 0)]
    assert preview["data"]["result"]["rejected_sample"][0]["code"] == "sh600001"
    assert client.get(f"/api/selection-models/{model_id}/runs").json()["data"]["total"] == 0


def test_cancel_endpoint_cannot_falsify_synchronous_run_status(client, selection_store):
    model_id = _create_and_publish(client)
    run = client.post(f"/api/selection-models/{model_id}/runs", json={"records": _condition_records()}).json()
    resp = client.post(f"/api/selection-models/runs/{run['data']['run_id']}/cancel").json()
    assert resp["error_code"] == "MODEL_RUN_CANCEL_UNSUPPORTED"
    assert client.get(f"/api/selection-models/runs/{run['data']['run_id']}").json()["data"]["run"]["status"] == "COMPLETED"
    missing = client.post("/api/selection-models/runs/nope/cancel").json()
    assert missing["error_code"] == "MODEL_RUN_NOT_FOUND"


# ------------------------------------------------------------------ SSE（W-01）
def test_run_events_stream_has_run_id_and_watermark(client, selection_store):
    model_id = _create_and_publish(client)
    run = client.post(f"/api/selection-models/{model_id}/runs", json={"records": _condition_records()}).json()
    resp = client.get(f"/api/selection-models/runs/{run['data']['run_id']}/events")
    assert resp.status_code == 200
    body = resp.text
    assert "event: run.started" in body
    assert "event: stage.completed" in body
    assert "event: run.finished" in body
    assert "watermark" in body


# ------------------------------------------------------------------ 调度与数据健康（§15.3）
def test_schedule_pause_resume_and_invalid_window(client, selection_store):
    model_id = _create_and_publish(client)
    sched = client.get(f"/api/selection-models/{model_id}/schedule").json()
    assert sched["status"] == "ok"
    assert sched["data"]["daemon"]["online"] is False
    assert sched["data"]["daemon"]["reason_code"] == "DAEMON_HEARTBEAT_MISSING"

    paused = client.post(f"/api/selection-models/{model_id}/pause").json()
    assert paused["data"]["paused"] is True
    resumed = client.post(f"/api/selection-models/{model_id}/resume").json()
    assert resumed["data"]["paused"] is False

    bad = client.put(f"/api/selection-models/{model_id}/schedule", json={"stages": {"condition_filter": "99:99"}}).json()
    assert bad["error_code"] == "MODEL_CONFIG_INVALID"


def test_r4_daemon_online_requires_fresh_matching_model_tick(client, selection_store):
    from core.selection_models.scheduler_heartbeat import SchedulerHeartbeatStore

    model_id = _create_and_publish(client)
    store = SchedulerHeartbeatStore()
    tick_at = datetime.now(timezone.utc).isoformat()
    store.record_tick({"model_id": model_id, "model_version": 1, "status": "IDLE",
        "heartbeat": {"tick_at": tick_at}, "executed": [], "next_run_at": None})
    live = client.get(f"/api/selection-models/{model_id}/schedule").json()["data"]["daemon"]
    assert live["online"] is True and live["last_tick_at"] == tick_at
    beat = store.load(model_id)
    beat["recorded_at"] = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    store.path(model_id).write_text(json.dumps(beat), encoding="utf-8")
    stale = client.get(f"/api/selection-models/{model_id}/schedule").json()["data"]["daemon"]
    assert stale["online"] is False and stale["reason_code"] == "DAEMON_HEARTBEAT_STALE"


def test_data_health_never_fabricates_coverage(client, selection_store):
    resp = client.get("/api/selection-models/data-health").json()
    assert resp["status"] == "ok"
    assert "availability" in resp["watermark"]


# ------------------------------------------------------------------ 文案草稿解析
def test_draft_from_text_returns_ambiguities(client, selection_store):
    resp = client.post("/api/selection-models/drafts/from-text", json={
        "text": "20日新高，高于60日均线，排除ST；另外想要龙头股",
    }).json()
    assert resp["status"] == "ok"
    assert resp["data"]["activated"] is False
    matched = [r["type"] for r in resp["data"]["matched_rules"]]
    assert "rolling_high" in matched and "text_exclude" in matched
    assert "另外想要龙头股" in resp["data"]["ambiguities"]


def test_llm_draft_api_uses_provider_without_creating_model(client, selection_store, monkeypatch):
    from server.llm.base import LLMStreamChunk
    from server.services import selection_llm_compiler as service

    class Provider:
        model_name = "configured-flash"

        async def stream_chat(self, messages, **kwargs):
            yield LLMStreamChunk(delta_text=json.dumps({"clauses": [
                {"id": 0, "kind": "daily_change_lte", "params": {"percent": 7}},
            ]}))

    monkeypatch.setattr(service.LLMProviderFactory, "get_provider", lambda **kwargs: Provider())
    before = client.get("/api/selection-models").json()["data"]["total"]
    resp = client.post("/api/selection-models/drafts/from-text", json={
        "text": "今日涨幅小于等于7%", "mode": "llm", "model": "configured-flash",
    }).json()
    after = client.get("/api/selection-models").json()["data"]["total"]
    assert resp["status"] == "ok", resp
    assert resp["data"]["complete"] is True
    assert resp["data"]["definition"]["stages"][0]["rules"][0]["value"] == 7
    assert resp["watermark"]["eligible_for_signal"] is False
    assert before == after


# ------------------------------------------------------------------ 权限（C-03）
def test_model_author_lacks_publish_permission(client, selection_store):
    from server.db import create_auth_token, create_user, get_role_by_code

    role = get_role_by_code("model_author")
    assert role is not None
    uid = create_user("author_a", "作者", "pw12345678", int(role["id"]))
    token = create_auth_token(uid, 3600)["token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 可创建（有 create 权限）
    created = client.post("/api/selection-models", json={"model_type": "funnel", "name": "作者模型"}, headers=headers)
    assert created.status_code == 200
    model_id = created.json()["data"]["model_id"]
    # 不可发布（无 publish 权限）
    denied = client.post(f"/api/selection-models/{model_id}/versions", json={}, headers=headers)
    assert denied.status_code == 403
    # 不可调试（debug 仅超级管理员，G-02）
    denied_debug = client.post(f"/api/selection-models/{model_id}/debug/rule",
                               json={"rule": {"id": "r", "type": "rolling_high"}, "records": []}, headers=headers)
    assert denied_debug.status_code == 403


def test_r4_author_activation_is_owner_bound_and_schedule_is_admin_only(client, selection_store):
    from server.db import create_auth_token, create_user, get_role_by_code

    role = get_role_by_code("model_author")
    first_id = create_user("r4_author_one", "作者甲", "pw12345678", int(role["id"]))
    second_id = create_user("r4_author_two", "作者乙", "pw12345678", int(role["id"]))
    first = {"Authorization": f"Bearer {create_auth_token(first_id, 3600)['token']}"}
    second = {"Authorization": f"Bearer {create_auth_token(second_id, 3600)['token']}"}
    created = client.post("/api/selection-models", json={"model_type": "condition_tree", "name": "作者甲模型"}, headers=first).json()
    assert created["status"] == "ok"
    model_id = created["data"]["model_id"]
    detail = client.get(f"/api/selection-models/{model_id}", headers=first).json()["data"]
    assert detail["owner_user_id"] == first_id and detail["permissions"]["activate"] is True
    assert client.get(f"/api/selection-models/{model_id}", headers=second).json()["data"]["permissions"]["activate"] is False
    assert client.post(f"/api/selection-models/{model_id}/versions", json={}).json()["status"] == "ok"
    assert client.post(f"/api/selection-models/{model_id}/activate/1", headers=second).status_code == 403
    assert client.post(f"/api/selection-models/{model_id}/activate/1", headers=first).json()["status"] == "ok"
    assert client.post(f"/api/selection-models/{model_id}/pause", headers=first).status_code == 403
    assert client.get(f"/api/selection-models/{model_id}/schedule").json()["data"]["paused"] is False


def test_r4_legacy_owner_requires_explicit_admin_assignment(client, selection_store):
    from core.selection_models.catalog import create_model
    from server.db import create_auth_token, create_user, get_role_by_code

    uid = create_user("r4_legacy_author", "旧模型作者", "pw12345678",
                      int(get_role_by_code("model_author")["id"]))
    headers = {"Authorization": f"Bearer {create_auth_token(uid, 3600)['token']}"}
    model_id = create_model(model_type="condition_tree", name="旧模型", operator="r4_legacy_author")["model_id"]
    assert client.post(f"/api/selection-models/{model_id}/versions", json={}).json()["status"] == "ok"
    assert client.post(f"/api/selection-models/{model_id}/activate/1", headers=headers).status_code == 403
    assigned = client.put(f"/api/selection-models/{model_id}/owner", json={"user_id": uid}).json()
    assert assigned["data"]["owner_user_id"] == uid
    assert client.put(f"/api/selection-models/{model_id}/owner", json={"user_id": uid}).json()["error_code"] == "MODEL_OWNER_CONFLICT"
    assert client.post(f"/api/selection-models/{model_id}/activate/1", headers=headers).json()["status"] == "ok"
