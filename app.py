"""
古牛量化 — Flask 后端 API
"""
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import sys
import os
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout

sys.path.insert(0, os.path.dirname(__file__))

from data_fetcher import (get_price_data, get_fundamentals, detect_market,
                          get_network_status)
from strategies import strategy_ma, strategy_value, strategy_momentum
import backtest

app = Flask(__name__)
CORS(app)

# 有界线程池：限制并发抓取数。配合数据层每个 HTTP 请求自带的超时，
# 即使某次抓取慢，也只占用池中一个 worker 并会自行结束，不会无限堆积僵尸线程。
_pool = ThreadPoolExecutor(max_workers=4)


def fetch_with_timeout(code, days, seconds=90):
    """提交抓取任务到有界线程池，最多等待 seconds 秒。
    返回 (df, error)。超时仅放弃等待，worker 因 HTTP 超时会自行退出。"""
    future = _pool.submit(get_price_data, code, days)
    try:
        return future.result(timeout=seconds), None
    except FutureTimeout:
        return None, f"数据获取超时（{seconds}s）"
    except Exception as e:
        return None, str(e)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/analyze", methods=["POST"])
def analyze():
    data = request.get_json()
    code = data.get("code", "").strip()

    if not code:
        return jsonify({"error": "请输入股票代码"}), 400

    market = detect_market(code)
    if market == "unknown":
        return jsonify({"error": f"无法识别「{code}」，请检查格式"}), 400

    market_label = {"a": "A股", "hk": "港股", "us": "美股"}.get(market, "未知")

    df, err = fetch_with_timeout(code, 150)
    if err or df is None or df.empty:
        hint = "（A股需要 VPN）" if market == "a" else ""
        return jsonify({"error": f"获取 {code} {market_label} 数据失败{hint}"}), 400

    fundamentals = get_fundamentals(code)

    result_ma       = strategy_ma.run(df)
    result_value    = strategy_value.run(df, fundamentals)
    result_momentum = strategy_momentum.run(df)

    total_score = (result_ma["score"] + result_value["score"] + result_momentum["score"]) / 3

    if total_score >= 65:
        overall, overall_color = "综合来看：现在是较好的买入时机 ✅", "green"
    elif total_score >= 40:
        overall, overall_color = "综合来看：可以小仓关注，等待更好信号 ⚠️", "orange"
    else:
        overall, overall_color = "综合来看：暂不建议买入，继续观望 ❌", "red"

    return jsonify({
        "code": code.upper(),
        "market": market_label,
        "latest_price": result_ma.get("latest_price") or result_momentum.get("latest_price"),
        "latest_date": result_ma.get("latest_date") or result_momentum.get("latest_date"),
        "overall": overall,
        "overall_color": overall_color,
        "total_score": round(total_score, 1),
        "strategies": [result_ma, result_value, result_momentum],
        "network_status": get_network_status()
    })


@app.route("/api/backtest", methods=["POST"])
def api_backtest():
    data = request.get_json() or {}
    code = data.get("code", "").strip()
    if not code:
        return jsonify({"error": "请输入股票代码"}), 400

    market = detect_market(code)
    market_label = {"a": "A股", "hk": "港股", "us": "美股"}.get(market, "未知")

    # 回测需要更长历史，尽量多取
    days = int(data.get("days", 600))
    try:
        w_ma = float(data.get("w_ma", 1.0))
        w_mo = float(data.get("w_mo", 1.0))
        buy_th = float(data.get("buy_th", 50.0))
        sell_th = float(data.get("sell_th", 25.0))
        cost = float(data.get("cost", 0.001))
    except (TypeError, ValueError):
        return jsonify({"error": "参数格式不正确"}), 400

    df, err = fetch_with_timeout(code, days, seconds=120)
    if err or df is None or df.empty:
        hint = "（A股需要 VPN）" if market == "a" else ""
        return jsonify({"error": f"获取 {code} {market_label} 数据失败{hint}"}), 400

    result = backtest.run_backtest(df, w_ma=w_ma, w_mo=w_mo,
                                   buy_th=buy_th, sell_th=sell_th, cost=cost)
    if "error" in result:
        return jsonify(result), 400

    result["code"] = code.upper()
    result["market"] = market_label
    return jsonify(result)


@app.route("/api/status")
def status():
    return jsonify({"ok": True})


if __name__ == "__main__":
    print("=" * 50)
    print("🐂 古牛量化系统启动中...")
    print("访问地址: http://127.0.0.1:5888")
    print("=" * 50)
    app.run(host="127.0.0.1", port=5888, debug=False, threaded=True)
