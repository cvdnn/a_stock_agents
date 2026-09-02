"""
aStocks HTML 报告生成器

基于 stock-report-html 标准样式模板生成可视化报告。
输出: 白色亚光背景 · 涨红跌绿 · 960px居中 · 自包含单文件
"""

import json
import sys
from pathlib import Path
from datetime import datetime

SKILL_DIR = Path(__file__).resolve().parent.parent
TEMPLATE_PATH = Path("./.AI-Platform/skills/stocks/a-share-data/templates/stock-report.html")


def generate_simple_report(data: dict, output_path: str = None) -> str:
    """生成简单HTML报告（不使用模板的快速版）"""
    code = data.get("code", "unknown")
    name = data.get("name", code)
    scores = data.get("scores", {})
    tech = data.get("technical_latest", {})
    entry = data.get("entry", {})
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    rating = scores.get("rating", "N/A")
    rating_text = scores.get("rating_text", "")
    total = scores.get("total", 0)
    max_total = scores.get("max_total", 100)

    # 评分明细行
    rows_html = ""
    for dim, info in scores.items():
        if dim in ("total", "max_total", "rating", "rating_text", "suggested_position"):
            continue
        rows_html += f"""
        <tr>
          <td>{dim}</td>
          <td>{info['score']}/{info['max']}</td>
          <td>{info['reason']}</td>
        </tr>"""

    # 涨跌色
    chg_pct = data.get("quote", {}).get("change_pct", 0) if data.get("quote") else 0
    chg_color = "#d0312d" if chg_pct >= 0 else "#219653"
    chg_sign = "+" if chg_pct >= 0 else ""

    price = data.get("quote", {}).get("price", tech.get("close", "N/A")) if data.get("quote") else tech.get("close", "N/A")

    html = f"""<!DOCTYPE html>
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
        Path(output_path).write_text(html)
        print(f"报告已保存: {output_path}")

    return html


if __name__ == "__main__":
    from core.data.data_bridge import DataBridge
    from core.indicators.technical_indicators import calc_all, gap_analysis
    from core.models.combo_scorer import ComboScorer, entry_assessment
    try:
        from core.config import OUTPUT_REPORTS_DIR
        default_out_dir = OUTPUT_REPORTS_DIR
    except Exception:
        default_out_dir = Path(__file__).resolve().parent.parent.parent / "output" / "reports"
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
