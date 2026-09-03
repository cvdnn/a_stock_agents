#!/usr/bin/env python3
"""
通达信数据同步工具

三种同步模式：
  1. pytdx 直连 — 通过 pytdx 库直接连接通达信行情服务器获取数据
  2. 导入通达信导出文件 — 读取通达信导出的 CSV/Excel 自选股文件
  3. 读取本地 T0002 文件 — 直接解析通达信安装目录下的自选股文件

用法:
  tdx_sync.py test                    # 测试 pytdx 连接
  tdx_sync.py import --file <path>    # 导入通达信导出的自选股CSV
  tdx_sync.py t0002 --path <tdx_dir>  # 读取通达信本地自选股
  tdx_sync.py quote <code>            # 通过 pytdx 获取个股行情
"""
import argparse
import csv
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# ── 路径与环境自适应 ──
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PROJECT_ROOT / "core") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "core"))

from core.config import OUTPUT_POOLS_DIR
POOLS_BASE = str(OUTPUT_POOLS_DIR)

SELECTED_PATH = os.path.join(POOLS_BASE, "selected_pool.csv")
WATCH_PATH = os.path.join(POOLS_BASE, "watch_pool.csv")


SELECTED_FIELDS = ["code", "name", "added_date", "reason", "sector", "rating", "entry_price", "position"]
WATCH_FIELDS = ["code", "name", "added_date", "reason", "sector", "wait_condition"]


def _ensure_file(path, fields):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if not os.path.exists(path):
        with open(path, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(fields)


def _read_csv(path):
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _write_csv(path, rows, fields):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


# ── 模式1: pytdx 直连 ──

def cmd_test(args):
    """测试 pytdx 连接"""
    servers = [
        ("180.153.18.170", 7709),
        ("180.153.18.171", 7709),
        ("119.147.212.81", 7709),
        ("119.147.212.82", 7709),
        ("218.75.126.51", 7709),
        ("112.74.142.143", 7709),
        ("40.73.36.197", 7709),
        ("106.15.69.99", 7709),
        ("47.107.73.188", 7709),
        ("59.175.238.38", 7709),
        ("123.125.108.22", 7709),
        ("61.153.144.183", 7709),
    ]

    print("pytdx 服务器连接测试")
    print("=" * 50)

    try:
        from pytdx.hq import TdxHq_API
    except ImportError:
        print("✗ pytdx 未安装，请执行: pip install pytdx")
        return

    for ip, port in servers:
        try:
            api = TdxHq_API()
            if api.connect(ip, port):
                # 尝试获取数据验证
                result = api.get_security_quotes([(1, 600000)])
                if result:
                    print(f"✓ {ip}:{port} — 可用 (数据正常)")
                    api.disconnect()
                    return True
                else:
                    print(f"⚠ {ip}:{port} — 可连接但数据异常")
            else:
                print(f"✗ {ip}:{port} — connect返回False")
        except Exception as e:
            print(f"✗ {ip}:{port} — {type(e).__name__}")

    print("\n所有服务器均不可用")
    print("提示: 通达信服务器IP经常变更，可搜索'pytdx 服务器列表'获取最新IP")
    return False


def cmd_quote(args):
    """通过 pytdx 获取个股行情"""
    try:
        from pytdx.hq import TdxHq_API
    except ImportError:
        print("✗ pytdx 未安装")
        return

    code_str = args.code
    if code_str.startswith("6"):
        market = 1  # 上海
    elif code_str.startswith(("0", "3")):
        market = 0  # 深圳
    else:
        print(f"无法判断市场: {code_str}")
        return

    code_int = int(code_str)

    api = TdxHq_API()
    for ip, port in [
        ("180.153.18.170", 7709),
        ("180.153.18.171", 7709),
    ]:
        try:
            if api.connect(ip, port):
                result = api.get_security_quotes([(market, code_int)])
                if result:
                    r = result[0]
                    print(f"股票: {r.get('code','?')}")
                    print(f"最新价: {r.get('price',0)}")
                    print(f"涨幅: {r.get('涨跌幅',0)}%")
                    print(f"最高: {r.get('high',0)}  最低: {r.get('low',0)}")
                    print(f"开盘: {r.get('open',0)}  昨收: {r.get('last_close',0)}")
                    print(f"成交量: {r.get('vol',0)}")
                    api.disconnect()
                    return
                api.disconnect()
        except:
            continue

    print("获取失败")


# ── 模式2: 导入通达信导出文件 ──

def cmd_import(args):
    """导入通达信导出自选股CSV"""
    file_path = args.file
    pool = args.pool or "watch"

    if not os.path.exists(file_path):
        print(f"✗ 文件不存在: {file_path}")
        return

    print(f"导入文件: {file_path}")
    print(f"目标池: {pool}")

    target_path = SELECTED_PATH if pool == "selected" else WATCH_PATH
    target_fields = SELECTED_FIELDS if pool == "selected" else WATCH_FIELDS
    pool_name = "自选股" if pool == "selected" else "关注股"

    _ensure_file(target_path, target_fields)
    existing = _read_csv(target_path)
    existing_codes = {r["code"] for r in existing}

    imported = 0
    skipped = 0
    blocked = 0  # 科创板/北交所过滤

    # 尝试检测编码（通达信导出GBK/UTF-8都可能）
    encodings = ["gbk", "utf-8", "gb2312", "gb18030"]
    content = None
    used_enc = None
    for enc in encodings:
        try:
            with open(file_path, "r", encoding=enc) as f:
                content = f.read()
                used_enc = enc
                break
        except (UnicodeDecodeError, UnicodeError):
            continue

    if content is None:
        print(f"✗ 无法识别文件编码")
        return

    print(f"  编码: {used_enc}")

    lines = content.split("\n")
    for line in lines:
        line = line.strip()
        if not line or line.startswith(("代码", "序号", "市场", "#")):
            continue

        parts = line.split(",")
        if len(parts) < 3:
            parts = line.split("\t")
        if len(parts) < 2:
            continue

        # 尝试提取股票代码
        code = ""
        name = ""
        for p in parts:
            p = p.strip()
            if p.isdigit() and len(p) == 6:
                code = p
            elif any(c.isalpha() for c in p) and len(p) <= 8:
                name = p

        if not code:
            continue
        if code.startswith(('688','689','30','8','4')):
            blocked += 1
            continue
        if code in existing_codes:
            skipped += 1
            continue

        if pool == "selected":
            existing.append({
                "code": code,
                "name": name,
                "added_date": datetime.now().strftime("%Y-%m-%d"),
                "reason": f"从通达信导入",
                "sector": "",
                "rating": "C",
                "entry_price": "",
                "position": "",
            })
        else:
            existing.append({
                "code": code,
                "name": name,
                "added_date": datetime.now().strftime("%Y-%m-%d"),
                "reason": f"从通达信导入",
                "sector": "",
                "wait_condition": "待评估",
            })

        existing_codes.add(code)
        imported += 1

    _write_csv(target_path, existing, target_fields)

    print(f"\n导入完成:")
    print(f"  成功导入: {imported} 只")
    print(f"  跳过(已存在): {skipped} 只")
    print(f"  当前{pool_name}池共: {len(existing)} 只")


# ── 模式3: 读取通达信本地 T0002 文件 ──

def cmd_t0002(args):
    """读取通达信本地自选股文件"""
    tdx_dir = args.path
    if not tdx_dir:
        # 尝试自动查找
        for base in ["/mnt/c/Program Files", "/mnt/c/Program Files (x86)"]:
            for d in os.listdir(base):
                if "通达信" in d or "tdx" in d.lower():
                    tdx_dir = os.path.join(base, d)
                    break

    if not tdx_dir or not os.path.exists(tdx_dir):
        print("✗ 未找到通达信安装目录")
        print("  请通过 --path 参数指定")
        return

    block_dir = os.path.join(tdx_dir, "T0002", "block")
    if not os.path.exists(block_dir):
        print(f"✗ 未找到自选股目录: {block_dir}")
        return

    print(f"通达信目录: {tdx_dir}")
    print(f"自选股目录: {block_dir}")
    print()

    # 列举所有板块文件
    files = [f for f in os.listdir(block_dir) if f.endswith(".dat") or f.endswith(".bk2")]
    print(f"找到 {len(files)} 个板块文件:")
    for f in sorted(files):
        fpath = os.path.join(block_dir, f)
        fsize = os.path.getsize(fpath)
        print(f"  {f} ({fsize} bytes)")

    # 尝试用 pytdx 解析
    try:
        from pytdx.reader import BlockReader
        reader = BlockReader()
        for f in files:
            fpath = os.path.join(block_dir, f)
            try:
                result = reader.get_df(fpath)
                if result is not None and len(result) > 0:
                    print(f"\n{f} 内容 ({len(result)} 只):")
                    for _, r in result.head(10).iterrows():
                        print(f"  {r.get('code','?')} {r.get('name','?')}")
                    if len(result) > 10:
                        print(f"  ... 共 {len(result)} 只")
            except:
                pass
    except ImportError:
        print("\n提示: 安装 pytdx 后可解析 .dat 文件格式")


def main():
    parser = argparse.ArgumentParser(description="通达信数据同步工具")
    sub = parser.add_subparsers(dest="command", required=True)

    # test
    sub.add_parser("test", help="测试 pytdx 连接")

    # quote
    p_q = sub.add_parser("quote", help="获取个股行情")
    p_q.add_argument("--code", required=True)

    # import
    p_i = sub.add_parser("import", help="导入通达信导出自选股CSV")
    p_i.add_argument("--file", required=True)
    p_i.add_argument("--pool", choices=["selected", "watch"], default="watch")

    # t0002
    p_t = sub.add_parser("t0002", help="读取通达信本地自选股")
    p_t.add_argument("--path", help="通达信安装目录")

    args = parser.parse_args()

    if args.command == "test":
        cmd_test(args)
    elif args.command == "quote":
        cmd_quote(args)
    elif args.command == "import":
        cmd_import(args)
    elif args.command == "t0002":
        cmd_t0002(args)


if __name__ == "__main__":
    main()