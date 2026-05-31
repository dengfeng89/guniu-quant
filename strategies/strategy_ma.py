"""
策略一：均线金叉策略（趋势跟踪）
逻辑：MA5上穿MA20，MA20上穿MA60，成交量放大
"""
import pandas as pd

MIN_BARS = 65  # 评分所需最少K线数（MA60 + 金叉回看）


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """一次性计算所有指标，供 run / 回测复用。"""
    df = df.copy()
    df["MA5"] = df["close"].rolling(5).mean()
    df["MA20"] = df["close"].rolling(20).mean()
    df["MA60"] = df["close"].rolling(60).mean()
    df["vol_ma20"] = df["volume"].rolling(20).mean()
    return df


def score_at(df: pd.DataFrame, i: int):
    """对第 i 天评分，只使用截至第 i 天的数据（无未来函数）。
    返回 (score, detail)。df 必须已 add_indicators。"""
    if i < MIN_BARS - 1:
        return 0, []
    row = df.iloc[i]
    detail = []
    score = 0

    c1 = row["MA5"] > row["MA20"]
    detail.append({"name": "MA5 > MA20（短期趋势）", "pass": bool(c1),
                   "value": f"MA5={row['MA5']:.2f}  MA20={row['MA20']:.2f}"})
    if c1:
        score += 25

    c2 = row["MA20"] > row["MA60"]
    detail.append({"name": "MA20 > MA60（中期趋势）", "pass": bool(c2),
                   "value": f"MA20={row['MA20']:.2f}  MA60={row['MA60']:.2f}"})
    if c2:
        score += 25

    recent = df.iloc[i - 4:i + 1]
    golden_cross = any(
        (recent["MA5"].iloc[j] > recent["MA20"].iloc[j]) and
        (recent["MA5"].iloc[j - 1] <= recent["MA20"].iloc[j - 1])
        for j in range(1, len(recent))
    )
    detail.append({"name": "近5日金叉信号", "pass": bool(golden_cross),
                   "value": "近5日内MA5上穿MA20" if golden_cross else "未检测到金叉"})
    if golden_cross:
        score += 30

    c4 = row["volume"] > row["vol_ma20"] * 1.5
    vol_ratio = row["volume"] / row["vol_ma20"] if row["vol_ma20"] > 0 else 0
    detail.append({"name": "成交量放大（>1.5倍均量）", "pass": bool(c4),
                   "value": f"量比={vol_ratio:.2f}x"})
    if c4:
        score += 20

    return score, detail


def _verdict(score):
    if score >= 75:
        return "强烈买入", "green"
    if score >= 50:
        return "可以关注", "orange"
    if score >= 25:
        return "观望为主", "gray"
    return "不建议买入", "red"


def run(df: pd.DataFrame) -> dict:
    if df.empty or len(df) < MIN_BARS:
        return {"signal": "数据不足", "score": 0, "detail": []}

    df = add_indicators(df)
    i = len(df) - 1
    score, detail = score_at(df, i)
    signal, color = _verdict(score)
    latest = df.iloc[i]

    chart_data = df.tail(60)[["date", "close", "MA5", "MA20", "MA60"]].copy()
    chart_data["date"] = chart_data["date"].dt.strftime("%Y-%m-%d")
    chart_data = chart_data.fillna(0)

    return {
        "strategy": "均线金叉策略",
        "signal": signal,
        "color": color,
        "score": score,
        "detail": detail,
        "chart": chart_data.to_dict(orient="list"),
        "latest_price": round(float(latest["close"]), 3),
        "latest_date": latest["date"].strftime("%Y-%m-%d")
    }
