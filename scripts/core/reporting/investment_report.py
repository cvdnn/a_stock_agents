#!/usr/bin/env python3
"""
投资报告生成器 — 技术面 + 产业成长性双维度报告

用法:
  investment_report.py --code 600760              # 个股报告
  investment_report.py --code 600760 --json        # JSON 格式
  investment_report.py --pool selected             # 自选股全景报告
  investment_report.py --pool watch                # 关注股评估报告
  investment_report.py --sector "航空装备"         # 板块产业分析
"""
import argparse
import csv
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# ── 路径与环境自适应 ──
SCRIPT_DIR = Path(__file__).resolve().parent
from core.config import PROJECT_ROOT, OUTPUT_POOLS_DIR, OUTPUT_REPORTS_DIR
POOLS_BASE = OUTPUT_POOLS_DIR

SELECTED_PATH = os.path.join(str(POOLS_BASE), "selected_pool.csv")
WATCH_PATH = os.path.join(str(POOLS_BASE), "watch_pool.csv")
A_DATA_DIR = str(PROJECT_ROOT / "core" / "data")
VENV_PY = sys.executable


def _run(cmd: list[str], timeout=30) -> dict:
    """执行命令返回结果"""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if r.returncode == 0 and r.stdout.strip():
            return {"data": r.stdout.strip(), "error": None}
        return {"data": None, "error": r.stderr[:200]}
    except Exception as e:
        return {"data": None, "error": str(e)}


def get_quote(code: str) -> dict:
    """获取实时行情"""
    try:
        from core.data.data_bridge import DataBridge
        q = DataBridge().get_realtime_quote(code)
        if q and "price" in q:
            return q
    except Exception:
        pass
    r = _run([VENV_PY, os.path.join(A_DATA_DIR, "fetch_realtime.py"), "--quote", code, "--json"])
    if r["data"]:
        try:
            return json.loads(r["data"])
        except json.JSONDecodeError:
            pass
    return {"error": "行情获取失败"}


def get_technical(code: str) -> dict:
    """获取技术指标"""
    try:
        from core.data.data_bridge import DataBridge
        from core.indicators.technical_indicators import calc_all
        bridge = DataBridge()
        klines = bridge.tencent_kline(code, count=120)
        if klines and len(klines) >= 20:
            tech = calc_all(klines)
            return tech.get("latest", {})
    except Exception:
        pass
    r = _run([VENV_PY, os.path.join(A_DATA_DIR, "fetch_technical.py"), code, "--freq", "1d", "--count", "120",
              "--indicators", "MA,MACD,KDJ,RSI,BOLL", "--json"], timeout=45)
    if r["data"]:
        try:
            data = json.loads(r["data"])
            if data:
                return data[-1] if isinstance(data, list) else data  # 最新一根
        except (json.JSONDecodeError, IndexError):
            pass
    return {"error": "技术指标获取失败"}


def _load_proxy_auth() -> tuple[str, str]:
    """从环境读取代理网关与鉴权令牌，避免在源码中硬编码凭据。

    优先级: 环境变量 PROXY_GATEWAY / AUTH_TOKEN → ~/.AI-Platform/.env
    """
    gateway = os.environ.get("PROXY_GATEWAY", "101.201.173.125")
    token = os.environ.get("AUTH_TOKEN", "")
    if not token:
        env_path = Path.home() / ".AI-Platform" / ".env"
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.startswith("AUTH_TOKEN="):
                    token = line.split("=", 1)[1].strip().strip("\"'")
                    break
    return gateway, token


def get_cyq(code: str) -> dict:
    """获取筹码分布"""
    gateway, auth_token = _load_proxy_auth()
    if not auth_token:
        return {"error": "未配置 AUTH_TOKEN，无法获取筹码分布（请设置环境变量 AUTH_TOKEN）"}
    code_py = (
        f"import akshare_proxy_patch; "
        f"akshare_proxy_patch.install_patch({gateway!r}, auth_token={auth_token!r}, fast=True); "
        f"import akshare as ak; "
        f"df=ak.stock_cyq_em(symbol={code!r}); "
        f"l=df.iloc[-1]; "
        f"print(json.dumps({{'date':str(l['日期']),'profit':float(l['获利比例']),"
        f"'avg_cost':float(l['平均成本']),'concentration':float(l['90集中度']),"
        f"'lower':float(l['90成本-低']),'upper':float(l['90成本-高'])}}))"
    )
    r = _run([VENV_PY, "-c", code_py], timeout=30)
    if r["data"]:
        try:
            return json.loads(r["data"])
        except json.JSONDecodeError:
            pass
    return {"error": "筹码获取失败"}


def get_fund_flow(code: str) -> dict:
    """获取资金流向"""
    r = _run([VENV_PY, os.path.join(A_DATA_DIR, "fetch_patched.py"),
              "fetch_realtime.py", "--fund-flow", code, "--days", "5", "--json"], timeout=30)
    if r["data"]:
        try:
            return json.loads(r["data"])
        except json.JSONDecodeError:
            pass
    return {"error": "资金流向获取失败"}


def get_sector(code: str) -> dict:
    """获取行业信息"""
    r = _run([VENV_PY, os.path.join(A_DATA_DIR, "fetch_patched.py"),
              "fetch_sector_info.py", "--no-concepts", "--json", code], timeout=20)
    if r["data"]:
        try:
            return json.loads(r["data"])
        except json.JSONDecodeError:
            pass
    return {"error": "行业获取失败"}


def read_pool(path: str) -> list:
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def report_single(code: str, json_output: bool = False) -> dict:
    """生成单只个股投资报告"""
    quote = get_quote(code)
    tech = get_technical(code)
    cyq = get_cyq(code)
    fund = get_fund_flow(code)
    sector = get_sector(code)

    report = {
        "code": code,
        "name": quote.get("名称", code),
        "report_date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "price": quote.get("最新价"),
        "change": quote.get("涨跌幅(%)"),
        "market_state": quote.get("市场状态"),
        "data_source": quote.get("数据源", "?"),
        "technical": {
            "ma": {
                "ma5": tech.get("MA5"),
                "ma10": tech.get("MA10"),
                "ma20": tech.get("MA20"),
                "ma60": tech.get("MA60"),
            },
            "macd": {
                "dif": tech.get("MACD_DIF"),
                "dea": tech.get("MACD_DEA"),
                "macd": tech.get("MACD"),
            },
            "kdj": {
                "k": tech.get("KDJ_K"),
                "d": tech.get("KDJ_D"),
                "j": tech.get("KDJ_J"),
            },
            "rsi": tech.get("RSI"),
        },
        "cyq": cyq,
        "fund_flow": fund,
        "sector": sector,
    }

    if json_output:
        return report

    # 文本输出
    name = report["name"]
    price = report["price"]
    change = report["change"]
    print("=" * 56)
    print(f"  个股投资报告: {name}({code})")
    print(f"  日期: {report['report_date']}")
    print(f"  现价: {price} ({change:+.2f}%)")
    print(f"  数据源: {report['data_source']}")
    print("=" * 56)

    # 技术面
    print("\n── 技术面分析 ──")
    ma = report["technical"]["ma"]
    if all(v is not None for v in [ma["ma5"], ma["ma10"], ma["ma20"], ma["ma60"]]):
        order = "多头" if ma["ma5"] > ma["ma10"] > ma["ma20"] > ma["ma60"] else "非多头"
        print(f"  均线: MA5={ma['ma5']:.2f} MA10={ma['ma10']:.2f} MA20={ma['ma20']:.2f} MA60={ma['ma60']:.2f} ({order})")
    macd = report["technical"]["macd"]
    if macd.get("dif") is not None:
        macd_status = "0轴上方" if macd["dif"] > 0 else "0轴下方"
        cross = "金叉" if macd["dif"] > macd["dea"] else "死叉"
        print(f"  MACD: DIF={macd['dif']:.2f} DEA={macd['dea']:.2f} ({macd_status} {cross})")
    kdj = report["technical"]["kdj"]
    if kdj.get("j") is not None:
        print(f"  KDJ: K={kdj['k']:.1f} D={kdj['d']:.1f} J={kdj['j']:.1f}")

    # 筹码
    print("\n── 筹码分布 ──")
    if "profit" in report["cyq"]:
        c = report["cyq"]
        print(f"  日期: {c.get('date','?')}")
        print(f"  获利比例: {c['profit']*100:.1f}%")
        print(f"  平均成本: {c['avg_cost']:.2f}")
        print(f"  90%筹码: {c['lower']:.2f}~{c['upper']:.2f} 集中度:{c['concentration']:.4f}")
        conc_level = "集中" if c['concentration'] < 0.13 else "发散" if c['concentration'] > 0.15 else "中性"
        print(f"  筹码状态: {conc_level}")

    # 行业
    print("\n── 所属行业 ──")
    if report["sector"].get("name"):
        print(f"  板块: {report['sector']['name']} ({report['sector'].get('industry','?')})")

    # 资金
    print("\n── 资金流向 ──")
    if isinstance(report["fund_flow"], list) and len(report["fund_flow"]) > 0:
        total = sum(f.get("主力净流入-净额", 0) for f in report["fund_flow"])
        direction = "流入" if total > 0 else "流出"
        print(f"  近5日主力净{direction}: {total/10000:.0f}万")

    print("\n" + "=" * 56)
    print(f"  报告仅供参看，不构成投资建议")
    print("=" * 56)

    return report


def report_pool(pool_type: str):
    """生成池内所有股票报告"""
    path = SELECTED_PATH if pool_type == "selected" else WATCH_PATH
    pool_name = "自选股" if pool_type == "selected" else "关注股"
    rows = read_pool(path)

    if not rows:
        print(f"{pool_name}池为空")
        return

    print(f"\n{'='*56}")
    print(f"  {pool_name}池全景报告 ({len(rows)}只)")
    print(f"  日期: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*56}")

    for r in rows:
        code = r["code"]
        name = r["name"]
        print(f"\n{'─'*40}")
        print(f"  {name}({code}) — 评级:{r.get('rating','?')} 理由:{r.get('reason','?')[:30]}")
        print(f"{'─'*40}")

        quote = get_quote(code)
        if "error" not in quote:
            price = quote.get("price") or quote.get("最新价", "?")
            chg = quote.get("change_pct") if quote.get("change_pct") is not None else quote.get("涨跌幅(%)", 0.0)
            try:
                chg_str = f"{float(chg):+.2f}%"
            except (ValueError, TypeError):
                chg_str = str(chg)
            print(f"  现价: {price} ({chg_str})")
        else:
            print(f"  [行情获取失败]")

        tech = get_technical(code)
        if "error" not in tech:
            ma5 = tech.get("ma5") or tech.get("MA5") or (tech.get("ma", {}).get(5) if isinstance(tech.get("ma"), dict) else "?")
            ma10 = tech.get("ma10") or tech.get("MA10") or (tech.get("ma", {}).get(10) if isinstance(tech.get("ma"), dict) else "?")
            ma20 = tech.get("ma20") or tech.get("MA20") or (tech.get("ma", {}).get(20) if isinstance(tech.get("ma"), dict) else "?")
            print(f"  均线: MA5={ma5} MA10={ma10} MA20={ma20}")

    print(f"\n{'='*56}")


def report_sector(sector_name: str):
    """板块产业分析"""
    print(f"\n{'='*56}")
    print(f"  板块产业分析: {sector_name}")
    print(f"  日期: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*56}")

    print("\n── 板块排行查询（需 a-share-data）──")
    print(f"  $VENV_PY fetch_patched.py fetch_realtime.py --boards-summary --boards-limit 20 --json")
    print(f"  然后 grep '{sector_name}'")
    print("\n── 产业成长性分析要点（Agent需补充）──")
    print(f"  1. 产业阶段：需搜索最新行业研报")
    print(f"  2. 政策支持：需搜索近期政策文件")
    print(f"  3. 竞争格局：需搜索行业集中度数据")
    print(f"  4. 成长驱动：需搜索产业增长驱动因素")
    print("\n  提示: Agent 需通过 web_search 搜索上述信息后补充")


def main():
    parser = argparse.ArgumentParser(description="投资报告生成器")
    parser.add_argument("--code", help="股票代码")
    parser.add_argument("--json", action="store_true", help="JSON输出")
    parser.add_argument("--pool", choices=["selected", "watch"], help="池全景报告")
    parser.add_argument("--sector", help="板块产业分析")

    args = parser.parse_args()

    if args.pool:
        report_pool(args.pool)
    elif args.sector:
        report_sector(args.sector)
    elif args.code:
        result = report_single(args.code, json_output=args.json)
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()