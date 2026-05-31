"""
策略二：低估值价值选股策略（基本面）
逻辑：PE低于行业均值、ROE高、净利润增长、市值门槛
"""
import pandas as pd


# 各市场行业PE参考基准（简化版，实际可接入行业数据）
INDUSTRY_PE_BENCHMARK = {
    "default": 25,
    "tech": 35,
    "finance": 12,
    "consumer": 28,
    "energy": 15,
    "healthcare": 40,
    "real_estate": 18,
}


def run(df: pd.DataFrame, fundamentals: dict) -> dict:
    detail = []
    score = 0

    pe = fundamentals.get("pe")
    pb = fundamentals.get("pb")
    roe = fundamentals.get("roe")
    market_cap = fundamentals.get("market_cap")

    # yfinance 有时返回字符串，强制转数字
    try:
        pe = float(pe) if pe is not None else None
    except (TypeError, ValueError):
        pe = None
    try:
        pb = float(pb) if pb is not None else None
    except (TypeError, ValueError):
        pb = None
    try:
        roe = float(roe) if roe is not None else None
    except (TypeError, ValueError):
        roe = None
    try:
        market_cap = float(market_cap) if market_cap is not None else None
    except (TypeError, ValueError):
        market_cap = None

    # 条件1：PE合理（< 30，或有数据）
    if pe is not None and pe > 0:
        c1 = pe < 30
        detail.append({
            "name": "PE < 30（估值合理）",
            "pass": bool(c1),
            "value": f"PE={pe:.1f}"
        })
        if c1:
            score += 25
        elif pe < 50:
            score += 10
    else:
        detail.append({
            "name": "PE（估值）",
            "pass": False,
            "value": "数据不可用"
        })

    # 条件2：PB合理（< 5）
    if pb is not None and pb > 0:
        c2 = pb < 5
        detail.append({
            "name": "PB < 5（资产估值）",
            "pass": bool(c2),
            "value": f"PB={pb:.2f}"
        })
        if c2:
            score += 20
    else:
        detail.append({
            "name": "PB（市净率）",
            "pass": False,
            "value": "数据不可用"
        })

    # 条件3：ROE > 15%（盈利能力）
    if roe is not None:
        roe_pct = roe * 100 if roe < 1 else roe  # 兼容小数和百分比
        c3 = roe_pct > 15
        detail.append({
            "name": "ROE > 15%（盈利能力）",
            "pass": bool(c3),
            "value": f"ROE={roe_pct:.1f}%"
        })
        if c3:
            score += 30
        elif roe_pct > 10:
            score += 15
    else:
        detail.append({
            "name": "ROE（净资产收益率）",
            "pass": False,
            "value": "数据不可用"
        })

    # 条件4：市值门槛（> 50亿，流动性保障）
    if market_cap is not None and market_cap > 0:
        cap_b = market_cap / 1e8  # 转换为亿
        c4 = cap_b > 50
        detail.append({
            "name": "市值 > 50亿（流动性）",
            "pass": bool(c4),
            "value": f"市值≈{cap_b:.0f}亿"
        })
        if c4:
            score += 25
    else:
        detail.append({
            "name": "市值",
            "pass": False,
            "value": "数据不可用"
        })

    # 价格趋势辅助判断（近期是否在低位）
    if not df.empty and len(df) >= 60:
        latest_close = float(df.iloc[-1]["close"])
        high_60 = float(df["close"].tail(60).max())
        low_60 = float(df["close"].tail(60).min())
        position = (latest_close - low_60) / (high_60 - low_60) if high_60 != low_60 else 0.5
        in_low_zone = position < 0.35
        detail.append({
            "name": "价格处于60日低位区间",
            "pass": bool(in_low_zone),
            "value": f"当前价格处于60日区间{position*100:.0f}%位置"
        })
        # 低位加分（不计入主分）

    # 综合判断
    if score >= 70:
        signal = "低估值买入机会"
        color = "green"
    elif score >= 45:
        signal = "估值尚可，可关注"
        color = "orange"
    elif score >= 20:
        signal = "估值偏高，谨慎"
        color = "gray"
    else:
        signal = "估值过高或数据不足"
        color = "red"

    return {
        "strategy": "低估值价值策略",
        "signal": signal,
        "color": color,
        "score": score,
        "detail": detail,
        "fundamentals": {
            "PE": f"{pe:.1f}" if pe else "N/A",
            "PB": f"{pb:.2f}" if pb else "N/A",
            "ROE": f"{roe*100:.1f}%" if roe else "N/A",
        }
    }
