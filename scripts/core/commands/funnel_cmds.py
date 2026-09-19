# -*- coding: utf-8 -*-
"""CLI commands for the configurable close-to-open stock funnel."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping

from core.strategy.stock_funnel import StockFunnelPipeline, derive_open_gap


def _read_json(path_value: str) -> Any:
    if path_value == "-":
        return json.load(sys.stdin)
    return json.loads(Path(path_value).read_text(encoding="utf-8"))


def cmd_funnel(args) -> None:
    config_path = Path(args.config).resolve() if getattr(args, "config", None) else None
    pipeline = StockFunnelPipeline(config_path=config_path)
    action = getattr(args, "funnel_cmd", None)

    if action == "validate":
        payload = {
            "status": "valid",
            "config": str(config_path or "config/funnel_strategy.yaml"),
            "stages": pipeline.stage_ids,
            "registered_rule_types": pipeline.registry.names,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    if action != "run":
        raise ValueError("funnel requires either validate or run")

    source = _read_json(args.input)
    if isinstance(source, list):
        records: List[Mapping[str, Any]] = source
        embedded_context: Dict[str, Any] = {}
    elif isinstance(source, dict):
        # A stage result can be fed directly to the next stage.
        records = source.get("records", source.get("passed_records", []))
        embedded_context = source.get("context", {}) or {}
    else:
        raise ValueError("input JSON must be a list or an object with records/context")

    context = embedded_context
    if getattr(args, "context", None):
        loaded_context = _read_json(args.context)
        if not isinstance(loaded_context, dict):
            raise ValueError("context JSON must be an object")
        context = loaded_context

    if args.stage == "opening_gap":
        records = derive_open_gap(records)

    payload = pipeline.run_stage(args.stage, records, context)
    if getattr(args, "save", False):
        target = pipeline.save_result(payload, trade_date=getattr(args, "trade_date", None))
        payload["saved_to"] = str(target)
    print(json.dumps(payload, ensure_ascii=False, indent=2))


__all__ = ["cmd_funnel"]
