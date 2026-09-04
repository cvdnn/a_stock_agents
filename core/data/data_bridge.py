"""
aStocks 数据桥接层 — 4级降级数据获取

整合 a-share-data skill 的脚本，提供统一数据接口：
  L1: 腾讯 qt.gtimg.cn 直连 (~0.1s, 零依赖)
  L2: a-share-data 新浪/腾讯脚本 (~3-5s)
  L3: 东财 proxy-patch (~0.4-2s, 消耗积分)
  L4: efinance (~0.2s, 零积分)
  Fallback: 腾讯 web.ifzq.gtimg.cn 历史K线

设计为独立运行，不依赖 TACN/TradingAgents 项目。
"""

import json
import os
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ─── 路径配置 (优先级: env > config.yaml > 默认值) ──────
try:
    from core.config import PROJECT_ROOT, CONFIG_DIR, SKILLS_DIR, GLOBAL_CONFIG
except ImportError:
    PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
    CONFIG_DIR = PROJECT_ROOT / "config"
    SKILLS_DIR = PROJECT_ROOT / "skills"
    GLOBAL_CONFIG = {}

def _load_path_config() -> Dict[str, str]:
    """加载路径配置，优先级: 环境变量 > config.yaml > 默认值"""
    cfg = {}

    # 1. 尝试从 GLOBAL_CONFIG 或 config.yaml 加载
    if GLOBAL_CONFIG:
        python_cfg = GLOBAL_CONFIG.get("python", {})
        cfg["venv_python"] = python_cfg.get("venv_python", "")
        cfg["system_python"] = python_cfg.get("system_python", sys.executable or "python3")
        cfg["a_share_data_dir"] = GLOBAL_CONFIG.get("skills", {}).get("a_share_data", "")
    else:
        config_path = CONFIG_DIR / "config.yaml"
        if config_path.exists():
            try:
                import yaml
                data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
                if data:
                    cfg["venv_python"] = data.get("python", {}).get("venv_python", "")
                    cfg["system_python"] = data.get("python", {}).get("system_python", sys.executable or "python3")
                    skill_paths = data.get("skills", {})
                    cfg["a_share_data_dir"] = skill_paths.get("a_share_data", "")
            except Exception:
                pass

    # 2. 环境变量覆盖 (优先级最高)
    env_map = {
        "ASTOCKS_VENV_PY": "venv_python",
        "ASTOCKS_SYSTEM_PY": "system_python",
        "ASTOCKS_A_SHARE_DATA_DIR": "a_share_data_dir",
    }
    for env_key, cfg_key in env_map.items():
        val = os.environ.get(env_key, "")
        if val:
            cfg[cfg_key] = val

    # 3. 默认值回退
    if not cfg.get("a_share_data_dir"):
        candidates = [
            SKILLS_DIR / "a-share-data",
            PROJECT_ROOT / "skills" / "a-share-data",
        ]
        for candidate in candidates:
            if candidate.is_dir():
                cfg["a_share_data_dir"] = str(candidate)
                break
        if not cfg.get("a_share_data_dir"):
            cfg["a_share_data_dir"] = ""

    if not cfg.get("venv_python"):
        cfg["venv_python"] = sys.executable or "python3"

    if not cfg.get("system_python"):
        cfg["system_python"] = sys.executable or "python3"

    return cfg

_PATH_CFG = _load_path_config()
A_SHARE_DATA_DIR = Path(_PATH_CFG["a_share_data_dir"]) if _PATH_CFG.get("a_share_data_dir") else None
A_SHARE_SCRIPTS = A_SHARE_DATA_DIR / "scripts" if A_SHARE_DATA_DIR else None
VENV_PY = _PATH_CFG.get("venv_python", "python3")
SYSTEM_PY = _PATH_CFG.get("system_python", "python3")


class DataBridge:
    """统一数据桥接层 — 自动降级路由"""

    def __init__(self, config: Optional[Dict] = None):
        self.cfg = config or self._load_config()

    def _load_config(self) -> Dict:
        if A_SHARE_DATA_DIR:
            path = A_SHARE_DATA_DIR / "scripts" / "config.yaml"
            if path.exists():
                try:
                    import yaml
                    return yaml.safe_load(path.read_text()) or {}
                except Exception:
                    pass
        return {}

    # ═══════════════════════════════════════════════════
    #  L1: 腾讯 qt.gtimg.cn 直连 — 零依赖，任何Python环境
    # ═══════════════════════════════════════════════════

    @staticmethod
    def tencent_quote(codes: List[str]) -> Dict[str, Dict]:
        """批量获取腾讯实时行情，返回 {name: {price, change_pct, pe, ...}}"""
        codes_param = ",".join(codes)
        url = f"https://qt.gtimg.cn/q={codes_param}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            resp = urllib.request.urlopen(req, timeout=10)
            text = resp.read().decode("gbk")
        except Exception as e:
            print(f"[L1] 腾讯行情直连失败: {e}", file=sys.stderr)
            return {}

        results = {}
        for line in text.strip().split("\n"):
            if "~" not in line:
                continue
            parts = line.split("~")
            if len(parts) < 46:
                continue

            code_raw = parts[0].split("=")[0].split("_")[-1] if "_" in parts[0] else parts[0].split("=")[0]
            code = code_raw.replace("sh", "").replace("sz", "")
            name = parts[1]
            try:
                price = float(parts[3])
                prev_close = float(parts[4])
                change = price - prev_close
                change_pct = (change / prev_close * 100) if prev_close != 0 else 0
            except (ValueError, IndexError):
                continue

            outer = float(parts[7]) if parts[7] else 0
            inner = float(parts[8]) if parts[8] else 0
            o_ratio = (outer / (outer + inner) * 100) if (outer + inner) > 0 else 50

            results[name] = {
                "code": code,
                "name": name,
                "price": round(price, 2),
                "change": round(change, 2),
                "change_pct": round(change_pct, 2),
                "prev_close": round(prev_close, 2),
                "open": round(float(parts[5]), 2) if parts[5] else price,
                "high": round(float(parts[33]), 2) if parts[33] else price,
                "low": round(float(parts[34]), 2) if parts[34] else price,
                "volume_hands": int(float(parts[6])) if parts[6] else 0,
                "vol_ratio": round(float(parts[49]), 2) if len(parts) > 49 and parts[49] else 1.0,
                "turnover_pct": round(float(parts[38]), 2) if parts[38] else 0,
                "pe": round(float(parts[39]), 2) if parts[39] and parts[39] != "0" else 0,
                "market_cap": round(float(parts[45]), 2) if parts[45] else 0,
                "amplitude": round(float(parts[43]), 2) if parts[43] else 0,
                "o_ratio": round(o_ratio, 1),
                "time": parts[30] if len(parts) > 30 else "",
            }
        return results

    @staticmethod
    def tencent_index(codes: List[str] = None) -> Dict[str, Dict]:
        """获取大盘指数"""
        defaults = ["sh000001", "sz399001", "sz399006", "sh000688"]
        return DataBridge.tencent_quote(codes or defaults)

    @staticmethod
    def tencent_kline(code: str, count: int = 120) -> List[List]:
        """获取腾讯前复权日K线（零依赖）
        返回: [[date, open, close, high, low, volume], ...]
        """
        prefix = "sh" if code.startswith("6") else "sz"
        url = f"http://ifzq.gtimg.cn/appstock/app/fqkline/get?param={prefix}{code},day,,,{count},qfq"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            resp = urllib.request.urlopen(req, timeout=10)
            data = json.loads(resp.read().decode("utf-8"))
            key = f"{prefix}{code}"
            if key in data.get("data", {}):
                return data["data"][key].get("qfqday", [])
        except Exception as e:
            print(f"[L1] 腾讯K线获取失败 ({code}): {e}", file=sys.stderr)
        return []

    # ═══════════════════════════════════════════════════
    #  L2/L3: a-share-data skill 脚本调用
    # ═══════════════════════════════════════════════════

    @staticmethod
    def _run_script(script_name: str, args: str, timeout: int = 30, use_patch: bool = True) -> Optional[Dict]:
        """调用 a-share-data 的脚本 (需 A_SHARE_DATA_DIR 已配置)"""
        if not A_SHARE_SCRIPTS:
            return None
        script_path = A_SHARE_SCRIPTS / script_name
        if not script_path.exists():
            return None

        import subprocess
        if use_patch and (A_SHARE_SCRIPTS / "fetch_patched.py").exists():
            python = VENV_PY if Path(VENV_PY).is_file() else SYSTEM_PY
            cmd = [python, str(A_SHARE_SCRIPTS / "fetch_patched.py"), script_name] + args.split()
        else:
            cmd = [SYSTEM_PY, str(script_path)] + args.split()

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            if result.returncode == 0 and result.stdout:
                try:
                    return json.loads(result.stdout)
                except json.JSONDecodeError:
                    return {"text": result.stdout}
        except (subprocess.TimeoutExpired, Exception) as e:
            print(f"[L2/L3] 脚本调用失败 ({script_name}): {e}", file=sys.stderr)
        return None

    def get_realtime_quote(self, code: str) -> Optional[Dict]:
        """获取单只股票实时行情 — 自动降级"""
        # L1: 腾讯直连
        c = str(code).strip().lower().replace("sh", "").replace("sz", "").replace("bj", "")
        prefix = "sh" if str(code).lower().startswith("sh") or c.startswith(("6", "5", "9")) else ("bj" if str(code).lower().startswith("bj") or c.startswith(("8", "4", "92")) else "sz")
        result = self.tencent_quote([f"{prefix}{c}"])
        if result:
            return list(result.values())[0] if result else None

        # L2: a-share-data 脚本
        return self._run_script("fetch_realtime.py", f"--quote {code} --json")

    def get_kline(self, code: str, start: str, end: str) -> Optional[Dict]:
        """获取K线数据 — 自动降级"""
        # L1: 腾讯K线（前复权日线）
        klines = self.tencent_kline(code)
        if klines:
            return {
                "source": "tencent_direct",
                "code": code,
                "freq": "d",
                "count": len(klines),
                "data": klines,
            }

        # L2: a-share-data 脚本
        return self._run_script("fetch_history.py", f"--kline {code} --start {start} --end {end} --freq d --json")

    def get_technical(self, code: str, count: int = 120) -> Optional[Dict]:
        """获取技术指标 — 优先 L1 原地计算"""
        # L1: 获取K线 + 原地计算
        klines = self.tencent_kline(code, count)
        if klines and len(klines) >= 26:
            from . import technical_indicators as ti
            result = ti.calc_all(klines)
            return {"source": "tencent_direct+local_calc", "code": code, **result}

        # L2: a-share-data 脚本
        return self._run_script("fetch_technical.py", f"{code} --freq 1d --count {count} --indicators MA,MACD,KDJ,RSI,BOLL --json")

    def get_sector_info(self, code: str) -> Optional[Dict]:
        """获取行业信息"""
        return self._run_script("fetch_sector_info.py", f"--no-concepts --json {code}")

    def get_board_summary(self, limit: int = 20) -> Optional[Dict]:
        """获取板块排行"""
        return self._run_script("fetch_realtime.py", f"--boards-summary --boards-limit {limit} --json")

    def get_fund_flow(self, code: str, days: int = 5) -> Optional[Dict]:
        """获取资金流向"""
        return self._run_script("fetch_realtime.py", f"--fund-flow {code} --days {days} --json")

    # ═══════════════════════════════════════════════════
    #  P0 新增：筹码分布、个股事件、积分余额、A+H
    # ═══════════════════════════════════════════════════

    def get_cyq(self, code: str) -> Optional[Dict[str, Any]]:
        """获取筹码分布(CYQ) — 需 proxy-patch 模式
        返回: {profit_ratio, avg_cost, concentration_90, concentration_70, ...}
        """
        result = self._run_script("fetch_patched.py",
                                   f"fetch_realtime.py --cyq {code} --json",
                                   use_patch=True, timeout=30)
        if result:
            return result
        # 尝试直接调用 akshare (需要 venv)
        python = VENV_PY if Path(VENV_PY).is_file() else SYSTEM_PY
        if not A_SHARE_SCRIPTS:
            return None
        import subprocess
        cmd = [python, "-c", f"""
import sys
sys.path.insert(0, '{A_SHARE_SCRIPTS}')
from _init_patch import patched_akshare as ak
try:
    df = ak.stock_cyq_em(symbol='{code}')
    import json
    print(json.dumps(df.tail(3).to_dict('records'), ensure_ascii=False))
except Exception as e:
    print(json.dumps({{'error': str(e)}}))
"""]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if r.returncode == 0 and r.stdout:
                data = json.loads(r.stdout)
                if isinstance(data, list) and data:
                    latest = data[-1]
                    return {
                        "code": code,
                        "profit_ratio": latest.get("获利比例", 0),
                        "avg_cost": latest.get("平均成本", 0),
                        "cost_90_low": latest.get("90成本-低", 0),
                        "cost_90_high": latest.get("90成本-高", 0),
                        "concentration_90": latest.get("90集中度", 0),
                        "cost_70_low": latest.get("70成本-低", 0),
                        "cost_70_high": latest.get("70成本-高", 0),
                        "concentration_70": latest.get("70集中度", 0),
                    }
        except Exception as e:
            print(f"[P0] CYQ获取失败 ({code}): {e}", file=sys.stderr)
        return None

    def get_stock_events(self, code: str, name: str = "", limit: int = 20) -> Optional[Dict]:
        """获取个股事件"""
        name_arg = f"--name {name}" if name else ""
        return self._run_script("fetch_stock_events.py",
                                f"--code {code} {name_arg} --limit {limit} --json",
                                use_patch=True, timeout=30)

    def get_ah_stocks(self) -> Optional[Dict]:
        """获取A+H双重上市列表"""
        return self._run_script("fetch_ah_stocks.py", "--json", use_patch=True, timeout=30)

    def check_proxy_balance(self) -> Optional[Dict]:
        """检查代理积分余额"""
        if not A_SHARE_SCRIPTS:
            return None
        import subprocess
        cmd = [SYSTEM_PY, str(A_SHARE_SCRIPTS / "fetch_realtime.py"), "--balance"]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            if r.returncode == 0:
                try:
                    return json.loads(r.stdout)
                except json.JSONDecodeError:
                    return {"raw": r.stdout}
        except Exception as e:
            return {"error": str(e)}
        return None

    def get_tencent_pe(self, code: str) -> Optional[float]:
        """从腾讯行情获取PE (零依赖)"""
        c = str(code).strip().lower().replace("sh", "").replace("sz", "").replace("bj", "")
        prefix = "sh" if str(code).lower().startswith("sh") or c.startswith(("6", "5", "9")) else ("bj" if str(code).lower().startswith("bj") or c.startswith(("8", "4", "92")) else "sz")
        result = self.tencent_quote([f"{prefix}{c}"])
        if result:
            data = list(result.values())[0]
            pe = data.get("pe", 0)
            return pe if pe and pe > 0 else None
        return None

    def get_fundamentals(self, code: str) -> Dict[str, Any]:
        """获取基本面数据聚合 — L1优先，逐级降级

        返回: {
            pe, market_cap, turnover_pct (L1腾讯),
            pb, roe, revenue_growth (L4 efinance, 可选),
            source: 数据来源层级
        }
        """
        result = {"code": code, "source": "L1_tencent"}

        # L1: PE/市值/换手率 (腾讯直连，零依赖)
        quote = self.get_realtime_quote(code)
        if quote:
            pe = quote.get("pe", 0)
            result["pe"] = pe if pe and pe > 0 else None
            result["market_cap"] = quote.get("market_cap", 0)
            result["turnover_pct"] = quote.get("turnover_pct", 0)

        # L4: efinance 基本面 (可选，需 efinance 包)
        try:
            import subprocess
            python = SYSTEM_PY
            cmd = [python, "-c", f"""
import json
try:
    import efinance as ef
    info = ef.stock.get_base_info('{code}')
    if info is not None:
        row = info.iloc[0].to_dict() if hasattr(info, 'iloc') else info
        print(json.dumps({{k: str(v) for k, v in row.items()}}, ensure_ascii=False))
    else:
        print(json.dumps({{}}))
except Exception as e:
    print(json.dumps({{'error': str(e)}}))
"""]
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            if r.returncode == 0 and r.stdout:
                efinfo = json.loads(r.stdout)
                if efinfo and "error" not in efinfo:
                    result["source"] = "L4_efinance"
                    # 映射常见字段
                    for ef_key, our_key in [
                        ("市盈率-动态", "pe_dynamic"),
                        ("市净率", "pb"),
                        ("ROE", "roe"),
                        ("营业收入", "revenue"),
                        ("净利润", "net_profit"),
                    ]:
                        if ef_key in efinfo:
                            result[our_key] = efinfo[ef_key]
        except Exception:
            pass

        return result

    # ═══════════════════════════════════════════════════
    #  综合数据获取 — 全链路降级
    # ═══════════════════════════════════════════════════

    def fetch_full_snapshot(self, code: str, with_technical: bool = True) -> Dict[str, Any]:
        """获取单只股票的全维快照"""
        result = {"code": code, "ts": time.time()}

        # 实时行情
        quote = self.get_realtime_quote(code)
        result["quote"] = quote

        # 技术指标
        if with_technical:
            tech = self.get_technical(code)
            result["technical"] = tech

        return result

    def fetch_batch_snapshot(self, codes: List[str]) -> List[Dict]:
        """批量获取实时行情"""
        prefix_codes = [f"sh{c}" if c.startswith("6") else f"sz{c}" for c in codes]
        results = self.tencent_quote(prefix_codes)
        output = []
        for c in codes:
            for name, data in results.items():
                if data.get("code") == c:
                    output.append(data)
                    break
        return output


# ─── 便捷函数 ─────────────────────────────────────────

def get_bridge() -> DataBridge:
    return DataBridge()


def batch_quote(codes: List[str]) -> Dict[str, Dict]:
    codes_with_prefix = [f"sh{c}" if c.startswith("6") else f"sz{c}" for c in codes]
    return DataBridge.tencent_quote(codes_with_prefix)


def index_snapshot() -> Dict[str, Dict]:
    return DataBridge.tencent_index()


# ─── CLI ──────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="aStocks 数据桥接层")
    parser.add_argument("action", choices=["quote", "kline", "technical", "index", "batch",
                                            "sector", "boards", "fund-flow"])
    parser.add_argument("--code", help="股票代码")
    parser.add_argument("--codes", help="批量代码，逗号分隔")
    parser.add_argument("--start", help="开始日期 YYYYMMDD")
    parser.add_argument("--end", help="结束日期 YYYYMMDD")
    parser.add_argument("--count", type=int, default=120, help="K线数量")
    parser.add_argument("--json", action="store_true", default=True)
    args = parser.parse_args()

    bridge = DataBridge()

    if args.action == "quote":
        result = bridge.get_realtime_quote(args.code)
    elif args.action == "kline":
        result = bridge.get_kline(args.code, args.start or "20250101", args.end or time.strftime("%Y%m%d"))
    elif args.action == "technical":
        result = bridge.get_technical(args.code, args.count)
    elif args.action == "index":
        result = bridge.index_snapshot()
    elif args.action == "batch":
        codes = args.codes.split(",") if args.codes else []
        result = bridge.fetch_batch_snapshot(codes)
    elif args.action == "sector":
        result = bridge.get_sector_info(args.code)
    elif args.action == "boards":
        result = bridge.get_board_summary()
    elif args.action == "fund-flow":
        result = bridge.get_fund_flow(args.code)

    print(json.dumps(result, ensure_ascii=False, indent=2))
