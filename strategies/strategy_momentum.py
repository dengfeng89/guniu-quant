"""
策略三：动量反转策略（超跌反弹）
逻辑：RSI超卖 + 布林带下轨 + 价格企稳信号
"""
import pandas as pd
import numpy as np

MIN_BARS = 30


def calc_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def calc_bollinger(series: pd.Series, period: int = 20, std_dev: float = 2.0):
    mid = series.rolling(period).mean()
    std = series.rolling(period).std()
    return mid + std_dev * std, mid, mid - std_dev * std


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["RSI"] = calc_rsi(df["close"], 14)
    df["BB_upper"], df["BB_mid"], df["BB_lower"] = calc_bollinger(df["close"], 20)
    df["MA5"] = df["close"].rolling(5).mean()
    return df


def score_at(df: pd.DataFrame, i: int):
    """对第 i 天评分，只用截至第 i 天的数据。返回 (score, detail)。"""
    if i < MIN_BARS - 1:
        return 0, []
    row = df.iloc[i]
    detail = []
    score = 0

    rsi_val = float(row["RSI"]) if not pd.isna(row["RSI"]) else 50
    c1 = rsi_val < 35
    c1_mild = rsi_val < 45
    detail.append({"name": "RSI超卖（< 35）", "pass": bool(c1),
                   "value": f"RSI={rsi_val:.1f}{'  ⚡超卖区间' if c1 else ('  接近超卖' if c1_mild else '')}"})
    if c1:
        score += 35
    elif c1_mild:
        score += 15

    bb_lower = float(row["BB_lower"]) if not pd.isna(row["BB_lower"]) else 0
    bb_mid = float(row["BB_mid"]) if not pd.isna(row["BB_mid"]) else 0
    close = float(row["close"])
    c2 = close <= bb_lower * 1.02
    bb_position = (close - bb_lower) / (bb_mid - bb_lower) if bb_mid != bb_lower else 1
    detail.append({"name": "价格触及布林带下轨", "pass": bool(c2),
                   "value": f"当前价={close:.3f}  下轨={bb_lower:.3f}  位置={bb_position:.2f}"})
    if c2:
        score += 30

    recent_lows = df["low"].iloc[i - 3:i + 1].values
    stabilizing = recent_lows[-1] >= min(recent_lows[:-1])
    detail.append({"name": "价格企稳（近3日不创新低）", "pass": bool(stabilizing),
                   "value": "近3日低点未再下探" if stabilizing else "仍在下跌中"})
    if stabilizing:
        score += 20

    if i >= 20:
        price_20d_ago = float(df.iloc[i - 19]["close"])
        drawdown = (close - price_20d_ago) / price_20d_ago * 100
        c4 = drawdown < -10
        detail.append({"name": "近20日跌幅 > 10%（有反弹空间）", "pass": bool(c4),
                       "value": f"近20日涨跌幅={drawdown:.1f}%"})
        if c4:
            score += 15

    return score, detail


def _verdict(score):
    if score >= 70:
        return "超跌反弹机会", "green"
    if score >= 45:
        return "可以小仓试探", "orange"
    if score >= 20:
        return "尚未到底，继续观察", "gray"
    return "不具备反弹条件", "red"


def run(df: pd.DataFrame) -> dict:
    if df.empty or len(df) < MIN_BARS:
        return {"signal": "数据不足", "score": 0, "detail": []}

    df = add_indicators(df)
    i = len(df) - 1
    score, detail = score_at(df, i)
    signal, color = _verdict(score)
    latest = df.iloc[i]

    chart_data = df.tail(60)[["date", "close", "RSI", "BB_upper", "BB_mid", "BB_lower"]].copy()
    chart_data["date"] = chart_data["date"].dt.strftime("%Y-%m-%d")
    chart_data = chart_data.fillna(0)

    return {
        "strategy": "动量反转策略",
        "signal": signal,
        "color": color,
        "score": score,
        "detail": detail,
        "chart": chart_data.to_dict(orient="list"),
        "latest_price": round(float(latest["close"]), 3),
        "latest_date": latest["date"].strftime("%Y-%m-%d")
    }
