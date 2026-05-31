"""
回测引擎 — 把策略评分在历史数据上模拟交易，给出绩效与风险指标。

核心原则（避免未来函数）：
  · 第 i 天收盘后用「截至第 i 天」的数据算综合评分
  · 据此决定的买/卖，在「第 i+1 天开盘价」成交
  · 每笔交易扣除手续费 + 滑点

综合评分 = 均线策略与动量策略的加权平均（价值策略依赖实时基本面，
          无历史序列，故不参与回测）。
"""
import numpy as np
import pandas as pd

from strategies import strategy_ma, strategy_momentum

TRADING_DAYS = 252  # 年化用


def combined_score_series(df: pd.DataFrame, w_ma: float, w_mo: float) -> np.ndarray:
    """逐日计算综合评分（0-100）。返回与 df 等长的数组，无未来函数。"""
    dm = strategy_ma.add_indicators(df)
    dmo = strategy_momentum.add_indicators(df)
    n = len(df)
    scores = np.full(n, np.nan)
    wsum = w_ma + w_mo
    for i in range(n):
        s_ma = strategy_ma.score_at(dm, i)[0]
        s_mo = strategy_momentum.score_at(dmo, i)[0]
        if i >= strategy_ma.MIN_BARS - 1:        # 两策略都可用
            scores[i] = (w_ma * s_ma + w_mo * s_mo) / wsum
        elif i >= strategy_momentum.MIN_BARS - 1:  # 仅动量可用
            scores[i] = s_mo
    return scores


def _metrics(equity: pd.Series, n_days: int) -> dict:
    """从净值序列计算绩效指标。equity 为归一化净值（起点1.0）。"""
    total_return = float(equity.iloc[-1] - 1.0)
    years = n_days / TRADING_DAYS
    annual = float(equity.iloc[-1] ** (1 / years) - 1) if years > 0 and equity.iloc[-1] > 0 else 0.0

    daily_ret = equity.pct_change().dropna()
    if len(daily_ret) > 1 and daily_ret.std() > 0:
        sharpe = float(daily_ret.mean() / daily_ret.std() * np.sqrt(TRADING_DAYS))
    else:
        sharpe = 0.0

    running_max = equity.cummax()
    drawdown = equity / running_max - 1.0
    max_dd = float(drawdown.min())

    return {
        "total_return": round(total_return * 100, 2),
        "annual_return": round(annual * 100, 2),
        "sharpe": round(sharpe, 2),
        "max_drawdown": round(max_dd * 100, 2),
    }


def run_backtest(df: pd.DataFrame, w_ma: float = 1.0, w_mo: float = 1.0,
                 buy_th: float = 50.0, sell_th: float = 25.0,
                 cost: float = 0.001) -> dict:
    """
    df:    含 date/open/high/low/close/volume，按日期升序
    buy_th/sell_th: 综合评分买入/卖出阈值
    cost:  单边交易成本（手续费+滑点），默认 0.1%
    """
    if df is None or df.empty or len(df) < strategy_ma.MIN_BARS + 5:
        return {"error": "数据不足，无法回测（至少需约 70 个交易日）"}

    df = df.sort_values("date").reset_index(drop=True)
    scores = combined_score_series(df, w_ma, w_mo)
    n = len(df)
    opens = df["open"].values
    closes = df["close"].values

    cash = 1.0           # 初始资金归一化为 1
    shares = 0.0         # 持仓份额
    holding = False
    equity = np.empty(n)
    trades = []          # 每笔完整交易 (buy_price, sell_price, ret)
    buy_price = 0.0
    n_trades = 0

    # 第一个可评分日之前净值恒为 1
    first = strategy_momentum.MIN_BARS - 1
    for i in range(n):
        # 当日净值（按当日收盘价计）
        equity[i] = cash + shares * closes[i]

        if i < first or i >= n - 1:
            continue  # 无评分 或 最后一天无次日开盘可成交

        s = scores[i]
        if np.isnan(s):
            continue
        exec_price = opens[i + 1]  # 次日开盘成交，避免未来函数

        if not holding and s >= buy_th:
            # 全仓买入，扣成本
            eff = exec_price * (1 + cost)
            shares = cash / eff
            cash = 0.0
            holding = True
            buy_price = eff
            n_trades += 1
        elif holding and s <= sell_th:
            eff = exec_price * (1 - cost)
            cash = shares * eff
            trades.append((buy_price, eff, eff / buy_price - 1))
            shares = 0.0
            holding = False

    # 收盘清算最后一天净值
    equity[-1] = cash + shares * closes[-1]
    if holding:  # 期末仍持仓，按最后收盘价记一笔未平仓收益用于胜率统计
        trades.append((buy_price, closes[-1], closes[-1] / buy_price - 1))

    eq = pd.Series(equity)
    strat = _metrics(eq, n)

    # 买入持有基准：首个可评分日开盘买入，持有到末日收盘
    bh_entry = opens[first + 1] if first + 1 < n else opens[first]
    bh_equity = pd.Series(closes / bh_entry)
    bench = _metrics(bh_equity, n)

    wins = [t for t in trades if t[2] > 0]
    win_rate = round(len(wins) / len(trades) * 100, 1) if trades else 0.0

    dates = df["date"].dt.strftime("%Y-%m-%d").tolist()
    return {
        "metrics": {
            **strat,
            "n_trades": n_trades,
            "win_rate": win_rate,
        },
        "benchmark": bench,
        "params": {"w_ma": w_ma, "w_mo": w_mo, "buy_th": buy_th,
                   "sell_th": sell_th, "cost": cost},
        "curve": {
            "date": dates,
            "strategy": [round(x, 4) for x in equity.tolist()],
            "benchmark": [round(x, 4) for x in bh_equity.tolist()],
            "score": [None if np.isnan(x) else round(float(x), 1) for x in scores],
        },
        "period": {"start": dates[0], "end": dates[-1], "days": n},
    }
