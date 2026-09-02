#!/usr/bin/env python3
"""
通达信选股公式生成器

将 trading-combo 策略转化为通达信可执行的选股公式文件。

支持生成:
  .tn6 — 条件选股公式（可在通达信"条件选股"中直接运行）
  .tni — 技术指标公式（可在通达信K线图中显示）
  .csv — 选股结果CSV（直接导入板块）

用法:
  formula_generator.py list                          # 列出可选策略
  formula_generator.py generate <strategy>            # 生成公式文件
  formula_generator.py generate <strategy> --tdx-dir <通达信路径>  # 指定输出目录
  formula_generator.py csv <strategy>                 # 生成CSV选股结果
"""
import argparse
import csv
import os
import sys
from datetime import datetime

# ── 路径 ──
SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(SKILL_DIR, "formulas")

# ── 策略库 ──
STRATEGIES = {
    "trend_resonance": {
        "name": "趋势共振选股",
        "desc": "均线多头+MACD0轴上方金叉（trading-combo A级评分核心条件）",
        "type": "tn6",
        "formula": """
// ==========================================
// 趋势共振选股
// 来源: trading-combo 策略
// 条件: 均线多头 + MACD0轴上方 + 成交量确认
// ==========================================

// ---- 均线定义 ----
MA5:=MA(CLOSE,5);
MA10:=MA(CLOSE,10);
MA20:=MA(CLOSE,20);
MA60:=MA(CLOSE,60);

// ---- MACD定义 ----
DIF:="MACD.DIF"(#DAY);
DEA:="MACD.DEA"(#DAY);
MACD:="MACD.MACD"(#DAY);

// ---- 成交量定义 ----
VOL5:=MA(VOL,5);

// ---- 核心条件 ----
// 1. 均线多头排列
多头排列:=MA5>MA10 AND MA10>MA20 AND MA20>MA60;
// 2. MACD在0轴上方
MACD强势:=DIF>0;
// 3. MACD金叉或DIF>DEA
MACD金叉:=CROSS(DIF,DEA) OR DIF>DEA;
// 4. 成交量不异常萎缩
量能充足:=VOL>VOL5*0.6;
// 5. 非ST
非ST:=NAMELIKE('ST')=0 AND NAMELIKE('*ST')=0;
// 6. 股价在MA20上方
价在线上:=CLOSE>MA20;

// ---- 选股条件 ----
选股:多头排列 AND MACD强势 AND MACD金叉 AND 量能充足 AND 非ST AND 价在线上;
""",
    },
    "pullback_buy": {
        "name": "缩量回踩买入",
        "desc": "回踩MA20不破+缩量（符合当前小步上涨市场特征）",
        "type": "tn6",
        "formula": """
// ==========================================
// 缩量回踩买入
// 来源: trading-combo 策略
// 适用: 结构性分化市场，不追高
// ==========================================

MA5:=MA(CLOSE,5);
MA10:=MA(CLOSE,10);
MA20:=MA(CLOSE,20);
MA60:=MA(CLOSE,60);

VOL5:=MA(VOL,5);
VOL10:=MA(VOL,10);

// ---- 核心条件 ----
// 1. 趋势向上（MA20>MA60为中期趋势向上）
中期向上:=MA20>MA60;
// 2. 回踩MA20不破（最低价接近MA20但收盘在MA20上方）
回踩不破:=LOW<MA20*1.02 AND CLOSE>MA20;
// 3. 缩量（成交量萎缩至5日均量的60%~90%）
缩量:=VOL<VOL5*0.9 AND VOL>VOL5*0.5;
// 4. MACD在0轴附近或上方
DIF:="MACD.DIF"(#DAY);
MACD不弱:=DIF>-0.5;
// 5. 非ST
非ST:=NAMELIKE('ST')=0 AND NAMELIKE('*ST')=0;

// ---- 选股条件 ----
选股:中期向上 AND 回踩不破 AND 缩量 AND MACD不弱 AND 非ST;
""",
    },
    "macd_second_golden": {
        "name": "MACD二次金叉",
        "desc": "零轴附近第二次金叉（底部反转信号）",
        "type": "tn6",
        "formula": """
// ==========================================
// MACD二次金叉选股
// 来源: macd-second-golden-cross skill
// 条件: 水下二次金叉 + DIF低点抬高
// ==========================================

DIF:="MACD.DIF"(#DAY);
DEA:="MACD.DEA"(#DAY);

// 第一次金叉（回溯20天内）
金叉1:=COUNT(CROSS(DIF,DEA),20)>=1;
// 第二次金叉
金叉2:=CROSS(DIF,DEA);
// 第二次金叉位置高于第一次
REFDIF1:=REF(DIF,BARSLAST(CROSS(DIF,DEA))+1);
位置抬高:=DIF>REFDIF1;
// 仍在零轴附近
零轴附近:=DIF<0.5;
// 非ST
非ST:=NAMELIKE('ST')=0 AND NAMELIKE('*ST')=0;

// ---- 选股条件 ----
选股:金叉1 AND 金叉2 AND 位置抬高 AND 零轴附近 AND 非ST;
""",
    },
    "combo_score": {
        "name": "综合评分排序",
        "desc": "技术指标公式，在K线图上显示综合评分（满分100）",
        "type": "tni",
        "formula": """
// ==========================================
// 综合评分排序（技术指标）
// 来源: trading-combo 策略评分卡
// 在K线图底部显示各维度评分
// ==========================================

// ---- 均线结构评分（满分25）----
MA5:=MA(CLOSE,5);
MA10:=MA(CLOSE,10);
MA20:=MA(CLOSE,20);
MA60:=MA(CLOSE,60);

// 每一条多头关系+5分
均线分:=IF(MA5>MA10,5,0)+IF(MA10>MA20,5,0)+IF(MA20>MA60,5,0)+IF(CLOSE>MA20,5,0)+IF(MA5>MA60,5,0);

// ---- MACD状态评分（满分20）----
DIF:="MACD.DIF"(#DAY);
DEA:="MACD.DEA"(#DAY);
MACD分:=IF(DIF>0,10,0)+IF(DIF>DEA,10,0);

// ---- 成交量评分（满分15）----
VOL5:=MA(VOL,5);
量能分:=IF(VOL<VOL5*0.9 AND VOL>VOL5*0.5,15,IF(VOL<VOL5*1.2,10,0));

// ---- 综合评分 ----
评分:均线分+MACD分+量能分;

// 评分区间标注
DRAWTEXT(评分>=85, HIGH*1.02, 'A级'), COLORRED;
DRAWTEXT(评分>=70 AND 评分<85, HIGH*1.02, 'B级'), COLORLIBLUE;
DRAWTEXT(评分>=55 AND 评分<70, HIGH*1.02, 'C级'), COLORGREEN;
DRAWTEXT(评分<55, HIGH*1.02, 'D级'), COLORGRAY;
""",
    },
}


def _ensure_dir(path):
    os.makedirs(path, exist_ok=True)


def _find_tdx_dir():
    """自动查找通达信安装目录"""
    candidates = [
        "/mnt/c/Program Files (x86)/TDX",
        "/mnt/c/Program Files (x86)/通达信",
        "/mnt/c/Program Files/TDX",
        "/mnt/c/Program Files/通达信",
        "/mnt/c/TDX",
    ]
    for p in candidates:
        if os.path.exists(p):
            t0002 = os.path.join(p, "T0002")
            if os.path.exists(t0002):
                return p
    return None


def cmd_list(args):
    """列出所有可选策略"""
    print("\n可选策略公式:")
    print("=" * 60)
    for key, s in STRATEGIES.items():
        print(f"  {key:<25} {s['name']:<16} [{s['type'].upper()}]")
        print(f"  {'':<25} {s['desc']}")
        print()


def cmd_generate(args):
    """生成公式文件"""
    strategy_name = args.strategy
    if strategy_name not in STRATEGIES:
        print(f"✗ 未知策略: {strategy_name}")
        print(f"  可用策略: {', '.join(STRATEGIES.keys())}")
        return

    strategy = STRATEGIES[strategy_name]
    ext = strategy["type"]

    # 确定输出目录
    if args.tdx_dir:
        tdx_dir = args.tdx_dir
        if ext == "tn6":
            out_dir = os.path.join(tdx_dir, "T0002", "user", "条件选股")
        elif ext == "tni":
            out_dir = os.path.join(tdx_dir, "T0002", "user")
        else:
            out_dir = os.path.join(tdx_dir, "T0002", "user")
        print(f"  输出到通达信目录: {out_dir}")
    else:
        out_dir = os.path.join(OUTPUT_DIR, ext)
        print(f"  输出到: {out_dir}")

    _ensure_dir(out_dir)

    filename = f"{strategy_name}.{ext}"
    filepath = os.path.join(out_dir, filename)

    # 构造完整公式文件
    if ext == "tn6":
        content = f"""[General]
Name={strategy['name']}
Type=条件选股
{strategy['formula']}
"""
    elif ext == "tni":
        content = f"""[General]
Name={strategy['name']}
Type=技术指标
{strategy['formula']}
"""
    else:
        content = strategy["formula"]

    # 按通达信要求用GBK编码
    with open(filepath, "w", encoding="gbk", errors="replace") as f:
        f.write(content.strip())

    print(f"✓ 生成成功: {filepath}")
    print(f"  名称: {strategy['name']}")
    print(f"  类型: {ext.upper()}")
    print()

    if args.tdx_dir:
        print("  下一步: 重启通达信 → Ctrl+F 打开公式管理器")
        if ext == "tn6":
            print("           → 条件选股标签 → 选择刚导入的公式 → 执行选股")
        elif ext == "tni":
            print("           → 技术指标标签 → 选择刚导入的公式 → 应用到K线图")
    else:
        print(f"  文件已保存到: {out_dir}")
        print("  需要复制到通达信对应目录才能使用")


def cmd_generate_all(args):
    """生成所有策略公式"""
    tdx_dir = args.tdx_dir
    for key in STRATEGIES:
        args.strategy = key
        cmd_generate(args)


def cmd_csv(args):
    """生成选股结果CSV（可直接在通达信中导入板块）"""
    strategy_name = args.strategy
    if strategy_name not in STRATEGIES:
        print(f"✗ 未知策略: {strategy_name}")
        return

    strategy = STRATEGIES[strategy_name]
    print(f"生成CSV选股结果: {strategy['name']}")
    print()
    print("  ⚠ CSV模式需要先获取全市场数据并应用策略筛选")
    print("  推荐流程:")
    print(f"  1. 在通达信中运行条件选股公式 '{strategy['name']}'")
    print(f"  2. 选股结果 → 右键 → 导出到CSV")
    print(f"  3. 通过 tdx_sync.py import 导入到关注/自选股池")
    print()
    print(f"  或直接通过 a-share-data 获取全市场数据后筛选:")
    print(f"  $VENV_PY a-share-data/scripts/fetch_patched.py fetch_realtime.py --all-quote --json")
    print(f"  | python3 -c \"筛选逻辑...\" > 选股结果.csv")


def main():
    parser = argparse.ArgumentParser(description="通达信选股公式生成器")
    sub = parser.add_subparsers(dest="command", required=True)

    # list
    sub.add_parser("list", help="列出可选策略")

    # generate
    p_gen = sub.add_parser("generate", help="生成公式文件")
    p_gen.add_argument("strategy", nargs="?", help="策略名称（留空生成全部）")
    p_gen.add_argument("--tdx-dir", help="通达信安装目录（指定后直接输出到公式目录）")

    # csv
    p_csv = sub.add_parser("csv", help="生成选股结果CSV说明")
    p_csv.add_argument("strategy", help="策略名称")

    args = parser.parse_args()

    if args.command == "list":
        cmd_list(args)
    elif args.command == "generate":
        if args.strategy:
            cmd_generate(args)
        else:
            # 生成全部
            tdx_dir = args.tdx_dir or _find_tdx_dir()
            if tdx_dir:
                print(f"检测到通达信目录: {tdx_dir}")
            else:
                print("未检测到通达信安装，公式将保存到 formulas/ 目录")
            args.tdx_dir = tdx_dir
            cmd_generate_all(args)
    elif args.command == "csv":
        cmd_csv(args)


if __name__ == "__main__":
    main()