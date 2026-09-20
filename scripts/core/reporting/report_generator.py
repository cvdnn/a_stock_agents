"""
aStocks HTML 报告生成器

基于 stock-report-html 标准样式模板生成可视化报告。
输出: 白色亚光背景 · 涨红跌绿 · 960px居中 · 自包含单文件
"""

import html as html_lib
import json
import sys
import os
from pathlib import Path
from datetime import datetime

SCRIPT_DIR = Path(__file__).resolve().parent
from core.config import PROJECT_ROOT, OUTPUT_REPORTS_DIR
from core.strategy.execution_action_engine import ExecutionActionEngine

def _resolve_template_path() -> Path:
    """自适应查找并解析 HTML 报告模板路径"""
    candidate_paths = [
        PROJECT_ROOT / ".agents" / "skills" / "astock-data-feed" / "templates" / "stock-report.html",
        PROJECT_ROOT / "skills" / "astock-data-feed" / "templates" / "stock-report.html",
        PROJECT_ROOT / "skills" / "a-share-data" / "templates" / "stock-report.html",
    ]
    for p in candidate_paths:
        if p.exists():
            return p
    return candidate_paths[0]

TEMPLATE_PATH = _resolve_template_path()


def _sanitize_report_output_path(output_path: str) -> Path:
    """Ensure report output path is safely sandboxed within an authorized directory.

    允许的输出位置（三桶规范）：
      1) output/reports/        — 用户最终交付物唯一落盘区
      2) temp/                  — 可重建中间产物暂存区（含 verify 自检产物、LLM 草稿）
    其它任意系统路径一律重定向到 output/reports/，防止 LLM 写出沙箱。
    """
    out_p = Path(output_path)
    clean_name = out_p.name
    resolved_out = (PROJECT_ROOT / out_p).resolve() if not out_p.is_absolute() else out_p.resolve()
    # 解析 temp/（可能已被环境变量 A_STOCK_TEMP_DIR 覆盖）
    try:
        from core.config import TEMP_DIR
        temp_root = TEMP_DIR.resolve()
    except Exception:
        temp_root = (PROJECT_ROOT / "temp").resolve()
    allowed_subdirs = [
        (PROJECT_ROOT / "output" / "reports").resolve(),
        OUTPUT_REPORTS_DIR.resolve(),
        temp_root,
    ]
    for r_dir in allowed_subdirs:
        try:
            resolved_out.relative_to(r_dir)
            return resolved_out
        except ValueError:
            pass
    return (OUTPUT_REPORTS_DIR / clean_name).resolve()


def generate_simple_report(data: dict, output_path: str = None) -> str:
    """生成符合 astock-report-html 规范的标准自包含 HTML 投研报告"""
    raw_code = data.get("code", "000001")
    raw_name = data.get("name", raw_code)
    code = html_lib.escape(str(raw_code))
    name = html_lib.escape(str(raw_name))

    quote = data.get("quote") or {}
    scores = data.get("scores") or {}
    tech = data.get("technical_latest") or {}
    entry = data.get("entry") or {}
    gaps = data.get("gaps") or {}

    now_dt = datetime.now()
    timestamp_str = now_dt.strftime("%Y-%m-%d %H:%M")
    date_str = now_dt.strftime("%Y-%m-%d")

    # 现价与涨跌
    curr_price = float(quote.get("price") or tech.get("close") or 10.0)
    chg_pct = float(quote.get("change_pct") or 0.0)
    chg_sign = "+" if chg_pct >= 0 else ""
    chg_class = "up" if chg_pct >= 0 else "down"

    # 评级与打分
    raw_rating = str(scores.get("rating", "B")).upper()
    rating = html_lib.escape(raw_rating)
    rating_text = html_lib.escape(str(scores.get("rating_text", "")))
    total_score = scores.get("total", 60)
    max_total = scores.get("max_total", 100)

    # ① 精确实战保本价 (严格向上进位到 0.01 分位)
    cost = float(data.get("cost") or curr_price)
    shares = int(data.get("shares") or 100)
    breakeven_price = ExecutionActionEngine.calc_min_breakeven_price(cost=cost, shares=shares)

    # ② 三级止损位计算
    stop_t0 = round(cost * 0.97, 2)
    stop_t1 = round(cost * 0.95, 2)
    stop_t2 = round(cost * 0.92, 2)

    # ③ 三场景即时操作单
    ma20_val = float(tech.get("ma20") or curr_price)
    ma10_val = float(tech.get("ma10") or curr_price)

    scenario_high = f"若早盘冲高至 {max(ma10_val, curr_price * 1.02):.2f} 附近受阻且无量，逢高减仓兑现；放量站稳方可降级观察。"
    scenario_flat = f"若盘中在 {curr_price:.2f} 附近窄幅缩量震荡，持仓者持股防守，场外不盲目左侧建仓。"
    scenario_drop = f"若跳水急跌击穿 T0警戒线 {stop_t0:.2f} 启动减仓对冲预案；破 T1减仓线 {stop_t1:.2f} 减半仓；破 T2绝杀线 {stop_t2:.2f} 无条件离场。"

    # 评分维度明细行
    rows_html = ""
    for dim, info in scores.items():
        if not isinstance(info, dict) or "score" not in info or "max" not in info:
            continue
        dim_esc = html_lib.escape(str(dim))
        reason_esc = html_lib.escape(str(info.get("reason", "")))
        score_val = info.get("score", 0)
        max_val = info.get("max", 0)
        score_class = "down" if (score_val / max(max_val, 1)) < 0.4 else ("up" if (score_val / max(max_val, 1)) >= 0.7 else "")
        rows_html += f"""
        <tr>
          <td><b>{dim_esc}</b></td>
          <td class="{score_class}">{score_val} / {max_val}</td>
          <td style="color:#5a6070">{reason_esc}</td>
        </tr>"""

    if not rows_html:
        rows_html = """
        <tr><td>均线结构 (MA)</td><td>--</td><td>多空趋势综合研判</td></tr>
        <tr><td>MACD指标动能</td><td>--</td><td>零轴强弱与背离特征</td></tr>
        <tr><td>量价配合度</td><td>--</td><td>换手与成交量沉淀</td></tr>
        """

    # 顶栏统计卡片
    header_stats_html = f"""
    <div class="hdr-stat">
      <div class="l">现价 / 涨跌幅</div>
      <div class="v {chg_class}">{curr_price:.2f} ({chg_sign}{chg_pct:.2f}%)</div>
      <div class="s">今开 {quote.get('open', curr_price)} · 昨收 {quote.get('prev_close', curr_price)}</div>
    </div>
    <div class="hdr-stat">
      <div class="l">量化综合评级</div>
      <div class="v {'up' if rating in ('A', 'B') else 'down'}">{rating}</div>
      <div class="s">{rating_text or '多因子研判'}</div>
    </div>
    <div class="hdr-stat">
      <div class="l">多因子总评分</div>
      <div class="v {'up' if total_score >= 60 else 'down'}">{total_score} <span style="font-size:11px;color:#8a909e">/{max_total}</span></div>
      <div class="s">建议仓位: {scores.get('suggested_position', '适度配置')}</div>
    </div>
    <div class="hdr-stat">
      <div class="l">最低保本卖出价</div>
      <div class="v blue">{breakeven_price:.2f}</div>
      <div class="s">含全部摩擦税费·强制进位</div>
    </div>
    """

    # 报告主体 CONTENT
    content_html = f"""
    <!-- 实时行情与综合诊断卡片 -->
    <div class="section">
      <div class="sec-title">📈 实时行情与基础指标</div>
      <div class="card">
        <table class="tbl">
          <tr>
            <th>指标项</th><th>数值</th><th>指标项</th><th>数值</th>
          </tr>
          <tr>
            <td>最新价</td><td class="{chg_class}"><b>{curr_price:.2f}</b> ({chg_sign}{chg_pct:.2f}%)</td>
            <td>最高 / 最低</td><td>{quote.get('high', curr_price)} / {quote.get('low', curr_price)}</td>
          </tr>
          <tr>
            <td>换手率</td><td>{quote.get('turnover_pct', quote.get('turnover', '--'))}%</td>
            <td>成交额</td><td>{quote.get('amount', quote.get('turnover_val', '--'))}</td>
          </tr>
          <tr>
            <td>市盈率 PE(TTM)</td><td>{quote.get('pe') if quote.get('pe') is not None else '--'}</td>
            <td>总市值</td><td>{quote.get('total_market_cap', '--')} 亿</td>
          </tr>
        </table>
      </div>
    </div>

    <!-- 实战交易三原则 (铁律指令) -->
    <div class="section">
      <div class="sec-title">🛡️ 实战交易三原则（核心反应中枢）</div>
      <div class="card" style="border-left: 4px solid #2563eb;">
        <div style="margin-bottom: 14px;">
          <span class="tag tag-blue" style="font-size:12px; padding:2px 8px;">① 精确最低保本卖出价</span>
          <span style="font-size:20px; font-weight:800; font-family:var(--font-mono); margin-left:10px; color:#2563eb;">
            ¥ {breakeven_price:.2f}
          </span>
          <span style="font-size:12px; color:#8a909e; margin-left:8px;">(买入成本 ¥{cost:.2f} · {shares}股，含印花税0.05%、佣金最低5元、过户费，强制进位至分位)</span>
        </div>

        <div style="margin-bottom: 16px;">
          <div style="font-size:13px; font-weight:600; margin-bottom:8px; color:#5a6070;">② 三级风控止损阶梯</div>
          <table class="tbl">
            <tr>
              <th>风控级别</th><th>触发价位</th><th>预警跌幅</th><th>刚性执行动作</th>
            </tr>
            <tr>
              <td><span class="tag tag-ylw">T0 警戒线</span></td>
              <td class="down" style="font-weight:700;">¥ {stop_t0:.2f}</td>
              <td class="down">-3.0%</td>
              <td>准备减仓或对冲，高度警惕形态破位</td>
            </tr>
            <tr>
              <td><span class="tag tag-ylw">T1 减仓线</span></td>
              <td class="down" style="font-weight:700;">¥ {stop_t1:.2f}</td>
              <td class="down">-5.0%</td>
              <td>减仓 50%，保本防守，剥离脆弱敞口</td>
            </tr>
            <tr>
              <td><span class="tag tag-down">T2 绝杀线</span></td>
              <td class="down" style="font-weight:700;">¥ {stop_t2:.2f}</td>
              <td class="down">-8.0%</td>
              <td>无条件市价清仓出局，严禁逆势补仓扛单</td>
            </tr>
          </table>
        </div>

        <div>
          <div style="font-size:13px; font-weight:600; margin-bottom:8px; color:#5a6070;">③ 三场景即时操作单</div>
          <div class="info-box blue" style="margin-bottom:6px;">
            <b>🌞 场景一：开盘冲高</b> —— {scenario_high}
          </div>
          <div class="info-box ylw" style="margin-bottom:6px;">
            <b>🌤 场景二：盘中窄幅震荡</b> —— {scenario_flat}
          </div>
          <div class="info-box red">
            <b>🌧 场景三：跳水急跌破位</b> —— {scenario_drop}
          </div>
        </div>
      </div>
    </div>

    <!-- 策略多因子量化评分 -->
    <div class="section">
      <div class="sec-title">🎯 多因子量化评分明细（100分制模型）</div>
      <div class="card">
        <table class="tbl">
          <thead>
            <tr><th>评估维度</th><th>得分/权重</th><th>诊断依据与说明</th></tr>
          </thead>
          <tbody>
            {rows_html}
          </tbody>
        </table>
        <div style="margin-top:12px; text-align:right;">
          <span class="tag {'tag-up' if total_score >= 60 else 'tag-down'}" style="font-size:12px; padding:4px 10px;">
            综合评级：{rating} ({rating_text or '量化审定'}) · 建议仓位: {scores.get('suggested_position', '观望/防守')}
          </span>
        </div>
      </div>
    </div>

    <!-- 核心技术形态 -->
    <div class="section">
      <div class="sec-title">📊 核心技术形态指标</div>
      <div class="card">
        <table class="tbl">
          <tr><th>指标分类</th><th>当前读数</th><th>指标分类</th><th>当前读数</th></tr>
          <tr>
            <td>均线 MA5 / MA10</td><td>{tech.get('ma5', '--')} / {tech.get('ma10', '--')}</td>
            <td>均线 MA20 / MA60</td><td>{tech.get('ma20', '--')} / {tech.get('ma60', '--')}</td>
          </tr>
          <tr>
            <td>MACD (DIF / DEA)</td><td>{tech.get('dif', '--')} / {tech.get('dea', '--')}</td>
            <td>MACD 柱 (Hist)</td><td>{tech.get('macd_bar', tech.get('hist', '--'))}</td>
          </tr>
          <tr>
            <td>KDJ (K / D / J)</td><td>{tech.get('kdj_k', '--')} / {tech.get('kdj_d', '--')} / {tech.get('kdj_j', '--')}</td>
            <td>RSI (14) / ATR (14)</td><td>{tech.get('rsi', '--')} / {tech.get('atr', '--')}</td>
          </tr>
          <tr>
            <td>BOLL 上轨 / 中轨</td><td>{tech.get('boll_upper', '--')} / {tech.get('boll_mid', '--')}</td>
            <td>BOLL 下轨</td><td>{tech.get('boll_lower', '--')}</td>
          </tr>
        </table>
      </div>
    </div>

    <!-- 策略轨迹时间线 -->
    <div class="section">
      <div class="sec-title">⏱️ 投研轨迹记录</div>
      <div class="card">
        <div class="tl">
          <div class="tl-item">
            <div class="tl-time">{date_str} {now_dt.strftime("%H:%M")}</div>
            <div class="tl-head"><span class="tag tag-up">量化综合审定</span> 完成 {name}({code}) 多因子体检与实战决议</div>
            <div class="tl-body">现价 {curr_price:.2f} 元，评级 {rating}。已建立三级风控防御线与精确向上进位保本价 ¥{breakeven_price:.2f}。</div>
          </div>
        </div>
      </div>
    </div>
    """

    footer_text = f"aStocks 量化投研中枢 · 生成于 {timestamp_str} · 数据来源: 4级降级实时行情管线 · 市场有风险，入市需谨慎"

    # 尝试使用原生模板
    if TEMPLATE_PATH.exists():
        try:
            tpl_str = TEMPLATE_PATH.read_text(encoding="utf-8")
            html_out = (
                tpl_str
                .replace("{{TITLE}}", f"{raw_name}({raw_code}) 量化投研分析报告")
                .replace("{{DATE}}", date_str)
                .replace("{{HEADER_TAG}}", f"量化实战评估 · {date_str}")
                .replace("{{MAIN_TITLE}}", f"{raw_name} ({raw_code}) 投研报告")
                .replace("{{SUB_TITLE}}", f"现价 {curr_price:.2f} ({chg_sign}{chg_pct:.2f}%) · 评级 {rating} · 综合评分 {total_score}/100")
                .replace("{{HEADER_STATS}}", header_stats_html)
                .replace("{{CONTENT}}", content_html)
                .replace("{{FOOTER_TEXT}}", footer_text)
            )
            if output_path:
                safe_path = _sanitize_report_output_path(output_path)
                safe_path.parent.mkdir(parents=True, exist_ok=True)
                safe_path.write_text(html_out, encoding="utf-8")
                print(f"报告已保存: {safe_path}")
            return html_out
        except Exception as exc:
            print(f"模板渲染异常，使用自包含内建模板: {exc}")

    # 自包含 1344px 降级模板 (确保 100% 成功输出)
    html_fallback = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{name}({code}) 量化投研分析报告 | {date_str}</title>
<style>
  :root {{
    --bg-page: #f4f5f7;
    --bg-card: #ffffff;
    --bg-card-hover: #fafbfc;
    --border: #d8dce3;
    --text-primary: #1a1d24;
    --text-secondary: #5a6070;
    --text-muted: #8a909e;
    --up: #d0312d;
    --down: #219653;
    --accent-blue: #2563eb;
    --font: -apple-system, BlinkMacSystemFont, 'PingFang SC', 'Microsoft YaHei', sans-serif;
    --font-mono: 'SF Mono', Consolas, 'JetBrains Mono', monospace;
  }}
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ background:var(--bg-page); color:var(--text-primary); font-family:var(--font); min-height:100vh; }}
  .header {{ background:linear-gradient(135deg,#eef0f4 0%,#e2e6ed 100%); border-bottom:1px solid var(--border); padding:28px 40px 22px; }}
  .header-inner {{ display:flex; justify-content:space-between; align-items:flex-start; max-width:1344px; margin:0 auto; flex-wrap:wrap; gap:12px; }}
  .hdr-stats {{ display:flex; gap:14px; flex-wrap:wrap; }}
  .hdr-stat {{ text-align:center; padding:6px 14px; background:rgba(255,255,255,.8); border:1px solid var(--border); border-radius:4px; min-width:80px; }}
  .hdr-stat .l {{ font-size:10px; color:var(--text-muted); margin-bottom:1px; }}
  .hdr-stat .v {{ font-size:16px; font-weight:700; font-family:var(--font-mono); }}
  .hdr-stat .s {{ font-size:11px; color:var(--text-secondary); }}
  .container {{ max-width:1344px; margin:0 auto; padding:20px 24px 40px; }}
  .section {{ margin-bottom:20px; }}
  .sec-title {{ font-size:14px; font-weight:600; color:var(--text-secondary); margin-bottom:10px; }}
  .card {{ background:var(--bg-card); border:1px solid var(--border); border-radius:8px; padding:18px 20px; margin-bottom:12px; }}
  table.tbl {{ width:100%; border-collapse:collapse; font-size:13px; }}
  table.tbl th {{ text-align:left; padding:8px 10px; font-size:12px; font-weight:600; color:var(--text-muted); border-bottom:1px solid var(--border); }}
  table.tbl td {{ padding:8px 10px; border-bottom:1px solid rgba(216,227,227,.5); font-family:var(--font-mono); font-size:13px; }}
  .tag {{ display:inline-block; padding:2px 6px; border-radius:3px; font-size:11px; font-weight:600; }}
  .tag-up {{ background:rgba(208,49,45,0.08); color:var(--up); }}
  .tag-down {{ background:rgba(33,150,83,0.08); color:var(--down); }}
  .tag-blue {{ background:rgba(37,99,235,0.08); color:var(--accent-blue); }}
  .tag-ylw {{ background:rgba(184,134,11,0.08); color:#b8860b; }}
  .up {{ color:var(--up); }}
  .down {{ color:var(--down); }}
  .blue {{ color:var(--accent-blue); }}
  .info-box {{ padding:10px 14px; border-radius:6px; font-size:13px; line-height:1.5; margin-top:6px; }}
  .info-box.blue {{ background:rgba(37,99,235,0.04); border:1px solid rgba(37,99,235,0.15); }}
  .info-box.ylw {{ background:rgba(184,134,11,0.04); border:1px solid rgba(184,134,11,0.15); }}
  .info-box.red {{ background:rgba(208,49,45,0.04); border:1px solid rgba(208,49,45,0.15); }}
  .footer {{ text-align:center; padding:18px; color:var(--text-muted); font-size:11px; border-top:1px solid var(--border); margin-top:20px; }}
</style>
</head>
<body>
<div class="header">
  <div class="header-inner">
    <div>
      <h1 style="font-size:22px; font-weight:700;">{name} ({code}) 投研报告</h1>
      <div style="font-size:13px; color:var(--text-secondary); margin-top:4px;">现价 {curr_price:.2f} ({chg_sign}{chg_pct:.2f}%) · 评级 {rating} · 生成于 {timestamp_str}</div>
    </div>
    <div class="hdr-stats">
      {header_stats_html}
    </div>
  </div>
</div>
<div class="container">
  {content_html}
  <div class="footer">{footer_text}</div>
</div>
</body>
</html>
"""
    if output_path:
        safe_path = _sanitize_report_output_path(output_path)
        safe_path.parent.mkdir(parents=True, exist_ok=True)
        safe_path.write_text(html_fallback, encoding="utf-8")
        print(f"报告已保存: {safe_path}")

    return html_fallback


def markdown_to_html_body(md_text: str) -> str:
    """Zero-dependency markdown to clean semantic HTML converter for reports."""
    import re
    lines = md_text.strip().splitlines()
    html_lines = []
    in_table = False
    table_rows = []
    in_list = False
    in_code = False
    code_lines = []

    def inline_format(txt: str) -> str:
        txt = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', txt)
        txt = re.sub(r'`(.+?)`', r'<code style="background:rgba(0,0,0,0.05);padding:2px 5px;border-radius:3px;font-family:var(--font-mono);font-size:12px;">\1</code>', txt)
        txt = re.sub(r'(\+[0-9.]+(?:%)?)', r'<span class="up">\1</span>', txt)
        txt = re.sub(r'(-[0-9.]+(?:%)?)', r'<span class="down">\1</span>', txt)
        return txt

    def flush_table():
        nonlocal in_table, table_rows
        if not table_rows:
            in_table = False
            return ""
        out = ['<div class="card"><table class="tbl">']
        is_first = True
        for row in table_rows:
            if re.match(r'^\s*\|?(\s*:?-+:?\s*\|?)+\s*$', row):
                continue
            cols = [c.strip() for c in row.strip().strip('|').split('|')]
            if is_first:
                out.append('<thead><tr>' + ''.join(f'<th>{inline_format(c)}</th>' for c in cols) + '</tr></thead><tbody>')
                is_first = False
            else:
                out.append('<tr>' + ''.join(f'<td>{inline_format(c)}</td>' for c in cols) + '</tr>')
        if not is_first:
            out.append('</tbody>')
        out.append('</table></div>')
        in_table = False
        table_rows = []
        return '\n'.join(out)

    for line in lines:
        stripped = line.strip()

        if stripped.startswith('```'):
            if in_code:
                html_lines.append('<pre style="background:#1e293b;color:#e2e8f0;padding:14px;border-radius:6px;overflow-x:auto;font-family:var(--font-mono);font-size:12px;"><code>' + html_lib.escape('\n'.join(code_lines)) + '</code></pre>')
                code_lines = []
                in_code = False
            else:
                if in_table:
                    html_lines.append(flush_table())
                if in_list:
                    html_lines.append('</ul>')
                    in_list = False
                in_code = True
            continue

        if in_code:
            code_lines.append(line)
            continue

        if '|' in stripped and not stripped.startswith('#'):
            if in_list:
                html_lines.append('</ul>')
                in_list = False
            in_table = True
            table_rows.append(stripped)
            continue
        elif in_table:
            html_lines.append(flush_table())

        if not stripped:
            if in_list:
                html_lines.append('</ul>')
                in_list = False
            continue

        if stripped in ('---', '***', '___'):
            if in_list:
                html_lines.append('</ul>')
                in_list = False
            html_lines.append('<hr style="border:none;border-top:1px solid var(--border);margin:20px 0;">')
            continue

        if stripped.startswith('# '):
            if in_list:
                html_lines.append('</ul>')
                in_list = False
            html_lines.append(f'<div class="sec-title" style="font-size:18px;font-weight:700;color:var(--text-primary);margin-top:20px;">{inline_format(stripped[2:])}</div>')
            continue
        if stripped.startswith('## '):
            if in_list:
                html_lines.append('</ul>')
                in_list = False
            html_lines.append(f'<div class="sec-title" style="font-size:15px;font-weight:600;color:var(--text-primary);margin-top:18px;">{inline_format(stripped[3:])}</div>')
            continue
        if stripped.startswith('### '):
            if in_list:
                html_lines.append('</ul>')
                in_list = False
            html_lines.append(f'<div style="font-size:14px;font-weight:600;color:var(--text-secondary);margin-top:14px;margin-bottom:6px;">{inline_format(stripped[4:])}</div>')
            continue

        if stripped.startswith('> '):
            if in_list:
                html_lines.append('</ul>')
                in_list = False
            content = inline_format(stripped[2:])
            html_lines.append(f'<div class="info-box blue" style="margin:10px 0;">{content}</div>')
            continue

        if stripped.startswith('- ') or stripped.startswith('* '):
            if not in_list:
                html_lines.append('<ul style="margin:8px 0 12px 24px;font-size:13px;line-height:1.7;">')
                in_list = True
            html_lines.append(f'<li style="margin-bottom:4px;">{inline_format(stripped[2:])}</li>')
            continue

        if in_list:
            html_lines.append('</ul>')
            in_list = False
        html_lines.append(f'<p style="font-size:13.5px;line-height:1.7;margin-bottom:10px;">{inline_format(stripped)}</p>')

    if in_table:
        html_lines.append(flush_table())
    if in_list:
        html_lines.append('</ul>')
    if in_code:
        html_lines.append('<pre style="background:#1e293b;color:#e2e8f0;padding:14px;border-radius:6px;overflow-x:auto;font-family:var(--font-mono);font-size:12px;"><code>' + html_lib.escape('\n'.join(code_lines)) + '</code></pre>')

    return '\n'.join(html_lines)


def wrap_markdown_as_html_report(markdown_text: str, title: str = "", filename: str = "") -> str:
    """将 Markdown 文本包装转化为符合 astock-report-html 视觉规范的自包含标准 HTML 单文件报告。"""
    clean_title = title or filename or "A-Stock 量化投研分析报告"
    if "<!DOCTYPE html" in markdown_text or ("<html" in markdown_text and "</html>" in markdown_text):
        return markdown_text

    now_dt = datetime.now()
    timestamp_str = now_dt.strftime("%Y-%m-%d %H:%M")
    body_html = markdown_to_html_body(markdown_text)

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{html_lib.escape(clean_title)}</title>
<style>
  :root {{
    --bg-page: #f4f5f7;
    --bg-card: #ffffff;
    --border: #d8dce3;
    --border-accent: #b8bcc8;
    --text-primary: #1a1d24;
    --text-secondary: #5a6070;
    --text-muted: #8a909e;
    --up: #d0312d;
    --down: #219653;
    --accent-blue: #2563eb;
    --font: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif;
    --font-mono: 'SF Mono', Consolas, 'JetBrains Mono', monospace;
    --radius: 8px;
  }}
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ background:var(--bg-page); color:var(--text-primary); font-family:var(--font); min-height:100vh; }}
  .header {{ background:linear-gradient(135deg,#eef0f4 0%,#e2e6ed 100%); border-bottom:1px solid var(--border); padding:28px 40px 22px; }}
  .header-inner {{ max-width:1344px; margin:0 auto; }}
  .header h1 {{ font-size:22px; font-weight:700; letter-spacing:-0.3px; }}
  .header .sub {{ font-size:13px; color:var(--text-secondary); margin-top:4px; }}
  .container {{ max-width:1344px; margin:0 auto; padding:20px 24px 40px; }}
  .card {{ background:var(--bg-card); border:1px solid var(--border); border-radius:8px; padding:18px 20px; margin-bottom:14px; }}
  .sec-title {{ font-size:15px; font-weight:600; color:var(--text-primary); margin-bottom:10px; }}
  table.tbl {{ width:100%; border-collapse:collapse; font-size:13px; }}
  table.tbl th {{ text-align:left; padding:8px 10px; font-size:12px; font-weight:600; color:var(--text-muted); border-bottom:1px solid var(--border); }}
  table.tbl td {{ padding:8px 10px; border-bottom:1px solid rgba(216,227,227,.5); font-family:var(--font-mono); font-size:13px; }}
  .up {{ color:var(--up); font-weight:600; }}
  .down {{ color:var(--down); font-weight:600; }}
  .info-box {{ padding:10px 14px; border-radius:6px; font-size:13px; line-height:1.5; margin-top:6px; }}
  .info-box.blue {{ background:rgba(37,99,235,0.04); border:1px solid rgba(37,99,235,0.15); }}
  .footer {{ text-align:center; padding:18px; color:var(--text-muted); font-size:11px; border-top:1px solid var(--border); margin-top:30px; }}
</style>
</head>
<body>
<div class="header">
  <div class="header-inner">
    <h1>{html_lib.escape(clean_title)}</h1>
    <div class="sub">A-Stock Agents 智能体量化投研平台 · 单文件自包含报告 · 生成于 {timestamp_str}</div>
  </div>
</div>
<div class="container">
  {body_html}
  <div class="footer">aStocks 量化投研中枢 · 生成于 {timestamp_str} · 数据来源: 4级降级实时行情管线 · 市场有风险，入市需谨慎</div>
</div>
</body>
</html>
"""

    from core.data.data_bridge import DataBridge
    from core.indicators.technical_indicators import calc_all, gap_analysis
    from core.models.combo_scorer import ComboScorer, entry_assessment

    default_out_dir = OUTPUT_REPORTS_DIR
    default_out_dir.mkdir(parents=True, exist_ok=True)

    code = sys.argv[1] if len(sys.argv) > 1 else "600519"
    output = sys.argv[2] if len(sys.argv) > 2 else str(default_out_dir / f"aStocks_{code}_{datetime.now():%Y%m%d}.html")


    bridge = DataBridge()
    quote = bridge.get_realtime_quote(code)
    klines = bridge.tencent_kline(code)

    if not klines or len(klines) < 26:
        print("K线数据不足")
        sys.exit(1)

    tech = calc_all(klines)
    gaps = gap_analysis(klines)
    scorer = ComboScorer()
    scores = scorer.score_full(klines, tech["latest"])
    entry = entry_assessment(klines, tech["latest"])

    name = quote.get("name", code) if quote else code
    data = {"code": code, "name": name, "quote": quote, "scores": scores,
            "technical_latest": tech["latest"], "entry": entry, "gaps": gaps}
    generate_simple_report(data, output)
