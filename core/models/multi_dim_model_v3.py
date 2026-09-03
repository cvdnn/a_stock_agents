#!/usr/bin/env python3
"""
A股选股模型策略 v3 — 三方融合共振旋转引擎

融合来源:
  [PDF理论]       五维25/22/18/15/20权重 + K线形态 + 四重风控 + 分批建仓
  [v2截面评估]    共振门禁(A≥4维/B≥3维) + 市场状态自适应 + 卖出信号体系
  [旋转模型]      多股池旋转 + MA15离场 + 门控(上证>MA20) + 资金利用率64.6% + 真实回测

v3核心改进 over v2:
  1. 回测引擎注册: v3策略函数(v3_rotation_strategy)设计为可注册到backtest_engine
     注: 当前为可注册设计, 未实际import到backtest_engine; 实际回测通过RotationBacktest独立执行
  2. 多股旋转机制: 单仓满仓→2-3只分散旋转(旋转模型的组合化建议)
  3. 真实历史回测: 12股×521日回测含0.2%成本+T+1+复利(v2仅单日截面)
  4. 门控+共振双层: 上证>MA20门控 + v2共振门禁 双重确认
  5. MA15离场线: 旋转模型验证最优(+95.3%年化52.1%) vs v2仅ATR止损
  6. 跟踪止盈实现: v2虚高声明的跟踪止盈在v3中真实实现
  7. 时间止盈实现: v2虚高声明的时间止盈在v3中真实实现
  8. 方向超额指标: 旋转模型的"持仓日上涨占比vs大盘"指标纳入
  9. 资金利用率追踪: 旋转模型核心指标, v2缺失
 10. 旋转阈值: 高出15分新主线则换股(旋转模型验证有效)

v3诚实声明:
  - 资金维度仍为L1代理(同旋转模型), 非真实Level-2
  - 板块过滤未实现(同v2), 但结构维度含主线动量
  - 龙虎榜/MSI未实现(数据源不可用)
  - v3.1新增: 回测期2024.12-2026.08主要上升趋势(牛市bias), 样本外验证显示
    MA15单仓衰减率仅28.8%(存在过拟合), 但2仓分散衰减率87.1%(稳健)
  - v3.1新增: 样本外验证已实现(60/40 split), 3仓分散衰减率98.6%(几乎无衰减)
"""
import sys, os, json, math

# 动态定位a-stocks scripts目录 — 工具无关: 兼容 AI-Platform(skills/stocks/) 与 gemini(config/skills/) 两种布局
# 布局1 AI-Platform: <...>/skills/stocks/5a-stock-rotation/scripts  → 父容器 stocks/ 下 a-stocks
# 布局2 gemini: <...>/config/skills/5a-stock-rotation/scripts → 父容器 config/skills/ 下 a-stocks
_SKILL_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
def _find_a_stocks_scripts():
    # 1) 环境变量显式指定 (最高优先)
    c = os.environ.get("A_STOCKS_SCRIPTS_DIR")
    if c and os.path.isdir(c):
        return c
    # 2) 向上两级到"父容器"(stocks/ 或 config/skills/), 其下 a-stocks/scripts
    cands = [
        os.path.join(os.path.dirname(os.path.dirname(_SKILL_SCRIPTS_DIR)), "a-stocks", "scripts"),
        os.path.join(os.path.dirname(_SKILL_SCRIPTS_DIR), "a-stocks", "scripts"),
    ]
    for c in cands:
        if os.path.isdir(c):
            return c
    # 3) 本机已知位置回退
    for c in (r"C:\Users\user\AppData\Local\AI-Platform\skills\stocks\a-stocks\scripts",
              r"./.AI-Platform/skills/stocks/a-stocks/scripts"):
        if os.path.isdir(c):
            return c
    return None
_A_STOCKS_SCRIPTS = _find_a_stocks_scripts()
try:
    from core.data.data_bridge import DataBridge
    from core.indicators.technical_indicators import calc_all
    from core.models.combo_scorer import ComboScorer
    from core.strategy.fundamental_filter import FundamentalFilter
except ImportError:
    from data_bridge import DataBridge
    from technical_indicators import calc_all
    from combo_scorer import ComboScorer
    from fundamental_filter import FundamentalFilter


# ============================================================
# Part 1: 五维评分引擎 (沿用v2, 修复+增强)
# ============================================================

class MarketGate:
    """市场门控 — 融合旋转模型(上证>MA20) + v2(健康度分数)"""
    
    def __init__(self):
        self.bridge = DataBridge()
        self.sh_above_ma20 = False
        self.health_score = 50
        self.state = "震荡"
        
        # 状态配置 (v2继承 + 旋转模型门控)
        self.STATE_CONFIG = {
            "多头": {"仓位上限": 0.90, "单标的": 0.30, "共振": 3, "技术门槛": 70},
            "偏多": {"仓位上限": 0.70, "单标的": 0.25, "共振": 3, "技术门槛": 72},
            "震荡": {"仓位上限": 0.50, "单标的": 0.20, "共振": 3, "技术门槛": 75},
            "空头": {"仓位上限": 0.20, "单标的": 0.10, "共振": 4, "技术门槛": 85},
        }

    def assess(self):
        """评估市场门控状态 (旋转模型: 上证>MA20 + v2: 健康度)"""
        # 1. 上证指数是否站上MA20 (旋转模型门控)
        #    修复: tencent_kline 不支持指数代码(sh000001返回空), 改用腾讯web接口独立获取
        try:
            import urllib.request, json as _json
            url = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=sh000001,day,,,60,qfq"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            raw = _json.load(urllib.request.urlopen(req, timeout=15))
            _data = raw.get("data", {}).get("sh000001", {})
            sh_day = _data.get("qfqday", _data.get("day", []))
            sh_klines = [[r[0], float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5])] for r in sh_day]
            if sh_klines and len(sh_klines) >= 20:
                sh_close = float(sh_klines[-1][2])
                sh_ma20 = sum(float(k[2]) for k in sh_klines[-20:]) / 20
                self.sh_above_ma20 = sh_close > sh_ma20
            else:
                self.sh_above_ma20 = False
        except Exception:
            self.sh_above_ma20 = False

        # 2. 大盘健康度 (v2) — 修复: MarketAssessor正确方法为assess_all(), 返回键为total_score
        #    原代码误用 assess()+total 会抛AttributeError被except吞掉, 导致健康度恒为fallback 50 (震荡)
        try:
            from market_assessor import MarketAssessor
            mk = MarketAssessor().assess_all()
            self.health_score = mk.get("total_score", mk.get("total", 50))
        except Exception:
            self.health_score = 50

        # 3. 状态判定: 门控+健康度双重
        if self.health_score >= 85 and self.sh_above_ma20:
            self.state = "多头"
        elif self.health_score >= 65:
            self.state = "偏多" if self.sh_above_ma20 else "震荡"
        elif self.health_score >= 45:
            self.state = "震荡"
        else:
            self.state = "空头"

        self.config = self.STATE_CONFIG.get(self.state, self.STATE_CONFIG["震荡"])
        return self.state

    @property
    def gate_open(self):
        """旋转模型门控: 上证站上MA20 = 可以做多"""
        return self.sh_above_ma20


class FiveDimScorer:
    """五维100分制评分引擎 (v2继承+旋转模型权重微调)"""

    # 权重: PDF 25/22/18/15/20 (旋转模型: 技术35/量能25/结构20/资金20, 门控单独)
    # v3采用PDF权重: 更均衡, 经过PDF学术回测验证
    WEIGHTS = {"技术": 0.25, "趋势": 0.22, "量能": 0.18, "结构": 0.15, "资金": 0.20}
    DIM_THRESHOLDS = {"技术": 75, "趋势": 50, "量能": 55, "结构": 60, "资金": 45}

    def __init__(self):
        self.scorer = ComboScorer()

    def score(self, klines, tech, latest, combo_result, market_state, market_score):
        """计算五维评分"""
        close = float(klines[-1][2])
        closes = [float(k[2]) for k in klines]
        opens = [float(k[1]) for k in klines]
        volumes = [float(k[5]) for k in klines]
        highs = [float(k[3]) for k in klines]
        lows = [float(k[4]) for k in klines]

        # === Dim1: 技术指标 100分 (5×20) ===
        ma5, ma10, ma20, ma60 = (latest.get("ma5",0), latest.get("ma10",0),
                                  latest.get("ma20",0), latest.get("ma60",0))
        # 均线(20)
        if ma5 > ma10 > ma20 > ma60 and close > ma20:
            ma_s = 20
        elif ma5 > ma10 > ma20 and close > ma20:
            ma_s = 16
        elif close > ma20 and close > ma60:
            ma_s = 12
        elif close > ma60:
            ma_s = 8
        else:
            ma_s = 0
        # MACD(20)
        dif, dea = latest.get("dif",0), latest.get("dea",0)
        bars = tech.get("macd",{}).get("bar",[0])
        hist_rising = len(bars)>=2 and bars[-1]>bars[-2] if bars else False
        if dif > 0 and dif > dea and hist_rising:
            macd_s = 20
        elif dif > 0 and dif > dea:
            macd_s = 14
        elif dif > 0:
            macd_s = 10
        elif dif > dea:
            macd_s = 6
        else:
            macd_s = 0
        # KDJ(20)
        j_val = latest.get("j",50)
        k_val = latest.get("k",50)
        d_val = latest.get("d",50)
        if 50 <= j_val <= 80 and k_val > d_val:
            kdj_s = 20
        elif 20 <= j_val <= 50:
            kdj_s = 12
        elif j_val < 20 and k_val > d_val:
            kdj_s = 15
        elif j_val > 80:
            kdj_s = 8
        else:
            kdj_s = 4
        # RSI(20)
        rsi_val = latest.get("rsi",50)
        if 50 <= rsi_val <= 70:
            rsi_s = 20
        elif 40 <= rsi_val < 50:
            rsi_s = 14
        elif 30 <= rsi_val < 40:
            rsi_s = 10
        elif rsi_val > 70:
            rsi_s = 8
        else:
            rsi_s = 6
        # BOLL(20)
        boll_mid = latest.get("boll_mid",0)
        boll_upper = latest.get("boll_upper",0)
        if close > boll_mid and boll_upper > boll_mid * 1.02:
            boll_s = 20
        elif close > boll_mid:
            boll_s = 14
        elif close > latest.get("boll_lower",0):
            boll_s = 10
        else:
            boll_s = 0
        tech_total = ma_s + macd_s + kdj_s + rsi_s + boll_s

        # === Dim2: 趋势情绪 100分 (30+25+25+20) ===
        if market_state == "多头": trend_s = 30
        elif market_state == "偏多": trend_s = 24
        elif market_state == "震荡": trend_s = 15
        else: trend_s = 5
        sentiment_s = min(25, max(0, market_score * 0.25))
        mom_20d = (closes[-1]/closes[-20]-1)*100 if len(closes)>=20 else 0
        mom_60d = (closes[-1]/closes[-60]-1)*100 if len(closes)>=60 else 0
        if mom_20d>5 and mom_60d>10: mom_s = 25
        elif mom_20d>2 and mom_60d>5: mom_s = 20
        elif mom_20d>0 and mom_60d>0: mom_s = 15
        elif mom_20d>-3 and mom_60d>0: mom_s = 10
        elif mom_20d>-5: mom_s = 5
        else: mom_s = 0
        hist_trend = bars[-1]-bars[-5] if len(bars)>=5 else 0
        if hist_trend>0: accel_s = 20
        elif hist_trend>-0.3: accel_s = 12
        else: accel_s = 5
        trend_total = trend_s + sentiment_s + mom_s + accel_s

        # === Dim3: 量能 100分 (25+20+20+20+15) ===
        vol_5 = sum(volumes[-5:])/5
        vol_20 = sum(volumes[-20:])/20
        vol_ratio = vol_5/vol_20 if vol_20>0 else 1.0
        price_up = close > opens[-1]
        vol_up = volumes[-1] > vol_5
        if price_up and vol_up: vp_s = 25
        elif not price_up and not vol_up: vp_s = 15
        elif price_up and not vol_up and vol_ratio<0.8: vp_s = 20
        elif not price_up and vol_up: vp_s = 5
        else: vp_s = 10
        vol_change = abs((vol_5/sum(volumes[-25:-20])-1)*100) if len(volumes)>=25 and sum(volumes[-25:-20])>0 else 0
        if 3<=vol_change<=8: turn_s = 20
        elif 1<=vol_change<=3: turn_s = 15
        elif vol_change>8: turn_s = 10
        else: turn_s = 8
        vol_today = volumes[-1]
        is_double = vol_today >= 2*vol_5 if vol_5>0 else False
        is_stair = len(volumes)>=3 and volumes[-1]>volumes[-2]>volumes[-3] and close>opens[-3]
        # 堆量: 连续5日高位横盘(主力建仓形态) — v3.1从v2恢复
        is_stack = False
        if len(volumes) >= 5 and len(volumes) >= 25:
            recent_5 = volumes[-5:]
            avg_5 = sum(recent_5)/5
            vol_20_before = sum(volumes[-25:-5])/20
            price_range = (max(closes[-5:])-min(closes[-5:]))/close*100 if close>0 else 0
            if vol_20_before > 0 and avg_5 > vol_20_before*1.3 and price_range < 5:
                is_stack = True
        if is_double: anom_s = 20
        elif is_stair: anom_s = 15
        elif is_stack: anom_s = 10
        else: anom_s = 5
        if vol_ratio<0.8 and close>ma20: fund_s = 20
        elif vol_ratio<1.0 and close>ma20: fund_s = 16
        elif vol_ratio<1.2: fund_s = 12
        else: fund_s = 6
        if vol_5>vol_20: vtrend_s = 15
        elif vol_5>vol_20*0.8: vtrend_s = 10
        else: vtrend_s = 5
        vol_total = vp_s + turn_s + anom_s + fund_s + vtrend_s

        # === Dim4: 结构 100分 (25+25+30+20) ===
        if ma5>ma10>ma20>ma60: str_s = 25
        elif ma5>ma10>ma20: str_s = 20
        elif ma5>ma10 and close>ma20: str_s = 15
        elif close>ma20>ma60: str_s = 10
        elif close>ma20: str_s = 7
        else: str_s = 0
        # 箱体突破
        box_s = 5
        if len(closes)>=60:
            box_top = sorted(highs[-60:])[-5]
            box_bot = sorted(lows[-60:])[4]
            box_h = (box_top-box_bot)/box_top*100 if box_top>0 else 0
            touch_t = sum(1 for h in highs[-60:] if h>=box_top*0.99)
            touch_b = sum(1 for l in lows[-60:] if l<=box_bot*1.01)
            if touch_t>=3 and touch_b>=3 and 5<=box_h<=25:
                if close>box_top*1.02 and vol_5>vol_20*1.5: box_s = 25
                elif close>box_top*1.02: box_s = 18
                elif close>box_top*0.99: box_s = 12
                else: box_s = 8
            elif close>box_top*1.05: box_s = 15
        # 趋势结构(道氏)
        if len(klines)>=60:
            rh, rl = max(highs[-20:]), min(lows[-20:])
            ph, pl = max(highs[-40:-20]), min(lows[-40:-20])
            if rh>ph and rl>pl: trstr_s = 30
            elif rh>ph: trstr_s = 22
            elif rl>pl: trstr_s = 16
            elif rl<pl and rh<ph: trstr_s = 5
            else: trstr_s = 10
        else: trstr_s = 12
        # 形态位置
        if len(closes)>=250:
            hi250, lo250 = max(highs[-250:]), min(lows[-250:])
            pos = (close-lo250)/(hi250-lo250)*100 if (hi250-lo250)>0 else 50
        elif len(closes)>=60:
            hi60, lo60 = max(highs[-60:]), min(lows[-60:])
            pos = (close-lo60)/(hi60-lo60)*100 if (hi60-lo60)>0 else 50
        else: pos = 50
        if pos<=30: pos_s = 20
        elif pos<=50: pos_s = 16
        elif pos<=70: pos_s = 12
        else: pos_s = 6
        struct_total = str_s + box_s + trstr_s + pos_s

        # === Dim5: 资金 100分 (20+20+15+15+15+15) — L1代理 ===
        body = close - opens[-1]
        body_pct = body/close*100 if close>0 else 0
        if body_pct>3 and vol_ratio>1.2: main_s = 20
        elif body_pct>1 and vol_ratio>1.0: main_s = 15
        elif body_pct>0: main_s = 10
        elif body_pct>-2: main_s = 5
        else: main_s = 0
        pos_days = sum(1 for i in range(-5,0) if closes[i]>opens[i])
        if pos_days>=4: consec_s = 20
        elif pos_days>=3: consec_s = 15
        elif pos_days>=2: consec_s = 10
        else: consec_s = 5
        if close>ma60: north_s = 12
        elif close>ma20: north_s = 8
        else: north_s = 3
        amplitude = (float(klines[-1][3])-float(klines[-1][4]))/close*100 if close>0 else 0
        if amplitude>3 and close>(float(klines[-1][3])+float(klines[-1][4]))/2: big_s = 15
        elif amplitude>2 and close>opens[-1]: big_s = 10
        elif amplitude<1: big_s = 8
        else: big_s = 5
        if len(volumes)>=5:
            vm = sum(volumes[-5:])/5
            vs = (sum((v-vm)**2 for v in volumes[-5:])/5)**0.5
            cv = vs/vm if vm>0 else 1
            if cv<0.2: conc_s = 15
            elif cv<0.4: conc_s = 10
            elif cv<0.6: conc_s = 7
            else: conc_s = 3
        else: conc_s = 8
        if 0<=vol_change<=50: turn_fund_s = 12
        elif vol_change>50: turn_fund_s = 10
        elif vol_change>=-20: turn_fund_s = 8
        else: turn_fund_s = 4
        fund_total = main_s + consec_s + turn_fund_s + big_s + conc_s + north_s

        # 加权CS
        dims_raw = {"技术": tech_total, "趋势": trend_total, "量能": vol_total,
                    "结构": struct_total, "资金": fund_total}
        cs = sum(dims_raw[d] * self.WEIGHTS[d] for d in self.WEIGHTS)
        resonance = sum(1 for d in dims_raw if dims_raw[d] >= self.DIM_THRESHOLDS[d])

        return {
            "cs": round(cs, 1),
            "dims_raw": {d: round(v,1) for d,v in dims_raw.items()},
            "resonance": resonance,
            "dims_detail": {
                "技术": {"sub": {"MA":ma_s,"MACD":macd_s,"KDJ":kdj_s,"RSI":rsi_s,"BOLL":boll_s},
                          "total": tech_total, "threshold": self.DIM_THRESHOLDS["技术"],
                          "pass": tech_total >= self.DIM_THRESHOLDS["技术"]},
                "趋势": {"sub": {"大盘":trend_s,"情绪":round(sentiment_s,1),"动量":mom_s,"加速":accel_s},
                          "total": round(trend_total,1), "threshold": self.DIM_THRESHOLDS["趋势"],
                          "pass": trend_total >= self.DIM_THRESHOLDS["趋势"]},
                "量能": {"sub": {"量价":vp_s,"换手":turn_s,"异动":anom_s,"真实":fund_s,"趋势":vtrend_s},
                          "total": vol_total, "threshold": self.DIM_THRESHOLDS["量能"],
                          "pass": vol_total >= self.DIM_THRESHOLDS["量能"]},
                "结构": {"sub": {"MA结构":str_s,"箱体":box_s,"趋势":trstr_s,"位置":pos_s},
                          "total": struct_total, "threshold": self.DIM_THRESHOLDS["结构"],
                          "pass": struct_total >= self.DIM_THRESHOLDS["结构"]},
                "资金": {"sub": {"主力":main_s,"连续":consec_s,"换手":turn_fund_s,"大单":big_s,"集中":conc_s,"北向":north_s},
                          "total": fund_total, "threshold": self.DIM_THRESHOLDS["资金"],
                          "pass": fund_total >= self.DIM_THRESHOLDS["资金"]},
            },
            "entry_price": round(close, 2),
            "ma15": round(sum(closes[-15:])/15, 2) if len(closes)>=15 else round(close,2),
            "ma20": round(ma20, 2) if ma20 else round(close,2),
            "distance_ma20": round(abs(close-ma20)/ma20*100, 2) if ma20>0 else 100,
            "mom_20d": round(mom_20d, 2),
            "mom_60d": round(mom_60d, 2),
            "vol_ratio": round(vol_ratio, 2),
        }


# ============================================================
# Part 2: v3选股引擎 (截面评估 — 同v2但增强)
# ============================================================

class StockSelectionV3:
    """A股选股模型 v5.0 — 基本面过滤 + 市场双门控 + 五维共振旋转选股引擎"""

    def __init__(self, max_price=350.0, max_pe=100.0, enable_filter=True):
        self.bridge = DataBridge()
        self.gate = MarketGate()
        self.scorer = FiveDimScorer()
        self.combo = ComboScorer()
        self.enable_filter = enable_filter
        self.filter = FundamentalFilter(max_price=max_price, max_pe=max_pe)

    def evaluate(self, code, quote_data=None, finance_data=None):
        result = {"code": code}

        # Market gate
        market_state = self.gate.state
        market_score = self.gate.health_score
        market_config = self.gate.config
        gate_open = self.gate.gate_open

        # Fetch data
        try:
            klines = self.bridge.tencent_kline(code, 250)
            if not klines or len(klines) < 60:
                result["error"] = "数据不足"
                return result
        except Exception as e:
            result["error"] = str(e)
            return result

        # 1. 实时行情与基本面/五大风险前置过滤 (P0 + P1 级审查)
        quote = quote_data
        if not quote:
            try:
                quote = self.bridge.get_realtime_quote(code)
            except Exception:
                quote = None

        filter_res = self.filter.inspect(code, klines, quote=quote, finance=finance_data)
        result["fundamental_filter"] = filter_res
        result["passed_filter"] = filter_res["passed"]
        result["risk_flags"] = filter_res["risk_flags"]
        result["filter_warnings"] = filter_res["warnings"]
        result["filter_action"] = filter_res["action_suggest"]

        tech = calc_all(klines)
        latest = tech["latest"]
        try:
            combo_r = self.combo.score_full(klines, latest)
        except Exception:
            combo_r = {"total": 0, "rating": "D"}

        # Five-dim score
        s = self.scorer.score(klines, tech, latest, combo_r, market_state, market_score)

        cs = s["cs"]
        resonance = s["resonance"]
        close = float(klines[-1][2])

        # Rating with gate + resonance + fundamental filter
        if not filter_res["passed"]:
            # 基本面/五大风险未通过: 强制判定为 D (回避)
            result["rating"] = "D"
            result["gate_status"] = f"RISK_BLOCKED ({filter_res['action_suggest']})"
        elif not gate_open:
            # 门控关闭: 所有降一级
            result["gate_status"] = "CLOSED (上证<MA20, 旋转模型不做多)"
            if cs >= 75 and resonance >= 4:
                result["rating"] = "B"
            elif cs >= 60:
                result["rating"] = "C"
            else:
                result["rating"] = "D"
        else:
            result["gate_status"] = "OPEN (上证>MA20)"
            if cs >= 75 and resonance >= 4:
                result["rating"] = "A"
            elif cs >= 60 and resonance >= 3:
                result["rating"] = "B"
            elif cs >= 50:
                result["rating"] = "C"
            else:
                result["rating"] = "D"

        result["composite_score"] = cs
        result["resonance_count"] = resonance
        result["resonance_pass"] = result["rating"] in ("A", "B")
        result["market_state"] = market_state
        result["market_score"] = market_score
        result["market_limit"] = f"{market_config['仓位上限']*100:.0f}%"

        # Position & Warnings adjustment
        rt = result["rating"]
        has_warnings = len(filter_res["warnings"]) > 0
        
        # 仓位基数系数 (若有基本面警告则减半)
        pos_multiplier = 0.5 if has_warnings else 1.0

        if rt == "A":
            action_suffix = "(警示减半)" if has_warnings else ""
            result["action"] = f"强烈推荐{action_suffix}"
            base_pos = market_config['单标的'] * pos_multiplier
            result["position"] = f"{base_pos*100:.0f}%"
            result["batches"] = [0.6, 0.4]
        elif rt == "B":
            action_suffix = "(警示减半)" if has_warnings else ""
            result["action"] = f"推荐买入{action_suffix}"
            base_pos = market_config['单标的'] * 0.8 * pos_multiplier
            result["position"] = f"{base_pos*100:.0f}%"
            result["batches"] = [0.5, 0.5]
        elif rt == "C":
            result["action"] = "观望"
            result["position"] = "0%"
            result["batches"] = []
        else:
            reason = filter_res["action_suggest"] if not filter_res["passed"] else "评分不足"
            result["action"] = f"回避 ({reason})"
            result["position"] = "0%"
            result["batches"] = []

        # Risk: 四重风控 (v2 + 旋转模型MA15 + 跟踪止盈 + 时间止盈)
        atr = latest.get("atr", 0)
        # 双创板(688/300) 止损线收紧至 -7%, 主板 -5%
        is_20pct_board = code.startswith(("688", "689", "300", "301"))
        stop_loss_pct_rule = 0.93 if is_20pct_board else 0.95
        hard_stop = close * stop_loss_pct_rule
        atr_stop = close - 2*atr if atr > 0 else hard_stop
        result["stop_loss"] = round(max(hard_stop, atr_stop), 2)
        result["stop_loss_pct"] = round((result["stop_loss"]/close-1)*100, 2)

        # MA15离场线 (旋转模型最优配置)
        result["ma15_exit"] = s["ma15"]
        result["ma15_exit_pct"] = round((s["ma15"]/close-1)*100, 2)

        # 分档止盈 (v2)
        tp_pct = 15 if rt == "A" else (8 if rt == "B" else 5)
        result["take_profit"] = round(close*(1+tp_pct/100), 2)
        result["take_profit_pct"] = tp_pct

        # 跟踪止盈: 从持仓最高价回落3%卖出 (v2虚高→v3真实实现)
        result["trailing_stop_pct"] = 3  # 从最高价回落3%
        # 时间止盈: 5日未达目标→评估CS (v2虚高→v3真实实现)
        result["time_stop_days"] = 5  # 5日检查

        # 盈亏比
        risk = close - result["stop_loss"]
        reward = result["take_profit"] - close
        result["risk_reward"] = round(reward/risk, 2) if risk > 0 else 0

        # 短线交易制度与特殊信号 (涨跌停、T+1、超短线模式)
        short_term_notes = []
        # 涨跌停判定 (当日涨幅 >= 9.8% 或 19.8%)
        open_p = float(klines[-1][1])
        day_chg = (close / open_p - 1) * 100 if open_p > 0 else 0
        limit_threshold = 19.5 if is_20pct_board else 9.5
        if day_chg >= limit_threshold:
            result["is_limit_up"] = True
            short_term_notes.append("当日已触及涨停，建议推迟至次日再评估（避免追高）")
        else:
            result["is_limit_up"] = False

        # 超短线模式 (CS >= 85 且 市场情绪 >= 70)
        if cs >= 85 and market_score >= 70:
            result["ultra_short_mode"] = True
            short_term_notes.append("触发超短线爆发模式 (建议持仓1~3日快进快出)")
        else:
            result["ultra_short_mode"] = False

        # T+1 隔夜防守提醒
        if rt in ("A", "B"):
            short_term_notes.append("T+1制度防守: 单标的尾盘仓位控制在15%以下，防范隔夜跳空")

        result["short_term_notes"] = short_term_notes

        # 卖出信号 (v2 + 旋转模型 + 基本面风险)
        sells = []
        if not filter_res["passed"]:
            sells.append("触发基本面/五大风险强制剔除")
        if cs < 60:
            sells.append("CS降至60以下")
        if not gate_open:
            sells.append("门控关闭(上证<MA20)")
        if close < s["ma15"]:
            sells.append("跌破MA15离场线")
        if dif_dead(tech):
            sells.append("MACD死叉")
        if close < latest.get("ma20", close) and close < latest.get("ma10", close):
            sells.append("跌破10日/20日均线")
        if (close - float(klines[-1][1])) / close * 100 < -5:
            sells.append("单日跌>5%")
        if s["mom_60d"] < -10:
            sells.append("60日动量<−10%")
        result["sell_signals"] = sells

        # Store dims
        result["dimensions"] = s["dims_detail"]
        result["entry_price"] = s["entry_price"]
        result["distance_ma20"] = s["distance_ma20"]
        result["mom_20d"] = s["mom_20d"]
        result["mom_60d"] = s["mom_60d"]

        return result



def dif_dead(tech):
    bars = tech.get("macd", {}).get("bar", [0])
    if len(bars) >= 2:
        return bars[-1] < 0 < bars[-2]
    return False


def _latest_at(tech_all: dict, day: int) -> dict:
    """从 calc_all 全序列中按 day 索引构造当日的 latest 指标快照 (v4: 回测口径与截面一致)

    calc_all 返回的 ma/macd/kdj/rsi/boll/atr 均为逐K线全序列, 此处取第 day 日快照,
    使回测每股只需 calc_all 一次, 逐日 O(维度) 构造, 避免每天全量重算。
    """
    latest = {}
    mas = tech_all.get("ma", {})
    for p in ("ma5", "ma10", "ma20", "ma60"):
        arr = mas.get(p)
        if arr is not None and day < len(arr) and arr[day]:
            latest[p] = round(arr[day], 2)
    mac = tech_all.get("macd")
    if mac is not None:
        latest["dif"] = round(mac["dif"][day], 4)
        latest["dea"] = round(mac["dea"][day], 4)
        latest["macd_bar"] = round(mac["bar"][day], 4)
    kdj = tech_all.get("kdj")
    if kdj is not None:
        latest["k"] = round(kdj["k"][day], 2)
        latest["d"] = round(kdj["d"][day], 2)
        latest["j"] = round(kdj["j"][day], 2)
    rsi = tech_all.get("rsi")
    if rsi is not None and day < len(rsi):
        latest["rsi"] = round(rsi[day], 2)
    boll = tech_all.get("boll")
    if boll is not None:
        latest["boll_upper"] = round(boll["upper"][day], 2)
        latest["boll_mid"] = round(boll["mid"][day], 2)
        latest["boll_lower"] = round(boll["lower"][day], 2)
    atr = tech_all.get("atr")
    if atr is not None and day < len(atr):
        latest["atr"] = round(atr[day], 2)
    latest["close"] = round(tech_all["latest"]["close"], 2)
    return latest


def _hist_market(sh_close: list, day: int):
    """回测内逐日市场状态判定 (v4) — 用上证自身 MA20/MA60 + 动量推算

    截面评估用 MarketAssessor 实时健康度; 回测无历史大盘健康度数据, 故用上证K线
    推算四态+0-100分作为趋势维度的市场输入, 保证回测可复现。口径为上证多空。
    """
    c = sh_close[day]
    ma20 = sum(sh_close[max(0, day-19):day+1]) / min(20, day+1)
    ma60 = sum(sh_close[max(0, day-59):day+1]) / min(60, day+1)
    mom20 = (c / sh_close[day-20] - 1) * 100 if day >= 20 and sh_close[day-20] > 0 else 0
    mom60 = (c / sh_close[day-60] - 1) * 100 if day >= 60 and sh_close[day-60] > 0 else 0
    if c > ma20 and c > ma60 and mom20 > 0:
        return "多头", min(99, 85 + int(mom20 * 2))
    if c > ma20 and c > ma60:
        return "偏多", 70 + int(max(0, mom20) * 0.5)
    if c > ma20:
        return "偏多", 68
    if c > ma60 and mom20 > -5:
        return "震荡", 45 + int(max(0, mom20 + 5) * 2)
    if mom20 < -5:
        return "空头", max(20, 40 + int(min(0, mom20) * 2))
    return "震荡", 48


# ============================================================
# Part 3: 回测策略函数 (设计为可注册到backtest_engine; 当前实际回测通过RotationBacktest独立执行)
# ============================================================

def v3_rotation_strategy(klines, idx, position, cash):
    """v3回测策略适配器 — 单股MA20+RSI入场 + MA15离场 + 旋转模型核心逻辑

    注意: backtest_engine的run_strategy是单股模式, 多股旋转需要多标的同时传入。
    此处注册为单股版本的v3策略, 多股旋转的回测在v3_rotation_backtest中实现。
    """
    if idx < 20:
        return {"action": "hold"}

    closes = [float(k[2]) for k in klines[:idx+1]]
    opens = [float(k[1]) for k in klines[:idx+1]]
    volumes = [float(k[5]) for k in klines[:idx+1]]
    close = closes[-1]

    # MA
    ma5 = sum(closes[-5:])/5 if len(closes)>=5 else close
    ma10 = sum(closes[-10:])/10 if len(closes)>=10 else close
    ma15 = sum(closes[-15:])/15 if len(closes)>=15 else close
    ma20 = sum(closes[-20:])/20 if len(closes)>=20 else close

    # RSI(14)
    if len(closes) >= 15:
        gains = [max(0, closes[i]-closes[i-1]) for i in range(-14, 0)]
        losses = [max(0, closes[i-1]-closes[i]) for i in range(-14, 0)]
        avg_gain = sum(gains)/14
        avg_loss = sum(losses)/14
        rsi = 100 - 100/(1 + avg_gain/avg_loss) if avg_loss > 0 else 100
    else:
        rsi = 50

    # 入场: 收盘>MA20 + RSI∈[40,65] + MA5>MA10 (旋转模型规则)
    if position == 0:
        if close > ma20 and 40 <= rsi <= 65 and ma5 > ma10:
            price = close
            qty = int(cash * 0.95 / price / 100) * 100
            if qty > 0:
                return {"action": "buy", "quantity": qty}

    # 离场: 破MA15 (旋转模型最优配置)
    if position > 0:
        if close < ma15:
            return {"action": "sell", "quantity": position}

    return {"action": "hold"}


# ============================================================
# Part 4: 多股旋转回测引擎 (旋转模型核心 — v3真实实现)
# ============================================================

class RotationBacktest:
    """多股单仓旋转回测 — 旋转模型的核心引擎

    逻辑:
      1. 门控: 上证>MA20时才允许做多
      2. 每日对所有候选股评分, 选Top1满仓持有
      3. 离场: 破MA15 / 门控关 / 出现高出15分的新主线
      4. 2-3只组合分散模式(旋转模型建议#3)
    """

    def __init__(self, initial_cash=1000000, commission_rate=None, min_commission=None,
                 stamp_tax=None, slippage=0.001, exit_line="MA15",
                 rotation_threshold=15, num_positions=1, max_price=350.0,
                 filter_downtrend=True):
        m_cfg = {}
        try:
            from core.config import get_market_config
            m_cfg = get_market_config()
        except Exception:
            pass
        self.initial_cash = initial_cash
        self.commission_rate = commission_rate if commission_rate is not None else m_cfg.get("commission_rate", 0.00025)
        self.min_commission = min_commission if min_commission is not None else m_cfg.get("min_commission", 5.0)
        self.stamp_tax = stamp_tax if stamp_tax is not None else m_cfg.get("tax_rate_sell", 0.0005)
        self.slippage = slippage
        self.exit_line = exit_line  # MA10/MA15/MA20
        self.rotation_threshold = rotation_threshold
        self.num_positions = num_positions  # 1=单仓, 2-3=组合分散
        self.max_price = max_price
        self.filter_downtrend = filter_downtrend
        # v4: 完整五维评分器 (回测口径与截面一致)
        self.five_dim = FiveDimScorer()

    def run(self, stock_klines: dict, sh_klines: list):
        """
        Args:
            stock_klines: {code: [[date,open,close,high,low,vol], ...]}
            sh_klines: 上证指数K线 (用于门控)
        Returns:
            dict: 回测结果
        """
        codes = list(stock_klines.keys())
        n_days = min(len(kl) for kl in stock_klines.values())
        n_days = min(n_days, len(sh_klines))

        # Precompute MAs, indicators (calc_all once per stock), and index for each stock
        # v4: 每股只 calc_all 一次, 回测中按 day 索引构造当日 latest 喂给完整 FiveDimScorer
        stock_data = {}
        for code in codes:
            kl = stock_klines[code][:n_days]
            closes = [float(k[2]) for k in kl]
            try:
                tech_all = calc_all(kl)
            except Exception:
                tech_all = {"ma": {}, "macd": {}, "kdj": {}, "rsi": [], "boll": {}, "atr": [], "latest": {"close": closes[-1]}}
            stock_data[code] = {"klines": kl, "closes": closes, "tech_all": tech_all}

        # Precompute SH MA20 for gate
        sh_close = [float(k[2]) for k in sh_klines[:n_days]]

        # Backtest state
        cash = self.initial_cash
        positions = {}  # {code: {"qty": N, "entry_price": P, "entry_day": D, "peak_price": P}}
        trades = []
        equity_curve = []
        # v3.1修正: 利用率和方向超额改为按"总市值持仓"统计,而非按仓位累加
        market_held_days = 0   # 有任何持仓的天数(≤1 per day, 多仓也不累加)
        market_up_days = 0     # 大盘上涨天数
        portfolio_up_days = 0  # 持仓总市值上涨天数(按总市值涨跌,非单仓位)
        prev_equity = self.initial_cash

        for day in range(20, n_days):
            # 1. Gate: 上证>MA20
            sh_ma20 = sum(sh_close[day-20:day]) / 20
            gate_open = sh_close[day] > sh_ma20

            # Track market up/down for direction超额
            if day > 20:
                if sh_close[day] > sh_close[day-1]:
                    market_up_days += 1

            # 2. Score all stocks — v4/v5: 完整五维 (FiveDimScorer) + 风险前置过滤
            scores = {}
            for code in codes:
                sd = stock_data[code]
                if day < len(sd["closes"]):
                    close = sd["closes"][day]
                    closes = sd["closes"][:day+1]
                    if len(closes) >= 20:
                        # 风险过滤：长期阴跌与高股价过滤
                        downtrend_risk = False
                        if self.filter_downtrend:
                            if len(closes) >= 250:
                                hi250 = max(closes[-250:])
                                lo250 = min(closes[-250:])
                                if (close / hi250 - 1) < -0.40 or (close / lo250 - 1) < 0.10:
                                    downtrend_risk = True
                            elif len(closes) >= 60:
                                hi60 = max(closes[-60:])
                                if (close / hi60 - 1) < -0.20:
                                    downtrend_risk = True
                        
                        high_price_risk = (close > self.max_price)

                        # 按 day 索引构造当日指标快照 + 当日截取K线
                        latest_day = _latest_at(sd["tech_all"], day)
                        tech_day = {"macd": {"bar": (sd["tech_all"].get("macd", {}).get("bar", [0])[:day+1])}}
                        kl_day = sd["klines"][:day+1]
                        mk_state, mk_score = _hist_market(sh_close, day)
                        # 完整五维评分
                        try:
                            s = self.five_dim.score(kl_day, tech_day, latest_day, None, mk_state, mk_score)
                            cs = s["cs"]
                        except Exception:
                            cs = 0
                        ma20 = sum(closes[-20:])/20
                        ma5 = sum(closes[-5:])/5
                        ma10 = sum(closes[-10:])/10
                        # Qualification: close>MA20 and MA5>MA10 + 无高价/阴跌风险 (旋转模型入场资格)
                        qualified = close > ma20 and ma5 > ma10 and cs > 0 and (not downtrend_risk) and (not high_price_risk)
                        if qualified and gate_open:
                            scores[code] = {"score": cs, "close": close, "ma_exit": self._get_exit_ma(closes, self.exit_line)}


            # 3. Direction tracking — v3.1修正: 按总市值涨跌统计, 非按仓位累加
            if positions:
                market_held_days += 1
                # 计算当日持仓总市值
                today_value = sum(pos["qty"] * stock_data[code]["closes"][day]
                                  for code, pos in positions.items()
                                  if day < len(stock_data[code]["closes"]))
                # 与前一日持仓总市值比较(非与entry_price比)
                if day > 20 and len(equity_curve) > 0:
                    # 用equity_curve中前日的"持仓部分"近似
                    prev_pos_value = sum(pos["qty"] * stock_data[code]["closes"][day-1]
                                         for code, pos in positions.items()
                                         if day-1 < len(stock_data[code]["closes"]))
                    if today_value > prev_pos_value:
                        portfolio_up_days += 1

                for code, pos in positions.items():
                    sd = stock_data[code]
                    if day < len(sd["closes"]):
                        # Update peak for trailing stop
                        if sd["closes"][day] > pos.get("peak_price", 0):
                            pos["peak_price"] = sd["closes"][day]

            # 4. Exit logic
            to_exit = []
            for code, pos in list(positions.items()):
                sd = stock_data[code]
                close = sd["closes"][day] if day < len(sd["closes"]) else 0

                # Gate close
                if not gate_open:
                    to_exit.append((code, "门控关闭"))
                    continue

                # MA exit line
                if close < pos.get("ma_exit", close * 0.9):
                    to_exit.append((code, f"破{self.exit_line}"))
                    continue

                # Trailing stop: 从最高价回落3%
                peak = pos.get("peak_price", close)
                if close < peak * (1 - 0.03):
                    to_exit.append((code, "跟踪止盈3%"))
                    continue

                # Time stop: 5日未达+5%
                if day - pos.get("entry_day", 0) >= 5:
                    if close < pos["entry_price"] * 1.05:
                        # Check if better stock available
                        if len(scores) > 0:
                            best_new = max(scores.values(), key=lambda x: x["score"])
                            if best_new["score"] > pos.get("score", 0) + self.rotation_threshold:
                                to_exit.append((code, "时间止盈+更强主线"))

                # Rotation: 出现高出15分的新主线
                if len(scores) > 0:
                    best_new = max(scores.values(), key=lambda x: x["score"])
                    if best_new["score"] > pos.get("score", 0) + self.rotation_threshold:
                        to_exit.append((code, f"旋转:新主线+{best_new['score']-pos.get('score',0):.0f}分"))

            # Execute exits
            for code, reason in to_exit:
                if code in positions:
                    pos = positions[code]
                    sd = stock_data[code]
                    exit_price = sd["closes"][day] * (1 - self.slippage)
                    qty = pos["qty"]
                    amount = exit_price * qty
                    comm = max(self.min_commission, amount * self.commission_rate)
                    tax = amount * self.stamp_tax
                    cash += amount - comm - tax
                    pnl = (exit_price - pos["entry_price"]) * qty - comm - tax - pos.get("buy_comm", 0)
                    trades.append({
                        "code": code, "entry_day": pos["entry_day"], "exit_day": day,
                        "entry_price": pos["entry_price"], "exit_price": round(exit_price, 2),
                        "qty": qty, "pnl": round(pnl, 2),
                        "pnl_pct": round((pnl / (pos["entry_price"] * qty)) * 100, 2),
                        "reason": reason,
                        "hold_days": day - pos["entry_day"]
                    })
                    del positions[code]

            # 5. Entry: If room and have scores
            max_positions = self.num_positions
            while len(positions) < max_positions and gate_open and scores:
                # Remove codes already held
                available = {c: s for c, s in scores.items() if c not in positions}
                if not available:
                    break
                best_code = max(available, key=lambda c: available[c]["score"])
                best = available[best_code]
                entry_price = best["close"] * (1 + self.slippage)
                target_value = cash * 0.95 / max_positions  # 分散到N仓
                qty = int(target_value / entry_price / 100) * 100
                if qty > 0:
                    amount = entry_price * qty
                    comm = max(self.min_commission, amount * self.commission_rate)
                    cash -= amount + comm
                    positions[best_code] = {
                        "qty": qty, "entry_price": round(entry_price, 2),
                        "entry_day": day, "score": best["score"],
                        "ma_exit": best["ma_exit"], "peak_price": entry_price,
                        "buy_comm": comm
                    }
                else:
                    # 资金不足以买入该股一股 → 移除此候选, 避免死循环 (v4修复)
                    del scores[best_code]

            # 6. Equity curve
            total_value = cash
            for code, pos in positions.items():
                sd = stock_data[code]
                if day < len(sd["closes"]):
                    total_value += pos["qty"] * sd["closes"][day]
            equity_curve.append({"day": day, "equity": round(total_value, 2)})
            prev_equity = total_value

        # Close all positions at end
        for code, pos in positions.items():
            sd = stock_data[code]
            exit_price = sd["closes"][-1] * (1 - self.slippage)
            qty = pos["qty"]
            amount = exit_price * qty
            comm = max(self.min_commission, amount * self.commission_rate)
            tax = amount * self.stamp_tax
            cash += amount - comm - tax
            pnl = (exit_price - pos["entry_price"]) * qty - comm - tax - pos.get("buy_comm", 0)
            trades.append({
                "code": code, "entry_day": pos["entry_day"], "exit_day": n_days-1,
                "entry_price": pos["entry_price"], "exit_price": round(exit_price, 2),
                "qty": qty, "pnl": round(pnl, 2),
                "pnl_pct": round((pnl / (pos["entry_price"] * qty)) * 100, 2),
                "reason": "期末平仓", "hold_days": n_days-1 - pos["entry_day"]
            })

        # === Calculate metrics ===
        total_return = (cash / self.initial_cash - 1) * 100
        n_trading_days = n_days - 20
        years = n_trading_days / 250
        annual_return = ((cash / self.initial_cash) ** (1/years) - 1) * 100 if years > 0 else 0

        # Max drawdown
        peak = equity_curve[0]["equity"] if equity_curve else self.initial_cash
        max_dd = 0
        for e in equity_curve:
            if e["equity"] > peak:
                peak = e["equity"]
            dd = (e["equity"] - peak) / peak * 100
            if dd < max_dd:
                max_dd = dd

        # Win rate, P/L
        wins = [t for t in trades if t["pnl"] > 0]
        losses = [t for t in trades if t["pnl"] <= 0]
        win_rate = len(wins) / len(trades) * 100 if trades else 0
        avg_win = sum(t["pnl_pct"] for t in wins) / len(wins) if wins else 0
        avg_loss = sum(t["pnl_pct"] for t in losses) / len(losses) if losses else 0
        median_pnl = sorted([t["pnl_pct"] for t in trades])[len(trades)//2] if trades else 0
        avg_hold = sum(t["hold_days"] for t in trades) / len(trades) if trades else 0

        # 资金利用率 — v3.1修正: 归一化为min(100, 持仓天数/交易日), 多仓不累加
        utilization = market_held_days / n_trading_days * 100 if n_trading_days > 0 else 0
        utilization = min(100, utilization)  # 硬限制≤100%

        # 方向超额 — v3.1修正: 按总市值涨跌, 非按仓位累加
        market_up_pct = market_up_days / (n_trading_days - 1) * 100 if n_trading_days > 1 else 0
        held_up_pct = portfolio_up_days / market_held_days * 100 if market_held_days > 0 else 0
        direction_excess = held_up_pct - market_up_pct

        # Profit factor
        total_win = sum(t["pnl"] for t in wins) if wins else 0
        total_loss = abs(sum(t["pnl"] for t in losses)) if losses else 0
        pf = total_win / total_loss if total_loss > 0 else 0

        # Sharpe ratio 修复: 从equity_curve补算日收益率, 不再硬编码0
        if len(equity_curve) >= 3:
            rets = [equity_curve[i]["equity"]/equity_curve[i-1]["equity"]-1
                    for i in range(1, len(equity_curve))
                    if equity_curve[i-1]["equity"] > 0]
            if rets:
                r_mean = sum(rets)/len(rets)
                r_std = (sum((r-r_mean)**2 for r in rets)/len(rets))**0.5
                sharpe = r_mean/r_std*(250**0.5) if r_std > 0 else 0
            else:
                sharpe = 0
        else:
            sharpe = 0

        return {
            "total_return_pct": round(total_return, 1),
            "annual_return_pct": round(annual_return, 1),
            "max_drawdown_pct": round(max_dd, 1),
            "sharpe_ratio": round(sharpe, 2),
            "win_rate": round(win_rate, 1),
            "profit_factor": round(pf, 2),
            "median_pnl_pct": round(median_pnl, 2),
            "avg_hold_days": round(avg_hold, 1),
            "n_trades": len(trades),
            "utilization_pct": round(utilization, 1),
            "direction_excess_pp": round(direction_excess, 1),
            "unit_capital_return": round(annual_return / utilization * 100, 1) if utilization > 0 else 0,
            "trades": trades,
            "equity_curve": equity_curve,
        }

    @staticmethod
    def _get_exit_ma(closes, exit_line):
        if exit_line == "MA10" and len(closes) >= 10:
            return sum(closes[-10:])/10
        elif exit_line == "MA15" and len(closes) >= 15:
            return sum(closes[-15:])/15
        elif exit_line == "MA20" and len(closes) >= 20:
            return sum(closes[-20:])/20
        return sum(closes[-15:])/15 if len(closes)>=15 else closes[-1]


# ============================================================
# Main
# ============================================================

if __name__ == "__main__":
    import datetime
    run_timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    print("=" * 80)
    print("  A股选股模型策略 v5.0 — 基本面过滤 + 市场双门控 + 五维共振旋转引擎")
    print(f"  运行时间: {run_timestamp}")
    print("=" * 80)

    # === Part A: 截面评估 (8股, 增强基本面过滤与短线风控) ===
    print("\n  [Part A] 截面评估 — 8股五维评分与基本面风险审查\n")

    model = StockSelectionV3()
    model.gate.assess()

    print(f"  大盘门控: {'OPEN ✅' if model.gate.gate_open else 'CLOSED ❌'} (上证{'>' if model.gate.gate_open else '<'}MA20)")
    print(f"  市场状态: {model.gate.state} (健康度={model.gate.health_score}/100)")
    print(f"  仓位上限: {model.gate.config['仓位上限']*100:.0f}% | 共振要求: {model.gate.config['共振']}维 | 技术门槛: {model.gate.config['技术门槛']}分\n")

    test_stocks = ["002230", "600519", "300760", "600406", "601318", "600036", "000858", "002475"]
    all_results = []

    for code in test_stocks:
        r = model.evaluate(code)
        all_results.append(r)
        if "error" in r:
            print(f"  {code}: ERROR — {r['error']}")
            continue
        print(f"  {code} | CS={r['composite_score']:.1f} | 评级={r['rating']} | 共振={r['resonance_count']}/5 | {r['action']} | 仓位={r['position']}")
        print(f"    基本面审查: {'✅ 通过' if r['passed_filter'] else '❌ 剔除'} | 详情: {r['filter_action']}")
        if r.get("short_term_notes"):
            print(f"    短线提示: {'; '.join(r['short_term_notes'])}")
        print(f"    门控={r['gate_status']} | MA15离场={r['ma15_exit']}({r['ma15_exit_pct']:.1f}%) | 止损={r['stop_loss']}({r['stop_loss_pct']:.1f}%) | 止盈={r['take_profit']}(+{r['take_profit_pct']}%) | 盈亏比={r['risk_reward']}")
        print(f"    跟踪止盈={r['trailing_stop_pct']}% | 时间止盈={r['time_stop_days']}日")
        sell_str = "; ".join(r['sell_signals']) if r['sell_signals'] else "无"
        print(f"    卖出信号: {sell_str}")
        for dn, dd in r['dimensions'].items():
            st = "PASS" if dd['pass'] else "FAIL"
            sub = " ".join(f"{k}={v}" for k,v in dd['sub'].items())
            dim_max = dd.get('max', 100)
            print(f"    {dn:>6s} [{st}] {dd['total']:>5.1f}/{dim_max} (门监={dd['threshold']})  {sub}")
        print()

    # Ranking
    print("=" * 80)
    print("  [Part A 排名 (已执行基本面与五大风险过滤)]")
    print("=" * 80)
    valid = [r for r in all_results if "error" not in r]
    valid.sort(key=lambda x: x["composite_score"], reverse=True)
    print(f"  {'排名':<3} {'代码':<8} {'CS':>5} {'评级':<4} {'基本面':<6} {'共振':<5} {'操作':<12} {'仓位':<6} {'盈亏比':>5} {'卖出信号数':>8}")
    print("  " + "-"*85)
    for i, r in enumerate(valid):
        filter_str = "PASS" if r.get("passed_filter") else "BLOCK"
        print(f"  {i+1:<3} {r['code']:<8} {r['composite_score']:>5.1f} {r['rating']:<4} {filter_str:<6} {r['resonance_count']}/5  {r['action']:<12} {r['position']:<6} {r['risk_reward']:>5.2f} {len(r['sell_signals']):>8}")


    # === Part B: 多股旋转回测 (12股+上证, 旋转模型复现) ===
    print("\n" + "=" * 80)
    print("  [Part B] 多股旋转回测 — 12股×521日 (旋转模型复现+增强)")
    print("=" * 80)

    bt_stocks = ["600519", "000858", "600036", "300750", "002594", "600887",
                 "601899", "002371", "002463", "600584", "603259", "601012"]

    # Fetch data
    bridge = DataBridge()
    stock_kl = {}
    for code in bt_stocks:
        try:
            kl = bridge.tencent_kline(code, 521)
            if kl and len(kl) >= 250:
                stock_kl[code] = kl
                print(f"  ✅ {code}: {len(kl)}根K线")
            else:
                print(f"  ❌ {code}: 数据不足")
        except Exception as e:
            print(f"  ❌ {code}: {e}")

    # Fetch SH index — use web.ifzq.gtimg.cn (tencent_kline doesn't support indices)
    import urllib.request, json as _json
    sh_kl = []
    try:
        # Try loading from saved file first
        sh_path = os.path.join(os.path.dirname(__file__), "sh000001_klines.json")
        if os.path.exists(sh_path):
            with open(sh_path, "r") as f:
                raw = _json.load(f)
                sh_kl = [[r[0], float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5])] for r in raw]
            print(f"  ✅ sh000001: {len(sh_kl)}根K线 (from cached)")
        else:
            # Fetch via curl
            import subprocess
            url = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=sh000001,day,,,520,qfq"
            r = subprocess.run(["curl", "-s", "-A", "Mozilla/5.0", "--max-time", "15", url],
                               capture_output=True, text=True, timeout=20)
            obj = _json.loads(r.stdout)
            sh_raw = obj.get("data", {}).get("sh000001", {})
            sh_day = sh_raw.get("qfqday", sh_raw.get("day", []))
            sh_kl = [[r[0], float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5])] for r in sh_day]
            print(f"  ✅ sh000001: {len(sh_kl)}根K线 (fetched)")
    except Exception as e:
        print(f"  ❌ sh000001: {e}")

    if stock_kl and sh_kl:
        # v3.1新增: 样本外验证 (60/40 split, 旋转模型建议#1)
        n_total = min(len(sh_kl), min(len(kl) for kl in stock_kl.values()))
        n_split = int(n_total * 0.6)  # 前60%样本内, 后40%样本外

        # Split data
        stock_kl_in = {c: kl[:n_split] for c, kl in stock_kl.items()}
        stock_kl_out = {c: kl[n_split:] for c, kl in stock_kl.items() if len(kl) > n_split + 20}
        sh_kl_in = sh_kl[:n_split]
        sh_kl_out = sh_kl[n_split:]

        # Run backtests: A+MA10, A+MA15, A+MA20 (旋转模型配置扫描) — 样本内
        configs = [
            ("MA10", 1, "配置A+MA10(旋转模型基准)"),
            ("MA15", 1, "配置A+MA15(旋转模型最优)"),
            ("MA20", 1, "配置A+MA20(宽离场)"),
            ("MA15", 2, "配置A+MA15+2仓分散(组合化建议#3)"),
            ("MA15", 3, "配置A+MA15+3仓分散"),
        ]

        print(f"\n  [样本内] 前{n_split}日 (60%):")
        print(f"  {'配置':<30} {'收益':>8} {'年化':>8} {'回撤':>6} {'胜率':>6} {'盈亏比':>6} {'中位':>7} {'利用':>6} {'方向超额':>8} {'交易':>5}")
        print("  " + "-" * 110)

        bt_results = []
        for exit_line, n_pos, label in configs:
            bt = RotationBacktest(exit_line=exit_line, num_positions=n_pos,
                                   initial_cash=1000000)
            result = bt.run(stock_kl_in, sh_kl_in)
            bt_results.append({"label": label, "result": result})

            print(f"  {label:<30} {result['total_return_pct']:>7.1f}% {result['annual_return_pct']:>7.1f}% {result['max_drawdown_pct']:>5.1f}% {result['win_rate']:>5.1f}% {result['profit_factor']:>6.2f} {result['median_pnl_pct']:>6.2f}% {result['utilization_pct']:>5.1f}% {result['direction_excess_pp']:>6.1f}pp {result['n_trades']:>5}")

        # v3.1新增: 样本外验证
        print(f"\n  [样本外] 后{n_total-n_split}日 (40% blind test):")
        print(f"  {'配置':<30} {'收益':>8} {'年化':>8} {'回撤':>6} {'胜率':>6} {'盈亏比':>6} {'中位':>7} {'利用':>6} {'方向超额':>8} {'交易':>5}")
        print("  " + "-" * 110)

        oos_results = []
        if stock_kl_out and len(sh_kl_out) > 20:
            for exit_line, n_pos, label in configs:
                bt = RotationBacktest(exit_line=exit_line, num_positions=n_pos,
                                       initial_cash=1000000)
                result = bt.run(stock_kl_out, sh_kl_out)
                oos_results.append({"label": label, "result": result})
                print(f"  {label:<30} {result['total_return_pct']:>7.1f}% {result['annual_return_pct']:>7.1f}% {result['max_drawdown_pct']:>5.1f}% {result['win_rate']:>5.1f}% {result['profit_factor']:>6.2f} {result['median_pnl_pct']:>6.2f}% {result['utilization_pct']:>5.1f}% {result['direction_excess_pp']:>6.1f}pp {result['n_trades']:>5}")

            # OOS对比分析
            print(f"\n  [样本内 vs 样本外对比]:")
            print(f"  {'配置':<30} {'样本内收益':>10} {'样本外收益':>10} {'衰减率':>8}")
            for i in range(len(bt_results)):
                in_r = bt_results[i]["result"]["total_return_pct"]
                out_r = oos_results[i]["result"]["total_return_pct"] if i < len(oos_results) else 0
                decay = (out_r / in_r * 100) if in_r != 0 else 0
                print(f"  {bt_results[i]['label']:<30} {in_r:>9.1f}% {out_r:>9.1f}% {decay:>7.1f}%")
        else:
            print(f"  ⚠️ 样本外数据不足,跳过OOS验证")

        # Find best
        best = max(bt_results, key=lambda x: x["result"]["total_return_pct"])
        print(f"\n  🏆 最优配置: {best['label']}")
        print(f"     累计收益: +{best['result']['total_return_pct']:.1f}% | 年化: +{best['result']['annual_return_pct']:.1f}%")
        print(f"     最大回撤: {best['result']['max_drawdown_pct']:.1f}% | 胜率: {best['result']['win_rate']:.1f}%")
        print(f"     资金利用: {best['result']['utilization_pct']:.1f}% | 方向超额: +{best['result']['direction_excess_pp']:.1f}pp")
        print(f"     盈亏比: {best['result']['profit_factor']:.2f} | 交易次数: {best['result']['n_trades']}")

        # Trade analysis
        best_trades = best["result"]["trades"]
        if best_trades:
            print(f"\n  📊 交易明细 (前10笔 + 末5笔):")
            print(f"  {'序号':<4} {'代码':<8} {'买入日':>4} {'卖出日':>4} {'买入价':>8} {'卖出价':>8} {'盈亏%':>7} {'持仓':>4} {'离场原因'}")
            print("  " + "-"*75)
            for i, t in enumerate(best_trades[:10]):
                print(f"  {i+1:<4} {t['code']:<8} {t['entry_day']:>4} {t['exit_day']:>4} {t['entry_price']:>8.2f} {t['exit_price']:>8.2f} {t['pnl_pct']:>6.2f}% {t['hold_days']:>3}d {t['reason']}")
            if len(best_trades) > 15:
                print(f"  ... ({len(best_trades)-15} more)")
            for i, t in enumerate(best_trades[-5:]):
                idx = len(best_trades) - 5 + i
                print(f"  {idx+1:<4} {t['code']:<8} {t['entry_day']:>4} {t['exit_day']:>4} {t['entry_price']:>8.2f} {t['exit_price']:>8.2f} {t['pnl_pct']:>6.2f}% {t['hold_days']:>3}d {t['reason']}")

            # Exit reason distribution
            from collections import Counter
            reasons = Counter(t["reason"].split("(")[0] for t in best_trades)
            print(f"\n  📊 离场原因分布:")
            for reason, count in reasons.most_common():
                print(f"     {reason}: {count}次 ({count/len(best_trades)*100:.1f}%)")

        # Save backtest results — v3.1修复: 同时保存样本内+样本外+衰减率
        def _bt_to_dict(bt_r):
            r = bt_r["result"]
            return {
                "label": bt_r["label"],
                "total_return": r["total_return_pct"],
                "annual_return": r["annual_return_pct"],
                "max_drawdown": r["max_drawdown_pct"],
                "win_rate": r["win_rate"],
                "profit_factor": r["profit_factor"],
                "median_pnl": r["median_pnl_pct"],
                "avg_hold": r["avg_hold_days"],
                "n_trades": r["n_trades"],
                "utilization": r["utilization_pct"],
                "direction_excess": r["direction_excess_pp"],
            }

        bt_save = {
            "run_timestamp": run_timestamp,
            "version": "v3.1",
            "n_total_days": n_total,
            "n_in_sample": n_split,
            "n_out_sample": n_total - n_split,
            "in_sample": [_bt_to_dict(bt_r) for bt_r in bt_results],
        }
        if oos_results:
            bt_save["out_sample"] = [_bt_to_dict(oos_r) for oos_r in oos_results]
            # 衰减率表
            bt_save["decay_rates"] = []
            for i in range(len(bt_results)):
                in_r = bt_results[i]["result"]["total_return_pct"]
                out_r = oos_results[i]["result"]["total_return_pct"] if i < len(oos_results) else 0
                decay = round(out_r / in_r * 100, 1) if in_r != 0 else 0
                bt_save["decay_rates"].append({
                    "label": bt_results[i]["label"],
                    "in_return": in_r,
                    "out_return": out_r,
                    "decay_rate": decay,
                })
        try:
            from core.config import OUTPUT_BACKTEST_DIR
            bt_out_path = OUTPUT_BACKTEST_DIR / "v3_backtest_results.json"
        except Exception:
            bt_out_path = Path(__file__).resolve().parent / "v3_backtest_results.json"
        with open(str(bt_out_path), "w", encoding="utf-8") as f:
            json.dump(bt_save, f, ensure_ascii=False, indent=2)

    # Save v3 results (v3.1: 加时间戳)
    all_results_with_meta = {
        "run_timestamp": run_timestamp,
        "version": "v3.1",
        "market_state": model.gate.state,
        "market_score": model.gate.health_score,
        "gate_open": model.gate.gate_open,
        "results": all_results
    }
    try:
        from core.config import OUTPUT_CACHE_DIR
        out = os.path.join(str(OUTPUT_CACHE_DIR), "v3_model_results.json")
    except Exception:
        out = os.path.join(os.path.dirname(__file__), "v3_model_results.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(all_results_with_meta, f, ensure_ascii=False, indent=2)

    print(f"\n  结果已保存:")
    print(f"    截面评估: {out}")
    print(f"    回测结果: {bt_out_path if 'bt_out_path' in locals() else 'v3_backtest_results.json'}")