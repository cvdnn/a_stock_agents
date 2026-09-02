"""
A-Share Quant Engine - Unstructured Factors (非结构化特征与舆情因子引擎)
功能:
1. 财经新闻、公告与研报文本的情感量化打分
2. 关键事件分类识别 (业绩预增/预减、增减持、问询调查、重大订单、股权激励等)
3. 指数半衰期时间衰减模型 (Exponential Half-Life Decay)
4. 输出归一化的数值型舆情因子 [-1.0, +1.0]
"""

import math
import time
from typing import Dict, List, Any, Optional, Tuple


class UnstructuredFactors:
    """非结构化文本与事件情感因子量化引擎"""

    # 预置 A股高敏感度金融情感词典与权重
    POSITIVE_KEYWORDS = {
        "预增": 0.8, "大幅增长": 0.9, "超预期": 0.85, "扭亏为盈": 0.75, "净利润增长": 0.7,
        "回购": 0.65, "增持": 0.6, "股权激励": 0.5, "员工持股": 0.45,
        "中标": 0.6, "签订大单": 0.7, "战略合作": 0.4, "重大突破": 0.65, "获批": 0.5,
        "龙头": 0.3, "涨价": 0.5, "订单饱满": 0.6, "产能扩产": 0.4, "高送转": 0.45
    }

    NEGATIVE_KEYWORDS = {
        "预减": -0.8, "亏损": -0.75, "大幅下滑": -0.85, "业绩变脸": -0.9,
        "立案调查": -0.95, "问询函": -0.6, "监管警示": -0.65, "通报批评": -0.7,
        "减持": -0.65, "清仓式减持": -0.85, "违规占用": -0.9, "财务造假": -1.0,
        "违约": -0.8, "债务危机": -0.85, "冻结": -0.7, "诉讼": -0.5, "败诉": -0.65,
        "重组失败": -0.8, "终止上市": -1.0, "退市风险": -0.9, "暴雷": -0.9
    }

    EVENT_WEIGHTS = {
        "EARNINGS_SURPRISE_UP": 0.85,      # 业绩大幅超预期
        "EARNINGS_UP": 0.60,               # 业绩稳健增长
        "EARNINGS_DOWN": -0.65,            # 业绩下滑
        "EARNINGS_LOSS": -0.85,            # 业绩巨亏
        "SHARE_BUYBACK": 0.65,             # 股份回购注销
        "MAJOR_CONTRACT": 0.55,            # 重大商业合同/中标
        "INSIDER_INCREASE": 0.50,          # 高管/大股东增持
        "INSIDER_REDUCE": -0.60,           # 高管/大股东减持
        "REGULATORY_INQUIRY": -0.70,       # 监管函/立案调查
        "DEBT_DEFAULT": -0.90,             # 债务违约
    }

    @classmethod
    def score_text(cls, text: str) -> float:
        """对单段新闻/公告文本进行情感极性评分 [-1.0, +1.0]"""
        if not text:
            return 0.0
        
        pos_score = 0.0
        neg_score = 0.0
        
        for kw, weight in cls.POSITIVE_KEYWORDS.items():
            if kw in text:
                pos_score += weight
                
        for kw, weight in cls.NEGATIVE_KEYWORDS.items():
            if kw in text:
                neg_score += abs(weight)
                
        total = pos_score + neg_score
        if total == 0:
            return 0.0
            
        raw_sentiment = (pos_score - neg_score) / (total + 0.5)
        # 裁剪到 [-1.0, 1.0]
        return max(-1.0, min(1.0, round(raw_sentiment, 3)))

    @classmethod
    def apply_decay(cls, initial_score: float, days_elapsed: float, half_life_days: float = 3.0) -> float:
        """应用指数半衰期时间衰减: S(t) = S0 * 2^(-dt / half_life)"""
        if initial_score == 0.0 or days_elapsed <= 0:
            return initial_score
        decay_factor = math.pow(2.0, -days_elapsed / half_life_days)
        return round(initial_score * decay_factor, 4)

    @classmethod
    def aggregate_news_sentiment(
        cls, 
        news_items: List[Dict[str, Any]], 
        current_date_ts: Optional[float] = None,
        half_life_days: float = 3.0
    ) -> Dict[str, Any]:
        """聚合近期多条新闻/公告，计算衰减后的综合情绪因子
        news_items 格式: [{'title': '...', 'content': '...', 'timestamp': 1700000000, 'event_type': '...'}, ...]
        """
        if not news_items:
            return {
                "sentiment_score": 0.0,
                "news_count": 0,
                "dominant_event": "NONE",
                "confidence": 0.0
            }

        now_ts = current_date_ts if current_date_ts else time.time()
        weighted_scores = []
        weights = []
        events_found = []

        for item in news_items:
            title = item.get("title", "")
            content = item.get("content", "")
            full_text = f"{title} {content}"
            
            # 基础文本分
            text_score = cls.score_text(full_text)
            
            # 事件类型修正
            event_type = item.get("event_type")
            if event_type and event_type in cls.EVENT_WEIGHTS:
                event_score = cls.EVENT_WEIGHTS[event_type]
                score = 0.5 * text_score + 0.5 * event_score
                events_found.append(event_type)
            else:
                score = text_score
            
            # 计算发布距离现在的天数
            item_ts = item.get("timestamp", now_ts)
            days_ago = max(0.0, (now_ts - item_ts) / 86400.0)
            
            # 时间衰减后的得分
            decayed = cls.apply_decay(score, days_ago, half_life_days)
            
            # 权重随时间递减
            w = math.pow(2.0, -days_ago / half_life_days)
            weighted_scores.append(decayed * w)
            weights.append(w)

        total_weight = sum(weights)
        if total_weight == 0:
            final_sentiment = 0.0
        else:
            final_sentiment = sum(weighted_scores) / total_weight

        final_sentiment = max(-1.0, min(1.0, round(final_sentiment, 3)))
        dominant_event = events_found[0] if events_found else "GENERAL_NEWS"

        return {
            "sentiment_score": final_sentiment,
            "news_count": len(news_items),
            "dominant_event": dominant_event,
            "confidence": min(1.0, round(total_weight / 3.0, 2))
        }
