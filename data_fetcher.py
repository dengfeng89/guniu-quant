"""
数据获取层 — 支持 A股 / 港股 / 美股
数据源：
  港股  → 腾讯财经（curl_cffi，主力）→ yfinance（备胎）
  美股  → Alpha Vantage（主力）→ yfinance（备胎）
  A股   → akshare 东方财富（需 VPN）
"""
import yfinance as yf
import pandas as pd
import os
import time
import random
import json
from datetime import datetime, timedelta
from curl_cffi import requests as curlreq

# ── 全局状态 ───────────────────────────────────────────────
_hk_source = "tencent"   # 记录港股用了哪个数据源
# API Key 从环境变量读取，未设置时回退到公共 demo（额度极低，仅供试跑）
ALPHA_VANTAGE_KEY = os.environ.get("ALPHA_VANTAGE_KEY", "demo")

# ── 本地缓存 ───────────────────────────────────────────────
CACHE_DIR = os.path.join(os.path.dirname(__file__), ".cache")
CACHE_TTL = 6 * 3600  # 行情缓存有效期（秒），默认 6 小时


def _cache_path(code: str, days: int) -> str:
    os.makedirs(CACHE_DIR, exist_ok=True)
    safe = code.strip().upper().replace(os.sep, "_")
    return os.path.join(CACHE_DIR, f"{safe}_{days}.pkl")


def _delay(base: float = 0.8):
    time.sleep(base + random.uniform(0, 0.5))


# ════════════════════════════════════════════════════════════
# 市场识别
# ════════════════════════════════════════════════════════════
def detect_market(code: str) -> str:
    code = code.strip().upper()
    if code.isdigit() and len(code) <= 5:
        return "hk"
    if code.isdigit() and len(code) == 6:
        return "a"
    return "us"


# ════════════════════════════════════════════════════════════
# 港股 — 腾讯财经（主力，实时）
# ════════════════════════════════════════════════════════════
def _fetch_hk_tencent(code: str, days: int = 150) -> pd.DataFrame:
    """
    腾讯财经港股历史K线
    接口：proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get
    返回格式：[日期, 开盘, 收盘, 最高, 最低, 成交量, ...]
    """
    global _hk_source
    sym = f"hk{code.zfill(5)}"
    url = "https://proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get"
    params = {
        "_var": f"kline_dayqfq",
        "param": f"{sym},day,,,{days},qfq",
        "r": str(random.random())
    }

    for attempt in range(4):
        try:
            _delay(0.5)
            r = curlreq.get(url, params=params, timeout=15, impersonate="chrome")
            # 响应格式：kline_dayqfq={...}
            text = r.text
            json_str = text[text.index("=") + 1:]
            data = json.loads(json_str)

            if data.get("code") != 0:
                raise ValueError(f"腾讯接口返回错误: {data.get('msg')}")

            klines = data["data"][sym]["day"]
            rows = []
            for k in klines:
                # [日期, 开盘, 收盘, 最高, 最低, 成交量, ...]
                rows.append({
                    "date": pd.to_datetime(k[0]),
                    "open":   float(k[1]),
                    "close":  float(k[2]),
                    "high":   float(k[3]),
                    "low":    float(k[4]),
                    "volume": float(k[5]),
                })

            df = pd.DataFrame(rows)
            df = df.sort_values("date").reset_index(drop=True)
            _hk_source = "tencent"
            print(f"  [腾讯财经] {code} 获取 {len(df)} 行，最新: {df.iloc[-1]['date'].date()} 收盘={df.iloc[-1]['close']}")
            return df

        except Exception as e:
            wait = (attempt + 1) * 5
            print(f"  [腾讯财经] {code} 第{attempt+1}次失败，{wait}s后重试: {str(e)[:80]}")
            if attempt < 3:
                time.sleep(wait)

    raise RuntimeError(f"腾讯财经接口全部失败: {code}")


# ════════════════════════════════════════════════════════════
# 港股 — yfinance（备胎，有1天延迟）
# ════════════════════════════════════════════════════════════
def _fetch_hk_yfinance(code: str, days: int = 150) -> pd.DataFrame:
    global _hk_source
    end   = datetime.today()
    start = end - timedelta(days=days)
    num   = code.strip().lstrip("0").zfill(4)
    _delay(0.5)
    ticker = yf.Ticker(f"{num}.HK")
    df = ticker.history(start=start.strftime("%Y-%m-%d"), end=end.strftime("%Y-%m-%d"))
    if df.empty:
        raise ValueError(f"yfinance 无数据: {code}")
    df = df.reset_index()
    df = df.rename(columns={
        "Date": "date", "Open": "open", "High": "high",
        "Low": "low", "Close": "close", "Volume": "volume"
    })
    df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None)
    _hk_source = "yfinance"
    print(f"  [yfinance备胎] {code} 获取 {len(df)} 行（有1天延迟）")
    return df


# ════════════════════════════════════════════════════════════
# 美股 — Alpha Vantage（主力）
# ════════════════════════════════════════════════════════════
def _fetch_us(code: str, days: int = 150) -> pd.DataFrame:
    """
    Alpha Vantage 美股日线数据
    免费额度：25 次/天
    """
    code = code.strip().upper()
    
    # Alpha Vantage
    try:
        _delay(0.5)
        url = "https://www.alphavantage.co/query"
        params = {
            "function": "TIME_SERIES_DAILY",
            "symbol": code,
            "outputsize": "compact",  # 免费版只能用 compact（100天）
            "apikey": ALPHA_VANTAGE_KEY
        }
        resp = curlreq.get(url, params=params, impersonate="chrome120", timeout=15)
        data = resp.json()
        
        if "Time Series (Daily)" in data:
            ts = data["Time Series (Daily)"]
            rows = []
            for date_str, values in ts.items():
                rows.append({
                    "date": pd.to_datetime(date_str),
                    "open": float(values["1. open"]),
                    "high": float(values["2. high"]),
                    "low": float(values["3. low"]),
                    "close": float(values["4. close"]),
                    "volume": int(values["5. volume"])
                })
            df = pd.DataFrame(rows)
            df = df.sort_values("date").reset_index(drop=True)
            # 只取最近 N 天
            if len(df) > days:
                df = df.tail(days).reset_index(drop=True)
            print(f"  [Alpha Vantage] {code} 获取 {len(df)} 行")
            return df
        elif "Note" in data or "Information" in data:
            # API 限流提示，fallback 到 yfinance
            print(f"  [Alpha Vantage] 限流提示: {data.get('Note', data.get('Information', ''))}")
        else:
            print(f"  [Alpha Vantage] 无数据: {data}")
    except Exception as e:
        print(f"  [Alpha Vantage] 失败: {e}")
    
    # Fallback: yfinance
    print(f"  [yfinance备胎] 尝试获取 {code}...")
    return _fetch_us_yfinance(code, days)


def _fetch_us_yfinance(code: str, days: int = 150) -> pd.DataFrame:
    """yfinance 美股备胎"""
    end = datetime.today()
    start = end - timedelta(days=days)
    
    for attempt in range(3):
        try:
            _delay(1.5 + attempt * 1.0)
            ticker = yf.Ticker(code)
            df = ticker.history(start=start.strftime("%Y-%m-%d"), end=end.strftime("%Y-%m-%d"))
            if df.empty:
                raise ValueError(f"yfinance 美股无数据: {code}")
            df = df.reset_index()
            df = df.rename(columns={
                "Date": "date", "Open": "open", "High": "high",
                "Low": "low", "Close": "close", "Volume": "volume"
            })
            df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None)
            print(f"  [yfinance美股] {code} 获取 {len(df)} 行")
            return df
        except Exception as e:
            if "RateLimit" in str(type(e).__name__) or "429" in str(e):
                print(f"  [yfinance] 第{attempt+1}次被限流，等待重试...")
                time.sleep(5 + attempt * 5)
            else:
                raise e
    raise ValueError(f"yfinance 美股获取失败（限流）: {code}")


# ════════════════════════════════════════════════════════════
# A股 — akshare（需 VPN）
# ════════════════════════════════════════════════════════════
def _fetch_a(code: str, days: int = 150) -> pd.DataFrame:
    import akshare as ak
    end   = datetime.today()
    start = end - timedelta(days=days)
    _delay(1.5)
    df = ak.stock_zh_a_hist(
        symbol=code, period="daily",
        start_date=start.strftime("%Y%m%d"),
        end_date=end.strftime("%Y%m%d"),
        adjust="qfq"
    )
    return df.rename(columns={
        "日期": "date", "开盘": "open", "最高": "high",
        "最低": "low", "收盘": "close", "成交量": "volume"
    })


# ════════════════════════════════════════════════════════════
# 主入口（带本地缓存）
# ════════════════════════════════════════════════════════════
def get_price_data(code: str, days: int = 120, use_cache: bool = True) -> pd.DataFrame:
    """对外主入口：命中有效缓存直接返回，否则联网抓取并落盘。"""
    path = _cache_path(code, days)
    if use_cache and os.path.exists(path) and (time.time() - os.path.getmtime(path)) < CACHE_TTL:
        try:
            df = pd.read_pickle(path)
            print(f"  [缓存命中] {code} {len(df)} 行")
            return df
        except Exception:
            pass

    df = _fetch_price_data(code, days)

    if df is not None and not df.empty:
        try:
            df.to_pickle(path)
        except Exception as e:
            print(f"  [缓存写入失败] {e}")
    return df


def _fetch_price_data(code: str, days: int = 120) -> pd.DataFrame:
    market = detect_market(code)

    try:
        if market == "hk":
            try:
                df = _fetch_hk_tencent(code, days)
            except Exception as e:
                print(f"  腾讯接口失败，切换 yfinance: {e}")
                df = _fetch_hk_yfinance(code, days)
        elif market == "us":
            df = _fetch_us(code, days)
        elif market == "a":
            df = _fetch_a(code, days)
        else:
            return pd.DataFrame()
    except Exception as e:
        print(f"[get_price_data] {code} 全部失败: {e}")
        return pd.DataFrame()

    df["date"] = pd.to_datetime(df["date"])
    df = df[["date", "open", "high", "low", "close", "volume"]].copy()
    df = df.sort_values("date").reset_index(drop=True)
    df[["open", "high", "low", "close"]] = df[["open", "high", "low", "close"]].astype(float)
    df["volume"] = df["volume"].astype(float)

    if len(df) < 3:
        return pd.DataFrame()

    return df


# ════════════════════════════════════════════════════════════
# 基本面
# ════════════════════════════════════════════════════════════
def get_fundamentals(code: str) -> dict:
    result = {"pe": None, "pb": None, "roe": None, "market_cap": None}
    market = detect_market(code)

    # 港股实时快照（腾讯）
    if market == "hk":
        try:
            sym = f"hk{code.zfill(5)}"
            r = curlreq.get(
                f"https://web.sqt.gtimg.cn/q={sym}",
                timeout=10, impersonate="chrome"
            )
            # 格式: v_hk00700="700~腾讯控股~00700~481.600~..."
            text = r.text
            if "~" in text:
                parts = text.split('"')[1].split("~")
                # 字段顺序参考腾讯接口文档
                # 暂时只取 PE（字段位置不固定，用 yfinance 补充）
                pass
        except Exception:
            pass

    # yfinance 基本面（港股/美股）
    if market in ("us", "hk"):
        try:
            yf_code = code
            if market == "hk":
                num = code.strip().lstrip("0").zfill(4)
                yf_code = f"{num}.HK"
            _delay(0.5)
            info = yf.Ticker(yf_code).info
            result["pe"]  = info.get("trailingPE")
            result["pb"]  = info.get("priceToBook")
            result["roe"] = info.get("returnOnEquity")
            result["market_cap"] = info.get("marketCap")
        except Exception as e:
            print(f"[基本面] {code} yfinance 失败: {e}")

    elif market == "a":
        try:
            import akshare as ak
            _delay()
            df = ak.stock_a_lg_indicator(symbol=code)
            if not df.empty:
                latest = df.iloc[-1]
                result["pe"] = float(latest.get("pe", 0) or 0)
                result["pb"] = float(latest.get("pb", 0) or 0)
        except Exception as e:
            print(f"[基本面] {code} akshare 失败: {e}")

    return result


def get_network_status() -> dict:
    return {"hk_source": _hk_source}
