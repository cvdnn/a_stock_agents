"""
A-Share Quant Engine - Data Layer (数据接入与缓存层)
功能:
1. 腾讯高速行情 (L1 qt.gtimg.cn 实时快照 + ifzq.gtimg.cn 日K线) 零依赖接入
2. 本地 JSON 缓存加速
3. 前复权日K线清洗、数据结构标准化、ST/停牌过滤
"""

import os
import json
import time
import urllib.request
import urllib.parse
from typing import Dict, List, Optional, Any, Union

CACHE_DIR = os.path.join(os.path.dirname(__file__), ".data_cache")
os.makedirs(CACHE_DIR, exist_ok=True)


class DataLayer:
    """A股数据接入与管理层"""

    @staticmethod
    def normalize_symbol(symbol: str) -> str:
        """统一标的代码格式为 6位数字，并返回市场前缀格式 (如 sh600519, sz000858, bj830000)"""
        raw = symbol.strip().lower()
        digits = "".join([c for c in raw if c.isdigit()])
        if len(digits) != 6:
            raise ValueError(f"无效的股票代码: {symbol}")
        
        if digits.startswith(("60", "68", "90")):
            return f"sh{digits}"
        elif digits.startswith(("00", "30", "20")):
            return f"sz{digits}"
        elif digits.startswith(("43", "83", "87", "92")):
            return f"bj{digits}"
        else:
            return f"sh{digits}" if raw.startswith("sh") else f"sz{digits}"

    @classmethod
    def get_realtime_quote(cls, symbol: str) -> Dict[str, Any]:
        """获取个股实时行情快照"""
        full_code = cls.normalize_symbol(symbol)
        url = f"http://qt.gtimg.cn/q={full_code}"
        
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                data = resp.read().decode("gbk", errors="ignore")
            
            if "=" not in data:
                return {}
            content = data.split("=")[1].strip().strip('";')
            parts = content.split("~")
            if len(parts) < 45:
                return {}

            name = parts[1]
            code = parts[2]
            current_price = float(parts[3])
            prev_close = float(parts[4])
            open_price = float(parts[5])
            volume = float(parts[6])  # 手
            high_price = float(parts[33]) if len(parts) > 33 and parts[33] else current_price
            low_price = float(parts[34]) if len(parts) > 34 and parts[34] else current_price
            turnover = float(parts[38]) if len(parts) > 38 and parts[38] else 0.0  # 换手率 %
            pe = float(parts[39]) if len(parts) > 39 and parts[39] else 0.0
            pb = float(parts[46]) if len(parts) > 46 and parts[46] else 0.0
            amount = float(parts[37]) if len(parts) > 37 and parts[37] else 0.0  # 成交额 (万元)

            change_pct = round((current_price - prev_close) / prev_close * 100, 2) if prev_close > 0 else 0.0

            return {
                "symbol": code,
                "name": name,
                "price": current_price,
                "prev_close": prev_close,
                "open": open_price,
                "high": high_price,
                "low": low_price,
                "volume": volume,
                "amount": amount * 10000,  # 换算为元
                "turnover": turnover,
                "pe": pe,
                "pb": pb,
                "change_pct": change_pct,
                "is_st": "ST" in name or "*ST" in name,
                "is_suspended": current_price <= 0 or volume <= 0
            }
        except Exception as e:
            return {"symbol": symbol, "error": str(e)}

    @classmethod
    def get_kline_history(cls, symbol: str, num_days: int = 500, use_cache: bool = True) -> List[Dict[str, Any]]:
        """获取前复权日K线历史数据
        返回格式: List of dicts, sorted by date asc:
        [{'date': '2026-01-02', 'open': 10.0, 'close': 10.5, 'high': 10.8, 'low': 9.9, 'volume': 120000, 'amount': 1250000.0}, ...]
        """
        full_code = cls.normalize_symbol(symbol)
        cache_file = os.path.join(CACHE_DIR, f"{full_code}_qfq_kline.json")

        # 检查缓存 (如果缓存创建时间在 4小时内，直接复用)
        if use_cache and os.path.exists(cache_file):
            try:
                mtime = os.path.getmtime(cache_file)
                if time.time() - mtime < 14400:  # 4 hours
                    with open(cache_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        if len(data) >= min(num_days, 50):
                            return data[-num_days:]
            except Exception:
                pass

        # 从腾讯接口获取前复权日K
        url = f"http://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={full_code},day,,,{num_days},qfq"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        
        try:
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                raw_json = json.loads(resp.read().decode("utf-8"))
            
            stock_data = raw_json.get("data", {}).get(full_code, {})
            klines_raw = stock_data.get("qfqday", [])
            if not klines_raw:
                klines_raw = stock_data.get("day", [])
            
            result = []
            for item in klines_raw:
                if not isinstance(item, list) or len(item) < 6:
                    continue
                try:
                    d = str(item[0])
                    o = float(item[1])
                    c = float(item[2])
                    h = float(item[3])
                    l = float(item[4])
                    v = float(item[5])
                    amt = float(item[6]) * 10000 if len(item) > 6 and isinstance(item[6], (int, float, str)) and item[6] else o * v * 100
                    result.append({
                        "date": d,
                        "open": o,
                        "close": c,
                        "high": h,
                        "low": l,
                        "volume": v,
                        "amount": amt
                    })
                except (ValueError, TypeError):
                    continue

            if result and use_cache:
                with open(cache_file, "w", encoding="utf-8") as f:
                    json.dump(result, f, ensure_ascii=False, indent=2)

            return result[-num_days:] if result else []
        except Exception as e:
            if os.path.exists(cache_file):
                with open(cache_file, "r", encoding="utf-8") as f:
                    return json.load(f)[-num_days:]
            print(f"Error fetching kline for {symbol}: {e}")
            return []

    @classmethod
    def get_batch_quotes(cls, symbols: List[str]) -> Dict[str, Dict[str, Any]]:
        """批量获取实时行情"""
        full_codes = [cls.normalize_symbol(s) for s in symbols]
        query_str = ",".join(full_codes)
        url = f"http://qt.gtimg.cn/q={query_str}"
        
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        result = {}
        try:
            with urllib.request.urlopen(req, timeout=4.0) as resp:
                data = resp.read().decode("gbk", errors="ignore")
            
            for line in data.strip().split(";"):
                line = line.strip()
                if not line or "=" not in line:
                    continue
                content = line.split("=")[1].strip().strip('";')
                parts = content.split("~")
                if len(parts) < 45:
                    continue
                
                code = parts[2]
                current_price = float(parts[3])
                prev_close = float(parts[4])
                open_price = float(parts[5])
                volume = float(parts[6])
                high_price = float(parts[33]) if len(parts) > 33 and parts[33] else current_price
                low_price = float(parts[34]) if len(parts) > 34 and parts[34] else current_price
                turnover = float(parts[38]) if len(parts) > 38 and parts[38] else 0.0
                pe = float(parts[39]) if len(parts) > 39 and parts[39] else 0.0
                pb = float(parts[46]) if len(parts) > 46 and parts[46] else 0.0
                amount = float(parts[37]) if len(parts) > 37 and parts[37] else 0.0

                change_pct = round((current_price - prev_close) / prev_close * 100, 2) if prev_close > 0 else 0.0

                result[code] = {
                    "symbol": code,
                    "name": parts[1],
                    "price": current_price,
                    "prev_close": prev_close,
                    "open": open_price,
                    "high": high_price,
                    "low": low_price,
                    "volume": volume,
                    "amount": amount * 10000,
                    "turnover": turnover,
                    "pe": pe,
                    "pb": pb,
                    "change_pct": change_pct,
                    "is_st": "ST" in parts[1] or "*ST" in parts[1],
                    "is_suspended": current_price <= 0 or volume <= 0
                }
        except Exception as e:
            print(f"Error in get_batch_quotes: {e}")
        return result
