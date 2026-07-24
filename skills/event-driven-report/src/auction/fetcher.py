"""行情数据获取（支持 akshare / tushare 双后端）。

tushare: 走第三方代理(stockai888)或官方, token 走环境变量 TUSHARE_TOKEN 不落盘。
akshare: 免费(东财), 易限流, 作为回退。
用日K的"开盘价"作为集合竞价(9:25)结果。铁律：只取客观数据，不预测股价。
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

# akshare 东财为国内站点, 不走系统代理(避免限流); 对 tushare 直连也无害
os.environ.setdefault("NO_PROXY", "*")

import pandas as pd

# ---- 后端选择（从 settings 读取，初始化 tushare）----
_BACKEND = "akshare"
_TS_PRO = None
_TS_SERVER = ""


def _load_backend():
    global _BACKEND, _TS_PRO, _TS_SERVER
    try:
        import yaml
        p = Path(__file__).resolve().parents[2] / "config" / "settings.yaml"
        s = yaml.safe_load(open(p, encoding="utf-8")) or {}
        d = s.get("data") or {}
        _BACKEND = d.get("backend", "akshare")
        tsc = d.get("tushare") or {}
        token = str(tsc.get("token", ""))
        token = re.sub(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}",
                       lambda m: os.environ.get(m.group(1), ""), token)
        if not token:
            token = os.environ.get("TUSHARE_TOKEN", "")
        _TS_SERVER = str(tsc.get("api_server", "") or "")
        if _BACKEND == "tushare" and token:
            import tushare as ts
            ts.set_token(token)
            _TS_PRO = ts.pro_api()
            if _TS_SERVER:
                try:
                    _TS_PRO._DataApi__http_url = _TS_SERVER
                except Exception:
                    pass
    except Exception:
        _BACKEND = "akshare"


_load_backend()
import akshare as ak  # noqa: 回退后端


def _to_ts_code(code: str) -> str:
    """6位代码 → tushare ts_code。60/68/90→SH, 其余→SZ。"""
    c = str(code)
    if c.startswith(("60", "68", "90")):
        return c + ".SH"
    return c + ".SZ"


def _fetch_tushare(code: str, start: str, end: str) -> pd.DataFrame:
    """tushare daily，字段映射成中文（兼容 analyzer/macd/engine）。注意：不复权。"""
    df = _TS_PRO.daily(ts_code=_to_ts_code(code), start_date=start, end_date=end)
    df = df.rename(columns={
        "trade_date": "日期", "open": "开盘", "close": "收盘",
        "high": "最高", "low": "最低", "vol": "成交量", "amount": "成交额",
    })
    df["日期"] = df["日期"].astype(str)
    df = df.sort_values("日期").reset_index(drop=True)
    return df


def fetch_daily(code: str, start: str, end: str) -> pd.DataFrame:
    """拉日K。优先 tushare（配置时），失败回退 akshare。"""
    if _BACKEND == "tushare" and _TS_PRO is not None:
        try:
            return _fetch_tushare(code, start, end)
        except Exception:
            pass  # 回退 akshare
    return ak.stock_zh_a_hist(symbol=code, period="daily", start_date=start, end_date=end, adjust="qfq")


def fetch_recent(code: str, days: int = 40) -> pd.DataFrame:
    """拉最近约 days 个交易日的日K。"""
    end = datetime.now().strftime("%Y%m%d")
    start = (datetime.now() - timedelta(days=days * 2 + 15)).strftime("%Y%m%d")
    return fetch_daily(code, start, end)


_BS_LOGGED = False


def _bs_login() -> None:
    global _BS_LOGGED
    if not _BS_LOGGED:
        import baostock as bs
        bs.login()
        _BS_LOGGED = True


def _to_bs_code(code: str) -> str:
    return ("sh." if str(code).startswith(("60", "68", "90")) else "sz.") + str(code)


def fetch_minute_series_bs(code: str, start_date: str, end_date: str, freq: str = "5") -> pd.DataFrame:
    """baostock 长历史5min（1999起，免费无token，T+1更新）。adjustflag=2 前复权。

    start/end: 'YYYY-MM-DD'。返回 trade_time/open/high/low/close/vol/amount。
    """
    _bs_login()
    import baostock as bs
    rs = bs.query_history_k_data_plus(
        _to_bs_code(code),
        "date,time,open,high,low,close,volume,amount",
        start_date=start_date, end_date=end_date, frequency=str(freq), adjustflag="2")
    if rs.error_code != '0':
        return None
    rows = []
    while rs.next():
        rows.append(rs.get_row_data())
    if not rows:
        return None
    df = pd.DataFrame(rows, columns=["date", "time", "open", "high", "low", "close", "volume", "amount"])
    for c in ["open", "high", "low", "close", "volume", "amount"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["trade_time"] = pd.to_datetime(df["time"].astype(str).str[:14], format="%Y%m%d%H%M%S")
    df = df.rename(columns={"volume": "vol"})
    return df[["trade_time", "open", "high", "low", "close", "vol", "amount"]] \
        .sort_values("trade_time").reset_index(drop=True)


def fetch_minute_series_ts(code: str, start_date: str, end_date: str, freq: str = "5") -> pd.DataFrame:
    """tushare stk_mins 多日分钟(需 _TS_PRO 初始化=token+server；单次8000行)。

    freq: "5"->"5min"。支持 1/5/15/30/60min（中转 stockai888 + 15000积分 token，分钟权限已开）。
    返回 trade_time/open/high/low/close/vol/amount。中转第三方，准确性/稳定性自担。
    """
    if _TS_PRO is None:
        return None
    ts_code = _to_ts_code(code)
    freq_ts = str(freq).replace("min", "") + "min"
    start = f"{start_date} 09:00:00"
    end = f"{end_date} 15:00:00"
    try:
        df = _TS_PRO.stk_mins(ts_code=ts_code, freq=freq_ts, start_date=start, end_date=end)
        if df is None or len(df) == 0:
            return None
        for c in ["open", "high", "low", "close", "vol", "amount"]:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        df["trade_time"] = pd.to_datetime(df["trade_time"])
        return df[["trade_time", "open", "high", "low", "close", "vol", "amount"]] \
            .sort_values("trade_time").reset_index(drop=True)
    except Exception:
        return None


def fetch_minute_series(code: str, freq: str = "5", adjust: str = "qfq",
                        start_date: str = None, end_date: str = None) -> pd.DataFrame:
    """拉连续多日分钟K。有 start/end 时优先级：tushare stk_mins → baostock → 新浪。

    分时MACD不能按天切断重算(EMA跨日连续)，必须用全程连续序列。
    """
    if start_date and end_date:
        df = fetch_minute_series_ts(code, start_date, end_date, freq)  # 1/5min，复权完整
        if df is not None and len(df) > 0:
            return df
        try:
            df = fetch_minute_series_bs(code, start_date, end_date, freq)  # 5min，免费兜底
            if df is not None and len(df) > 0:
                return df
        except Exception:
            pass
    try:
        sym = ("sh" if str(code).startswith(("60", "68", "90")) else "sz") + str(code)
        period = str(freq).replace("min", "") or "5"
        raw = ak.stock_zh_a_minute(symbol=sym, period=period, adjust=adjust)
        if raw is None or len(raw) == 0:
            return None
        raw = raw.rename(columns={"day": "trade_time", "volume": "vol"})
        for c in ["open", "high", "low", "close", "vol", "amount"]:
            raw[c] = pd.to_numeric(raw[c], errors="coerce")
        raw["trade_time"] = pd.to_datetime(raw["trade_time"])
        return raw[["trade_time", "open", "high", "low", "close", "vol", "amount"]] \
            .sort_values("trade_time").reset_index(drop=True)
    except Exception:
        return None


def _cache_minute(cache_file: Path, df: pd.DataFrame) -> None:
    try:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(df.to_json(orient="records", force_ascii=False), encoding="utf-8")
    except Exception:
        pass


def fetch_minute(code: str, date_str: str, freq: str = "5") -> pd.DataFrame:
    """拉指定日期的分钟K线（统一字段 trade_time/open/high/low/close/vol/amount）。

    优先读本地缓存(data/minute_cache/)；无缓存按后端拉取：
    - tushare: stk_mins（需高权限，当前环境不可用）
    - akshare 新浪源: stock_zh_a_minute（免费，仅最近约2个月历史，作为回退主力）
    freq: "1"/"5"/"15"/"30"/"60"。默认 5min（分时MACD主力周期）。
    """
    cache_file = Path("data/minute_cache") / f"{code}_{date_str}_{freq}.json"
    if cache_file.exists():
        import json
        records = json.loads(cache_file.read_text(encoding="utf-8"))
        if not records:
            return None
        return pd.DataFrame(records)

    # ① tushare stk_mins（需高权限）
    if _BACKEND == "tushare" and _TS_PRO is not None:
        ts_code = _to_ts_code(code)
        start = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]} 09:00:00"
        end = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]} 15:00:00"
        try:
            df = _TS_PRO.stk_mins(ts_code=ts_code, freq=freq + "min", start_date=start, end_date=end)
            if df is not None and len(df) > 0:
                df = df.sort_values("trade_time").reset_index(drop=True)
                _cache_minute(cache_file, df)
                return df
        except Exception:
            pass

    # ② akshare 新浪源回退（免费，最近约2个月历史）
    try:
        sym = ("sh" if str(code).startswith(("60", "68", "90")) else "sz") + str(code)
        period = str(freq).replace("min", "") or "5"
        raw = ak.stock_zh_a_minute(symbol=sym, period=period, adjust="qfq")
        if raw is None or len(raw) == 0:
            return None
        raw["day"] = raw["day"].astype(str)
        prefix = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
        day_df = raw[raw["day"].str.startswith(prefix)].copy()
        if len(day_df) == 0:
            return None
        day_df = day_df.rename(columns={"day": "trade_time", "volume": "vol"})
        for c in ["open", "high", "low", "close", "vol", "amount"]:
            day_df[c] = pd.to_numeric(day_df[c], errors="coerce")
        day_df = day_df[["trade_time", "open", "high", "low", "close", "vol", "amount"]].reset_index(drop=True)
        _cache_minute(cache_file, day_df)
        return day_df
    except Exception:
        return None


def fetch_index(code: str = "000300", days: int = 400) -> pd.DataFrame:
    """拉指数日K（如沪深300=000300），用于市场风控。"""
    end = datetime.now().strftime("%Y%m%d")
    start = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")
    if _BACKEND == "tushare" and _TS_PRO is not None:
        try:
            ts_code = (code + ".SH") if code.startswith("000") else (code + ".SZ")
            df = _TS_PRO.index_daily(ts_code=ts_code, start_date=start, end_date=end)
            df = df.rename(columns={
                "trade_date": "日期", "open": "开盘", "close": "收盘",
                "high": "最高", "low": "最低", "vol": "成交量",
            })
            df["日期"] = df["日期"].astype(str)
            return df.sort_values("日期").reset_index(drop=True)
        except Exception:
            pass
    sym = ("sh" + code) if code.startswith(("000", "399")) else ("sz" + code)
    return ak.stock_zh_index_daily(symbol=sym)


def latest_trade_date(df: pd.DataFrame) -> Optional[str]:
    if df is None or len(df) == 0:
        return None
    return str(df.iloc[-1]["日期"])
