# -*- coding: utf-8 -*-
"""
core.paper_trading.account_manager - Paper trading account manager adapter.
Connects PaperTradingEngine directly to agent tools and API services.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.config import get_logger
from core.paper_trading.engine import OrderRequest, PaperTradingEngine
from core.paper_trading.paper_trading_runtime import get_default_db_path

logger = get_logger("core.paper_trading.account_manager")


class AccountManager:
    """管理模拟盘账户资金与订单操作，封装 SQLite PaperTradingEngine。"""

    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path = str(db_path or get_default_db_path())
        self.engine = PaperTradingEngine(db_path=self.db_path)
        self._ensure_default_account()

    def _ensure_default_account(self) -> None:
        """确保系统至少存在一个可用的模拟盘账户（如 alpha）。"""
        try:
            accounts = self.engine.list_accounts()
            if not accounts:
                self.engine.create_account("alpha", 1_000_000.0)
                self.engine.set_default_account("alpha")
        except Exception as exc:
            logger.warning("Could not initialize default paper trading account: %s", exc)

    def _resolve_account_id(self, account_id: Optional[str] = None) -> str:
        if account_id:
            return account_id
        def_id = self.engine.get_default_account_id()
        if def_id:
            return def_id
        accounts = self.engine.list_accounts()
        if accounts:
            return accounts[0]["account_id"]
        return "alpha"

    def get_account(self, account_id: Optional[str] = None) -> Dict[str, Any]:
        """获取账户资金及资产概况，包含 cash 与 total_assets 必须字段。"""
        aid = self._resolve_account_id(account_id)
        try:
            acc = self.engine.get_account(aid)
        except KeyError:
            self.engine.create_account(aid, 1_000_000.0)
            acc = self.engine.get_account(aid)

        positions = self.engine.get_positions(aid)
        market_val = sum(float(p.get("market_value", 0.0) or 0.0) for p in positions)
        cash = float(acc.get("cash", 0.0))
        avail = float(acc.get("available_cash", cash))
        frozen = float(acc.get("frozen_cash", 0.0))
        total_assets = round(cash + market_val, 2)

        return {
            "account_id": aid,
            "cash": round(cash, 2),
            "available_cash": round(avail, 2),
            "frozen_cash": round(frozen, 2),
            "market_value": round(market_val, 2),
            "total_assets": total_assets,
            "net_asset": total_assets,
            "positions": positions,
            "positions_count": len(positions),
            "updated_at": acc.get("updated_at", ""),
        }

    def get_positions(self, account_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """获取持仓列表。"""
        aid = self._resolve_account_id(account_id)
        return self.engine.get_positions(aid)

    def get_orders(self, account_id: Optional[str] = None, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """获取订单列表。"""
        aid = self._resolve_account_id(account_id)
        return self.engine.list_orders(aid, status=status)

    def place_order(
        self,
        code: str,
        side: str,
        shares: int,
        price: Optional[float] = None,
        order_type: str = "limit",
        account_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """提交委托挂单。"""
        aid = self._resolve_account_id(account_id)
        req = OrderRequest(
            account_id=aid,
            symbol=str(code).strip(),
            side=str(side).lower().strip(),
            qty=int(shares),
            order_type="market" if price is None else str(order_type).lower(),
            limit_price=float(price) if price is not None else None,
        )
        return self.engine.place_order(req)

    def cancel_order(self, order_id: str) -> Dict[str, Any]:
        """撤销委托挂单。"""
        return self.engine.cancel_order(str(order_id).strip())
