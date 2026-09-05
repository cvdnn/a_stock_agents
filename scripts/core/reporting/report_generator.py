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


def generate_simple_report(data: dict, output_path: str = None) -> str:
    """生成简单HTML报告（不使用模板的快速版）"""
    raw_code = data.get("code", "unknown")
    raw_name = data.get("name", raw_code)
    code = html_lib.escape(str(raw_code))
    name = html_lib.escape(str(raw_name))
    scores = data.get("scores", {})
    tech = data.get("technical_latest", {})
    entry = data.get("entry", {})
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    raw_rating = str(scores.get("rating", "N/A"))
    rating = html_lib.escape(raw_rating)
    rating_text = html_lib.escape(str(scores.get("rating_text", "")))
    total = scores.get("total", 0)
    max_total = scores.get("max_total", 100)

    # 评分明细行 (进行 HTML 转义防注入)
    rows_html = ""
    for dim, info in scores.items():
        if not isinstance(info, dict) or "score" not in info or "max" not in info:
            continue
        dim_esc = html_lib.escape(str(dim))
        reason_esc = html_lib.escape(str(info.get("reason", "")))
        score_val = info.get('score', 0)
        max_val = info.get('max', 0)
        rows_html += f"""
        <tr>
          <td>{dim_esc}</td>
          <td>{score_val}/{max_val}</td>
          <td>{reason_esc}</td>
        </tr>"""

    # 涨跌色
    chg_pct = data.get("quote", {}).get("change_pct", 0) if data.get("quote") else 0
    chg_color = "#d0312d" if chg_pct >= 0 else "#219653"
    chg_sign = "+" if chg_pct >= 0 else ""

    price_val = data.get("quote", {}).get("price", tech.get("close", "N/A")) if data.get("quote") else tech.get("close", "N/A")
    price = html_lib.escape(str(price_val))

    html_out = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{name}({code}) — aStocks 分析报告</title>
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ background:#f4f5f7; font-family:-apple-system,PingFang SC,Microsoft YaHei,sans-serif; color:#1a1d24; padding:20px 0; }}
  .wrap {{ max-width:960px; margin:0 auto; padding:0 16px; }}
  .header {{ background:linear-gradient(135deg,#2c3e50,#34495e); color:#fff; border-radius:12px; padding:28px 32px; margin-bottom:20px; }}
  .header h1 {{ font-size:24px; margin-bottom:6px; }}
  .header .sub {{ font-size:14px; opacity:0.75; }}
  .header .stats {{ display:flex; gap:24px; margin-top:18px; }}
  .hstat {{ flex:1; text-align:center; }}
  .hstat .v {{ font-size:22px; font-weight:700; font-family:SF Mono,Consolas,monospace; }}
  .hstat .l {{ font-size:12px; opacity:0.65; margin-top:4px; }}
  .card {{ background:#fff; border-radius:10px; padding:24px; margin-bottom:16px; box-shadow:0 1px 4px rgba(0,0,0,0.04); }}
  .card:hover {{ box-shadow:0 2px 12px rgba(0,0,0,0.08); }}
  .sec-title {{ font-size:16px; font-weight:600; margin-bottom:16px; padding-bottom:10px; border-bottom:1px solid #eee; }}
  table.tbl {{ width:100%; border-collapse:collapse; font-size:14px; }}
  table.tbl th, table.tbl td {{ padding:8px 12px; text-align:left; border-bottom:1px solid #f0f0f0; }}
  table.tbl th {{ background:#f8f9fa; font-weight:600; color:#666; font-size:12px; text-transform:uppercase; }}
  .up {{ color:#d0312d; }}
  .down {{ color:#219653; }}
  .tag {{ display:inline-block; padding:4px 10px; border-radius:4px; font-size:12px; font-weight:600; }}
  .tag-a {{ background:#e8f5e9; color:#2e7d32; }}
  .tag-b {{ background:#e3f2fd; color:#1565c0; }}
  .tag-c {{ background:#fff3e0; color:#e65100; }}
  .tag-d {{ background:#ffebee; color:#c62828; }}
  .footer {{ text-align:center; color:#999; font-size:12px; margin-top:24px; padding:16px; }}
  .grid-2 {{ display:grid; grid-template-columns:1fr 1fr; gap:16px; }}
  @media (max-width:768px) {{ .grid-2 {{ grid-template-columns:1fr; }} }}
  .level {{ display:flex; align-items:center; gap:10px; padding:8px 0; }}
  .level .dot {{ width:10px; height:10px; border-radius:50%; flex-shrink:0; }}
  .level .dot.red {{ background:#d0312d; }}
  .level .dot.green {{ background:#219653; }}
  .level .dot.yellow {{ background:#f0ad4e; }}
  .level .ll {{ font-size:12px; color:#888; width:60px; }}
  .level .lp {{ font-weight:600; font-family:SF Mono,Consolas,monospace; }}
  .level .ls {{ font-size:12px; color:#888; }}
</style>
</head>
<body>
<div class="wrap">

<div class="header">
  <h1>{name}({code}) 分析报告</h1>
  <div class="sub">aStocks · 生成于 {timestamp}</div>
  <div class="stats">
    <div class="hstat">
      <div class="v" style="color:{chg_color}">{chg_sign}{price}</div>
      <div class="l">现价 (涨跌)</div>
    </div>
    <div class="hstat">
      <div class="v">{rating}</div>
      <div class="l">综合评级</div>
    </div>
    <div class="hstat">
      <div class="v">{total}/{max_total}</div>
      <div class="l">策略评分</div>
    </div>
  </div>
</div>

<div class="card">
  <div class="sec-title">📈 策略评分明细</div>
  <table class="tbl">
    <thead><tr><th>维度</th><th>得分</th><th>说明</th></tr></thead>
    <tbody>{rows_html}</tbody>
  </table>
  <div style="margin-top:16px; text-align:center;">
    <span class="tag tag-{rating.lower()}">{rating_text} · 建议仓位 {scores.get('suggested_position','N/A')}</span>
  </div>
</div>

<div class="grid-2">
  <div class="card">
    <div class="sec-title">📊 技术指标</div>
    <table class="tbl">
      <tr><td>MA5/MA10</td><td>{tech.get('ma5','N/A')}/{tech.get('ma10','N/A')}</td></tr>
      <tr><td>MA20/MA60</td><td>{tech.get('ma20','N/A')}/{tech.get('ma60','N/A')}</td></tr>
      <tr><td>MACD DIF/DEA</td><td>{tech.get('dif','N/A')}/{tech.get('dea','N/A')}</td></tr>
      <tr><td>KDJ K/D/J</td><td>{tech.get('kdj_k','N/A')}/{tech.get('kdj_d','N/A')}/{tech.get('kdj_j','N/A')}</td></tr>
      <tr><td>RSI/ATR</td><td>{tech.get('rsi','N/A')}/{tech.get('atr','N/A')}</td></tr>
    </table>
  </div>

  <div class="card">
    <div class="sec-title">🎯 关键价位</div>
    <div class="level">
      <div class="dot red"></div><div class="ll">止损位</div>
      <div class="lp">{entry.get('stop_loss','N/A')}</div>
      <div class="ls">约 -{entry.get('stop_loss_pct','N/A')}%</div>
    </div>
    <div class="level">
      <div class="dot green"></div><div class="ll">MA20</div>
      <div class="lp">{tech.get('ma20','N/A')}</div>
      <div class="ls">距MA20 {entry.get('pct_from_ma20','N/A')}%</div>
    </div>
    <div class="level">
      <div class="dot yellow"></div><div class="ll">入场</div>
      <div class="lp">{entry.get('distance_text','N/A')}</div>
      <div class="ls">触发: {'; '.join(entry.get('triggers',[]))}</div>
    </div>
  </div>
</div>

<div class="card">
  <div class="sec-title">⏱ 跳空分析</div>
  <div style="font-size:14px;white-space:pre-wrap;">{json.dumps(data.get('gaps',{}).get('summary','无'), ensure_ascii=False) if data.get('gaps') else '未检测到显著跳空'}</div>
</div>

<div class="footer">
  aStocks · {timestamp} · 数据来源: 腾讯行情/L1直连 · 仅供参考不构成投资建议
</div>

</div>
</body>
</html>"""

    if output_path:
        Path(output_path).write_text(html_out)
        print(f"报告已保存: {output_path}")

    return html_out


if __name__ == "__main__":
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
