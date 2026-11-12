"""
每日更新：抓取 FRED / FinMind / GitHub(CNN 恐懼貪婪) / Siblis，計算指標與燈號，輸出 data.json
用法: python3 build_data.py <輸出資料夾>
規則來源：2026/10 回測（台股 1999-2026、美股 1990-2026）
"""
import sys, os, json, io, urllib.request, datetime as dt
import pandas as pd, numpy as np

OUT = sys.argv[1] if len(sys.argv) > 1 else "."

import time
def get(url, tries=5, timeout=90):
    last = None
    for i in range(tries):
        if i: time.sleep(5 * i)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; leverage-dashboard/1.0)", "Accept": "*/*"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8")
        except Exception as e:
            last = e
    raise last

def _deadline(fn, sec):
    """在背景執行，超過 sec 秒就放棄（避免對方網站拖住整個排程）"""
    import threading
    box = {}
    def run():
        try: box["v"] = fn()
        except Exception as e: box["e"] = e
    th = threading.Thread(target=run, daemon=True); th.start(); th.join(sec)
    if th.is_alive(): raise TimeoutError(f"超過 {sec} 秒")
    if "e" in box: raise box["e"]
    return box["v"]
FRED_CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
def fred(sid, start="2014-01-01"):
    """FRED 偶爾很慢：最多等 60 秒；失敗時用 data/ 裡的快取（仍標示為失敗）"""
    cp = os.path.join(FRED_CACHE, f"fred_{sid}.csv")
    try:
        txt = _deadline(lambda: get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}&cosd=2012-01-01", tries=2, timeout=25), 60)
        df = pd.read_csv(io.StringIO(txt), na_values=".")
        df.columns = ["date", "v"]; df["date"] = pd.to_datetime(df["date"])
        s_ = df.set_index("date")["v"].astype(float).dropna()
        if len(s_) > 100 and sid in ("BAA10Y", "DGS2", "BAMLH0A0HYM2"): s_.to_csv(cp, header=["v"])
        return s_.loc[start:]
    except Exception:
        if sid in ("BAA10Y", "DGS2", "BAMLH0A0HYM2") and os.path.exists(cp):
            c = pd.read_csv(cp, index_col=0, parse_dates=True)["v"].astype(float)
            fred_stale.append(f"{sid} 用快取到 {c.index[-1].date()}")
            return c.loc[start:]
        raise
fred_stale = []

import os
FM_TOKEN = os.environ.get("FINMIND_TOKEN", "").strip()
def finmind(dataset, sid, start):
    url = f"https://api.finmindtrade.com/api/v4/data?dataset={dataset}" + (f"&data_id={sid}" if sid else "") + f"&start_date={start}"
    if FM_TOKEN:
        url += f"&token={FM_TOKEN}"
    d = json.loads(get(url))["data"]
    df = pd.DataFrame(d); df["date"] = pd.to_datetime(df["date"]); return df.set_index("date")

def cboe(name):
    df = pd.read_csv(io.StringIO(get(f"https://cdn-api.cboe.com/api/global/us_indices/daily_prices/{name}_History.csv")))
    df.columns = [c.strip().upper() for c in df.columns]
    df["DATE"] = pd.to_datetime(df["DATE"])
    return df.set_index("DATE")["CLOSE"].astype(float).dropna()

def vol(name, fred_id):
    """CBOE 收盤當天更新；抓不到時用 FRED（通常晚一天）"""
    c = safe(f"CBOE {name}", lambda: cboe(name))
    if c is not None:
        return c
    f = safe(f"FRED {name}", lambda: fred(fred_id))
    if c is None:
        if f is not None:   # 只用 FRED，不算失敗，但標示可能晚一天
            src_status.pop(f"CBOE {name}", None); src_status[f"FRED {name}"] = "ok"
        return f
    src_status.pop(f"FRED {name}", None)
    return c if f is None else c.combine_first(f)

def wrsi(close, n=14):
    wk = close.resample("W-FRI").last().dropna(); d = wk.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n).mean(); dn = (-d.clip(upper=0)).ewm(alpha=1 / n).mean()
    return 100 - 100 / (1 + up / dn)

# ---------------- fetch ----------------
src_status = {}
_T0 = time.time()
def log(msg): print(f"[{time.time() - _T0:6.1f}s] {msg}", flush=True)
def safe(name, fn):
    t = time.time()
    try:
        v = fn(); src_status[name] = "ok"; log(f"{name} ok ({time.time() - t:.1f}s)"); return v
    except Exception as e:
        src_status[name] = f"失敗: {type(e).__name__}"; log(f"{name} 失敗 {type(e).__name__} ({time.time() - t:.1f}s)"); return None

vix = vol("VIX", "VIXCLS")
# 盤中：CBOE 延遲報價（約 15 分鐘），若比歷史資料新就補上今天這一筆
vix_live = None
try:
    q = json.loads(get("https://cdn-api.cboe.com/api/global/delayed_quotes/quotes/_VIX.json", tries=2))["data"]
    lt = pd.Timestamp(q["last_trade_time"]); px_ = float(q["current_price"])
    if vix is not None and px_ > 0 and lt.normalize() > vix.index[-1]:
        vix = pd.concat([vix, pd.Series([px_], index=[lt.normalize()])])
        vix_live = lt.strftime("%Y-%m-%d %H:%M")
except Exception:
    pass
vxn = vol("VXN", "VXNCLS")
vix3m = vol("VIX3M", "VXVCLS")
hy = safe("FRED HY OAS", lambda: fred("BAMLH0A0HYM2", "2020-01-01"))
baa = safe("FRED BAA 利差", lambda: fred("BAA10Y", "2012-01-01"))
if any("BAA10Y" in x for x in fred_stale) and baa is not None:
    src_status["FRED BAA 利差"] = ("失敗: " if (pd.Timestamp.today() - baa.index[-1]).days > 10 else "快取: ") + [x for x in fred_stale if "BAA10Y" in x][0]
taiex = safe("FinMind 加權指數", lambda: finmind("TaiwanStockPrice", "TAIEX", "2014-01-01"))
qqq = safe("FinMind QQQ", lambda: finmind("USStockPrice", "QQQ", "2014-01-01"))
fg = safe("CNN 恐懼貪婪 (GitHub)", lambda: pd.read_csv(io.StringIO(get("https://raw.githubusercontent.com/whit3rabbit/fear-greed-data/main/fear-greed.csv")), parse_dates=["Date"]).set_index("Date")["Fear Greed"])
fpe = safe("Siblis 前瞻本益比", lambda: json.loads(get("https://siblisresearch.supabase.co/functions/v1/free-data-api/v1/NDX/pe-forward"))["data"])

# ---------------- 融資資料（快取在 data/，每次只補最新的）----------------
import rules as RU
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
def tw_margin():
    p = os.path.join(ROOT, "data", "margin_tw.csv"); c = pd.read_csv(p)
    st = (pd.Timestamp(c["date"].iloc[-1]) - pd.Timedelta(days=10)).strftime("%Y-%m-%d")
    try:
        d = _deadline(lambda: finmind("TaiwanStockTotalMarginPurchaseShortSale", "", st), 120).reset_index()
        d = d[d["name"] == "MarginPurchaseMoney"]
        n = pd.DataFrame({"date": d["date"].dt.strftime("%Y-%m-%d"), "balance": d["TodayBalance"].astype("int64")})
        c = pd.concat([c[~c["date"].isin(n["date"])], n]).sort_values("date"); c.to_csv(p, index=False)
        src_status["FinMind 台股融資"] = "ok"
    except Exception as e:
        src_status["FinMind 台股融資"] = f"失敗: {type(e).__name__}（用快取到 {c['date'].iloc[-1]}）"
    return pd.Series(c["balance"].astype(float).values, index=pd.to_datetime(c["date"]))
def us_margin():
    p = os.path.join(ROOT, "data", "margin_us.csv"); c = pd.read_csv(p)
    # FINRA 每月一次（約次月第三週）公布；快取已有上個月的資料就不用再抓
    want = (pd.Timestamp.today() - pd.DateOffset(months=1)).strftime("%Y-%m")
    if c["ym"].iloc[-1] >= want or (pd.Timestamp.today().day < 15 and c["ym"].iloc[-1] >= (pd.Timestamp.today() - pd.DateOffset(months=2)).strftime("%Y-%m")):
        src_status["FINRA 美股融資"] = "ok"
        return pd.Series(c["debt"].astype(float).values, index=pd.to_datetime(c["ym"]))
    try:
        import re as _re
        def dl():
            UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"}
            html = urllib.request.urlopen(urllib.request.Request("https://www.finra.org/rules-guidance/key-topics/margin-accounts/margin-statistics", headers=UA), timeout=30).read().decode("utf-8", "ignore")
            link = [l for l in _re.findall(r'href="([^"]+\.xlsx)"', html) if "margin" in l.lower()][0]
            url = link if link.startswith("http") else "https://www.finra.org" + link
            return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30).read()
        x = pd.read_excel(io.BytesIO(_deadline(dl, 90)))
        x = x.iloc[:, :2]; x.columns = ["ym", "debt"]; x = x.dropna()
        x["ym"] = pd.to_datetime(x["ym"].astype(str).str[:7]).dt.strftime("%Y-%m")
        if len(x) > 300:
            c = x.sort_values("ym"); c.to_csv(p, index=False)
        src_status["FINRA 美股融資"] = "ok"
    except Exception as e:
        src_status["FINRA 美股融資"] = f"失敗: {type(e).__name__}（用快取到 {c['ym'].iloc[-1]}）"
    return pd.Series(c["debt"].astype(float).values, index=pd.to_datetime(c["ym"]))
log("start: mg_tw = tw_margin(); mg_us = u")
def vixtwn():
    """台指 VIX：快取在 data/vixtwn.csv（2001–2026/10 由台指選擇權結算價重算，之後用期交所官方每日收盤）"""
    p = os.path.join(ROOT, "data", "vixtwn.csv"); c = pd.read_csv(p)
    try:
        import re as _re
        today = pd.Timestamp.today(); got = {}
        for k in range(0, 3):
            ym = (today - pd.DateOffset(months=k)).strftime("%Y%m")
            try:
                txt = _deadline(lambda: get(f"https://www.taifex.com.tw/file/taifex/Dailydownload/vix/log2data_eng/{ym}new.txt", tries=2, timeout=30), 70)
            except Exception:
                continue
            for line in txt.splitlines():
                m = _re.match(r"(\d{8})\s+\d+\s+([\d.]+)", line)
                if m:
                    d_ = f"{m.group(1)[:4]}-{m.group(1)[4:6]}-{m.group(1)[6:]}"; got[d_] = float(m.group(2))
                    HI_NEW[d_] = max(HI_NEW.get(d_, 0), float(m.group(2)))
        # 期交所即時報價：補今天的收盤與盤中最高（排程在 13:50 收盤後跑，一天只抓一次）
        try:
            rq = urllib.request.Request("https://mis.taifex.com.tw/futures/api/getQuoteListVIX", data=b"{}",
                                        headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0 (compatible; leverage-dashboard/1.0)"})
            q = json.loads(urllib.request.urlopen(rq, timeout=20).read())["RtData"]["QuoteList"][0]
            cd = str(q.get("CDate", "")); last = float(q.get("CLastPrice") or 0); high = float(q.get("CHighPrice") or 0)
            now8 = pd.Timestamp.utcnow().tz_localize(None) + pd.Timedelta(hours=8)
            if len(cd) == 8 and last > 0:
                d_ = f"{cd[:4]}-{cd[4:6]}-{cd[6:]}"
                if d_ not in got and (d_ < now8.strftime("%Y-%m-%d") or now8.hour * 60 + now8.minute >= 13 * 60 + 45): got[d_] = last
                HI_NEW[d_] = max(HI_NEW.get(d_, 0), high, last)
        except Exception:
            pass
        if not got: raise RuntimeError("無資料")
        n = pd.DataFrame({"date": list(got), "vix": list(got.values())})
        c = pd.concat([c[~c["date"].isin(n["date"])], n]).sort_values("date"); c.to_csv(p, index=False)
        src_status["期交所台指 VIX"] = "ok"
    except Exception as e:
        src_status["期交所台指 VIX"] = f"失敗: {type(e).__name__}（用快取到 {c['date'].iloc[-1]}）"
    return pd.Series(c["vix"].astype(float).values, index=pd.to_datetime(c["date"]))
HI_NEW = {}
mg_tw = tw_margin(); mg_us = us_margin()
vx_tw = vixtwn()
def vixtwn_hi():
    """台指 VIX 每日盤中最高：2026/10 以前由台指選擇權高低價估算，之後用期交所報價的當日最高（收盤後抓一次）"""
    p = os.path.join(ROOT, "data", "vixtwn_hi.csv"); c = pd.read_csv(p)
    hi = dict(zip(c["date"], c["hi"].astype(float)))
    for d_, v in HI_NEW.items(): hi[d_] = round(max(hi.get(d_, 0), v), 2)
    c = pd.DataFrame({"date": list(hi), "hi": list(hi.values())}).sort_values("date"); c.to_csv(p, index=False)
    return pd.Series(c["hi"].values, index=pd.to_datetime(c["date"]))
vx_tw_hi = vixtwn_hi()
dgs2 = safe("FRED 2 年期殖利率", lambda: fred("DGS2", "2012-01-01"))
if any("DGS2" in x for x in fred_stale) and dgs2 is not None:
    src_status["FRED 2 年期殖利率"] = ("失敗: " if (pd.Timestamp.today() - dgs2.index[-1]).days > 10 else "快取: ") + [x for x in fred_stale if "DGS2" in x][0]
taiex_tr = safe("FinMind 加權報酬指數", lambda: finmind("TaiwanStockTotalReturnIndex", "TAIEX", "2012-01-01"))
qqq_long = safe("FinMind QQQ 長期", lambda: finmind("USStockPrice", "QQQ", "2012-01-01"))

# ---------------- rules ----------------
RULES = {
    "tw": {"name": "台股", "lev": "00685L", "one": "0050", "bul": "00713", "base": 0.60, "rsi_refill": 80},
    "us": {"name": "美股", "lev": "QLD", "one": "QQQM", "bul": "SGOV", "base": 0.60, "rsi_refill": 75},
}
EVN = {"panic1": "VIX ≥ 35：二倍槓桿加到 85%", "panic2": "VIX ≥ 40：二倍槓桿加到 100%", "twvix": "台股急跌（台指 VIX 收盤 ≥ 40 或盤中 ≥ 45）：二倍槓桿加到 100%", "deep": "深跌補滿：二倍槓桿加到 100%",
       "rsi": "RSI 過熱：二倍槓桿調回 60%", "mg": "融資過熱：二倍槓桿換成一倍原型", "re": "融資退燒：一倍原型換回二倍槓桿"}

BT_PATH = {}
def market(close, key, rclose):
    R = RULES[key]
    df = pd.DataFrame({"close": close})
    for k in [20, 60, 120, 240]:
        df[f"ma{k}"] = close.rolling(k).mean()
    df["ath"] = close.cummax(); df["dd"] = close / df["ath"] - 1
    rsi = wrsi(close); df["rsi_w"] = rsi.reindex(df.index, method="ffill")
    v = vix.reindex(df.index, method="ffill") if vix is not None else pd.Series(np.nan, index=df.index)
    if key == "tw":
        v = v.shift(1)
        if vix is not None and len(v): v.iloc[-1] = float(vix.iloc[-1])
    df["vix"] = v
    last = df.iloc[-1]
    ath_date = df.index[df["close"] == df["close"].cummax()][-1]
    rule = RU.run(key, rclose, vix, baa, dgs2, tw_margin=mg_tw, us_debt=mg_us, start="2012-06-01",
                  vix_today=float(vix.iloc[-1]) if (key == "tw" and vix is not None) else None,
                  vixtwn=vx_tw if key == "tw" else None, vixtwn_hi=vx_tw_hi if key == "tw" else None)
    m = rule["model"]; p = rule["panic"]
    if p["target"] > 0: state = "panic"
    elif rule["margin"]["reentry_ready"] and m["w1"] > 0.01: state = "reentry"
    elif rule["rsi_hot"]: state = "refill"
    elif rule["margin"]["on"]: state = "convert" if rule["conv_ok"] else "mgpause"
    elif m["w1"] > 0.01: state = "wait1x"
    else: state = "normal"
    BT_PATH[key] = (rule.pop("_path"), close, [e for e in rule["events"]])
    rule["state"] = state
    h = df.loc[df.index >= df.index[-1] - pd.Timedelta(days=900)]
    hist = {"date": [d.strftime("%Y-%m-%d") for d in h.index]}
    for c in ["close", "ma20", "ma60", "ma120", "ma240", "dd", "vix"]:
        hist[c] = [None if pd.isna(x) else round(float(x), 4 if c == "dd" else 2) for x in h[c]]
    if key == "tw" and vx_tw is not None:
        tv = vx_tw.reindex(h.index)          # 台指 VIX：台股交易日當天收盤
        hist["twvix"] = [None if pd.isna(x) else round(float(x), 2) for x in tv]
        rr20 = close / close.shift(20) - 1
        hist["r20"] = [None if pd.isna(x) else round(float(x), 4) for x in rr20.reindex(h.index)]
    rw = rsi.loc[rsi.index >= h.index[0]]
    hist_rsi = {"date": [d.strftime("%Y-%m-%d") for d in rw.index], "rsi": [round(float(x), 1) for x in rw]}
    marks = [{"date": d, "kind": k, "label": EVN[k]} for d, k in rule["events"] if d >= hist["date"][0]]
    return {
        "name": R["name"], "lev": R["lev"], "one": R["one"], "bul": R["bul"], "base": R["base"], "rsi_refill": R["rsi_refill"],
        "asof": df.index[-1].strftime("%Y-%m-%d"),
        "vix_asof": (vix.index[-1].strftime("%Y-%m-%d") if vix is not None else None),
        "close": round(float(last["close"]), 2), "chg1d": float(close.iloc[-1] / close.iloc[-2] - 1),
        "ath": round(float(last["ath"]), 2), "ath_date": ath_date.strftime("%Y-%m-%d"), "dd": float(last["dd"]),
        "lev_dd": float(np.prod(1 + 2 * close.loc[ath_date:].pct_change().dropna().values) - 1),
        "ma": {k: round(float(last[f"ma{k}"]), 2) for k in [20, 60, 120, 240]},
        "rsi_w": rule["rsi"], "vix": None if pd.isna(last["vix"]) else round(float(last["vix"]), 2),
        "state": state, "target": p["target"], "rule": rule,
        "hist": hist, "hist_rsi": hist_rsi, "marks": marks,
    }

out = {"generated": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%MZ"), "sources": src_status}
log("start: if taiex is not None and taiex")
if taiex is not None and taiex_tr is not None:
    out["tw"] = market(taiex["close"].astype(float), "tw", taiex_tr["price"].astype(float))
if qqq is not None:
    ql = qqq_long["Close"].astype(float) if qqq_long is not None else qqq["Close"].astype(float)
    out["us"] = market(qqq["Close"].astype(float), "us", ql)
    out["us"]["index_name"] = "QQQ"
if "tw" in out: out["tw"]["index_name"] = "加權指數"

def tail(s, n=600):
    s = s.dropna().iloc[-n:]
    return {"date": [d.strftime("%Y-%m-%d") for d in s.index], "v": [round(float(x), 2) for x in s]}
macro = {}
if vix is not None:
    macro["vix"] = {"last": round(float(vix.iloc[-1]), 2), "asof": vix.index[-1].strftime("%Y-%m-%d"), "series": tail(vix)}
    hi = vix[vix >= 35]
    macro["vix"]["last35"] = hi.index[-1].strftime("%Y-%m-%d") if len(hi) else None
    ep = {}
    for th in (28, 32, 35, 36, 40):
        idx = np.where((vix >= th).values)[0]; start = None; last = -10**9
        for i in idx:
            if i - last > 21: start = i
            last = i
        ep[str(th)] = vix.index[start].strftime("%Y-%m-%d") if start is not None else None
    macro["vix"]["last_ep"] = ep
    macro["vix"]["live"] = vix_live
if baa is not None and len(baa) > 64:
    macro["baa"] = {"last": round(float(baa.iloc[-1]), 2), "chg63": round(float(baa.iloc[-1] - baa.iloc[-64]), 2), "asof": baa.index[-1].strftime("%Y-%m-%d")}
if vxn is not None:
    macro["vxn"] = {"last": round(float(vxn.iloc[-1]), 2), "asof": vxn.index[-1].strftime("%Y-%m-%d"), "series": tail(vxn)}
if vix is not None and vix3m is not None:
    ts = (vix / vix3m).dropna(); macro["term"] = {"last": round(float(ts.iloc[-1]), 3), "asof": ts.index[-1].strftime("%Y-%m-%d")}
if hy is not None:
    macro["hy"] = {"last": round(float(hy.iloc[-1]), 2), "asof": hy.index[-1].strftime("%Y-%m-%d"), "chg63": round(float(hy.iloc[-1] - hy.iloc[-64]), 2) if len(hy) > 64 else None}
if fg is not None:
    macro["fg"] = {"last": round(float(fg.iloc[-1]), 1), "asof": fg.index[-1].strftime("%Y-%m-%d"), "series": tail(fg)}
if fpe:
    macro["fpe"] = {"last": fpe[-1]["value"], "asof": fpe[-1]["trading_day (EOD)"], "series": fpe}
out["macro"] = macro

log("start: # ---------------- 我的庫存用的收盤價")
# ---------------- 我的庫存用的收盤價（只放在完整版）----------------
PF_TICKERS = {"2330": "台積電", "00685L": "群益臺灣加權正2", "00631L": "元大台灣50正2", "00713": "元大台灣高息低波",
              "00918": "大華優利高填息30", "00830": "國泰費城半導體", "00670L": "富邦NASDAQ正2", "00865B": "國泰US短期公債",
              "00662": "富邦NASDAQ", "00924": "復華S&P500成長", "009815": "大華美國MAG7+"}
prices = {}
def _num(x):
    try: return float(str(x).replace(",", ""))
    except Exception: return None
# 上市（證交所）全部個股與 ETF 的收盤價
try:
    for r in json.loads(get("https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL", tries=3)):
        c = _num(r.get("ClosingPrice"))
        if c: prices[r["Code"].strip()] = {"name": r.get("Name", "").strip(), "close": c, "date": None}
    src_status["證交所收盤價"] = "ok"
except Exception as e:
    src_status["證交所收盤價"] = f"失敗: {type(e).__name__}"
# 上櫃（櫃買中心）
try:
    for r in json.loads(get("https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes", tries=3)):
        code = (r.get("SecuritiesCompanyCode") or "").strip(); c = _num(r.get("Close"))
        if code and c: prices[code] = {"name": (r.get("CompanyName") or "").strip(), "close": c, "date": None}
    src_status["櫃買中心收盤價"] = "ok"
except Exception as e:
    src_status["櫃買中心收盤價"] = f"失敗: {type(e).__name__}"
# 常用標的再用 FinMind 補日期（或在上面兩個來源失敗時補價格）
start_px = (dt.date.today() - dt.timedelta(days=20)).isoformat()
px_date = None
for tk, nm in PF_TICKERS.items():
    try:
        d = finmind("TaiwanStockPrice", tk, start_px); d = d[d["close"] > 0]
        if len(d):
            px_date = max(px_date or "", d.index[-1].strftime("%Y-%m-%d"))
            if tk not in prices: prices[tk] = {"name": nm, "close": float(d["close"].iloc[-1]), "date": None}
            elif not prices[tk]["name"]: prices[tk]["name"] = nm
    except Exception:
        pass
prices_doc = {"date": px_date, "p": {k: [v["name"], v["close"]] for k, v in prices.items()}}
log("start: # 朋友版：規則用到的歐洲 ETF")
# 朋友版：規則用到的歐洲 ETF（Yahoo Finance），統一換算成歐元
EU_UNIVERSE = "LQQ.PA IB01.L XEON.DE EQQQ.DE SXRV.DE CNDX.L CSPX.L VUAA.DE ZPR1.DE ERNE.L VWCE.DE IWDA.AS"  # 其餘歐股由 build_eu.py 另外產生 eu.json
# 舊代號（沒有交易所代碼）對應
EU_ALIAS = {"LQQ": "LQQ.PA", "IB01": "IB01.L", "XEON": "XEON.DE", "EQQQ": "EQQQ.DE", "SXRV": "SXRV.DE", "CNDX": "CNDX.L",
            "CSPX": "CSPX.L", "VUAA": "VUAA.DE", "ZPR1": "ZPR1.DE", "ERNE": "ERNE.L", "VWCE": "VWCE.DE", "IWDA": "IWDA.AS"}
def yahoo_close(sym, tries=3):
    j = json.loads(get(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=5d&interval=1d", tries=tries))
    r = j["chart"]["result"][0]; cur = r["meta"].get("currency")
    closes = [c for c in r["indicators"]["quote"][0]["close"] if c]
    px_ = closes[-1] if closes else r["meta"].get("regularMarketPrice")
    if cur in ("GBp", "GBX"): px_, cur = px_ / 100, "GBP"
    return float(px_), cur
eprices = {}
fx = {"EUR": 1.0}
try:
    for c_ in ["USD", "GBP", "CHF", "SEK", "DKK", "NOK"]:
        try: fx[c_] = 1 / yahoo_close(f"EUR{c_}=X")[0]
        except Exception: pass
    from concurrent.futures import ThreadPoolExecutor
    syms = list(dict.fromkeys(EU_UNIVERSE.split()))
    def one(sym):
        try: return sym, yahoo_close(sym, tries=2)
        except Exception: return sym, None
    with ThreadPoolExecutor(6) as ex:
        got = dict(ex.map(one, syms))
    bad = [s for s in syms if not got[s] or got[s][1] not in fx]
    print(f"Yahoo 歐洲：{len(syms) - len(bad)}/{len(syms)} 檔，抓不到：{' '.join(bad)}")
    for sym in syms:
        if sym in bad: continue
        v, cur = got[sym]; eprices[sym] = [sym, round(v * fx[cur], 4), round(v, 4), cur]
    # 沒打交易所代碼也能找到：只有一個上市地，或幾個上市地價格差不到 5%（同一檔）才對應
    groups = {}
    for sym in eprices: groups.setdefault(sym.rsplit(".", 1)[0], []).append(sym)
    for b, ls in groups.items():
        ps = [eprices[s][1] for s in ls]
        if b not in eprices and max(ps) <= min(ps) * 1.05: eprices[b] = eprices[ls[0]]
    for b, sym in EU_ALIAS.items():
        if sym in eprices: eprices[b] = eprices[sym]
    src_status["Yahoo 歐洲 ETF"] = "ok" if eprices else "失敗: 無資料"
except Exception as e:
    src_status["Yahoo 歐洲 ETF"] = f"失敗: {type(e).__name__}"
# 朋友版：美國上市常見標的的收盤價
uprices = {}
for tk in ["QLD", "SGOV", "QQQ", "TQQQ", "VOO", "SPY", "BIL", "SHV", "SCHD", "QQQM"]:
    try:
        d = finmind("USStockPrice", tk, start_px)
        if len(d): uprices[tk] = [tk, float(d["Close"].iloc[-1])]
    except Exception:
        pass

log("start: # 美股常見標的（給朋友版「我的庫存」用）")
# 美股常見標的（給朋友版「我的庫存」用）
US_TICKERS = ["QLD", "SGOV", "QQQ", "TQQQ", "QQQM", "SPY", "VOO", "VTI", "SSO", "UPRO", "BIL", "SHV", "USFR", "IEF", "TLT",
              "SCHD", "SOXX", "SMH", "SOXL", "NVDA", "AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA", "TSM"]
us_px = {}
start_us = (dt.date.today() - dt.timedelta(days=12)).isoformat()
for tk in US_TICKERS:
    try:
        d = finmind("USStockPrice", tk, start_us)
        if len(d): us_px[tk] = float(d["Close"].iloc[-1])
    except Exception:
        pass
out["us_prices"] = us_px


log("start: # ---------------- 訊號變化")
# ---------------- 訊號變化（給每日排程推播用）----------------
# ---------------- 回測圖延伸到最近一個交易日 ----------------
def extend_bt():
    EVL = {"panic1": "VIX ≥ 35", "panic2": "VIX ≥ 40", "twvix": "台指 VIX ≥ 40", "deep": "深跌補滿", "rsi": "週 RSI 過熱",
           "mg": "融資過熱", "re": "融資退燒滿 15 個月"}
    bt_path = os.path.join(ROOT, "docs", "bt.json")
    try: B = json.load(open(bt_path))
    except Exception as e: print("bt.json 讀取失敗", e); return
    for key in ["tw", "us"]:
        if key not in BT_PATH or key not in B: continue
        path, close, evs = BT_PATH[key]; S = B[key]["s"]; last = S[-1][0]
        pmap = {d: (v, l) for d, v, l in path}
        if last not in pmap: print("bt 延伸：找不到銜接日", key, last); continue
        v0 = pmap[last][0]; base = S[-1][2]
        lvl = close.copy()
        if key == "us":   # 美股回測畫那斯達克 100 點位：用 QQQ 換算
            q0 = float(close.asof(pd.Timestamp(last))); lvl = close * (S[-1][1] / q0)
        prev_l = S[-1][3]; n = 0
        for d, v, l in path:
            if d <= last: continue
            px = float(lvl.asof(pd.Timestamp(d)))
            S.append([d, round(px, 2), round(base * v / v0, 4), round(l, 2)]); n += 1
        lv = {d: l for d, v, l in path}; dates = [d for d, _, _ in path]
        for d, k in evs:
            if d <= last or d not in lv: continue
            i = dates.index(d); lb = lv[dates[i - 1]] if i else lv[d]
            B[key]["ev"].append([d, k, round(float(lvl.asof(pd.Timestamp(d))), 2), round(lb, 2), round(lv[d], 2), EVL.get(k, k), 0])
        B[key]["asof"] = S[-1][0]
        print("bt 延伸", key, n, "天，到", S[-1][0])
    json.dump(B, open(bt_path, "w"), ensure_ascii=False, separators=(",", ":"))
    json.dump({"us": B["us"]}, open(os.path.join(ROOT, "docs", "us", "bt.json"), "w"), ensure_ascii=False, separators=(",", ":"))
try: extend_bt()
except Exception as e: print("bt 延伸失敗", type(e).__name__, e)

NAMES = {"normal": "平常狀態", "panic": "恐慌加碼", "refill": "RSI 過熱調節", "convert": "融資過熱（二倍槓桿換成一倍原型）",
         "mgpause": "融資過熱（恐慌加碼後冷卻中，先不換）", "wait1x": "融資退燒中（一倍原型先不換回）", "reentry": "一倍原型換回二倍槓桿"}
changes = []
prev_path = sys.argv[2] if len(sys.argv) > 2 else None
if prev_path and os.path.exists(prev_path):
    try:
        prev = json.load(open(prev_path))
        for key in ["tw", "us"]:
            if key not in out or key not in prev: continue
            m = out[key]; a_, b_ = prev[key].get("state"), m["state"]; nm = m["name"]
            ta, tb = prev[key].get("target") or 0, m["target"] or 0
            if a_ != b_ or (b_ == "panic" and tb > ta):
                msg = f"{nm}：{NAMES.get(a_, a_)} → {NAMES.get(b_, b_)}"
                if b_ == "panic": msg += f"，二倍槓桿加到 {round(tb*100)}%（先用一倍原型，再用子彈）"
                if b_ == "refill": msg += f"，二倍槓桿調回 {round(m['base']*100)}%"
                changes.append(msg)
    except Exception as e:
        changes.append(f"(比對失敗: {type(e).__name__})")

os.makedirs(f"{OUT}/full", exist_ok=True); os.makedirs(f"{OUT}/friends", exist_ok=True)
with open(f"{OUT}/full/prices.json", "w") as f:
    json.dump(prices_doc, f, ensure_ascii=False, separators=(",", ":"))
with open(f"{OUT}/full/data.json", "w") as f:
    json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
us_only = {k: v for k, v in out.items() if k not in ("tw", "prices")}
us_only["uprices"] = uprices
us_only["eprices"] = eprices
try:
    us_only["fx"] = {"EUR" + k: round(1 / v, 5) for k, v in fx.items() if k != "EUR"}
except Exception:
    pass
us_only["sources"] = {k: v for k, v in src_status.items() if k not in ("FinMind 加權指數", "FinMind 加權報酬指數", "FinMind 台股融資", "期交所台指 VIX", "證交所收盤價", "櫃買中心收盤價")}
with open(f"{OUT}/friends/data.json", "w") as f:
    json.dump(us_only, f, ensure_ascii=False, separators=(",", ":"))
print("CHANGES: " + ("；".join(changes) if changes else "none"))
print("ok", out["generated"], {k: out[k]["state"] for k in ["tw", "us"] if k in out}, src_status)
