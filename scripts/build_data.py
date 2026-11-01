"""
每日更新：抓取 FRED / FinMind / GitHub(CNN 恐懼貪婪) / Siblis，計算指標與燈號，輸出 data.json
用法: python3 build_data.py <輸出資料夾>
規則來源：2026/10 回測（台股 1999-2026、美股 1990-2026）
"""
import sys, json, io, urllib.request, datetime as dt
import pandas as pd, numpy as np

OUT = sys.argv[1] if len(sys.argv) > 1 else "."

import time
def get(url, tries=5):
    last = None
    for i in range(tries):
        if i: time.sleep(5 * i)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; leverage-dashboard/1.0)", "Accept": "*/*"})
            with urllib.request.urlopen(req, timeout=90) as r:
                return r.read().decode("utf-8")
        except Exception as e:
            last = e
    raise last

def fred(sid, start="2014-01-01"):
    df = pd.read_csv(io.StringIO(get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}&cosd={start}")), na_values=".")
    df.columns = ["date", "v"]; df["date"] = pd.to_datetime(df["date"])
    return df.set_index("date")["v"].astype(float).dropna()

import os
FM_TOKEN = os.environ.get("FINMIND_TOKEN", "").strip()
def finmind(dataset, sid, start):
    url = f"https://api.finmindtrade.com/api/v4/data?dataset={dataset}&data_id={sid}&start_date={start}"
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
    f = safe(f"FRED {name}", lambda: fred(fred_id))
    c = safe(f"CBOE {name}", lambda: cboe(name))
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
def safe(name, fn):
    try:
        v = fn(); src_status[name] = "ok"; return v
    except Exception as e:
        src_status[name] = f"失敗: {type(e).__name__}"; return None

vix = vol("VIX", "VIXCLS")
vxn = vol("VXN", "VXNCLS")
vix3m = vol("VIX3M", "VXVCLS")
hy = safe("FRED HY OAS", lambda: fred("BAMLH0A0HYM2", "2020-01-01"))
baa = safe("FRED BAA 利差", lambda: fred("BAA10Y", "2025-01-01"))
taiex = safe("FinMind 加權指數", lambda: finmind("TaiwanStockPrice", "TAIEX", "2014-01-01"))
qqq = safe("FinMind QQQ", lambda: finmind("USStockPrice", "QQQ", "2014-01-01"))
fg = safe("CNN 恐懼貪婪 (GitHub)", lambda: pd.read_csv(io.StringIO(get("https://raw.githubusercontent.com/whit3rabbit/fear-greed-data/main/fear-greed.csv")), parse_dates=["Date"]).set_index("Date")["Fear Greed"])
fpe = safe("Siblis 前瞻本益比", lambda: json.loads(get("https://siblisresearch.supabase.co/functions/v1/free-data-api/v1/NDX/pe-forward"))["data"])

# ---------------- rules ----------------
RULES = {
    "tw": {"name": "台股", "lev": "00685L", "bul": "00713", "base": 0.60, "rsi_refill": 80,
           "mid": [("ma60", 0.0, 0.64, "跌破季線", "ma60"), ("ma120", 0.0, 0.67, "跌破半年線", "ma120"), ("ma120", -0.05, 0.70, "低於半年線 5%", "ma120_5")],
           "vix": [(28, 0.80, "VIX ≥ 28", "vix28"), (32, 0.85, "VIX ≥ 32", "vix32"), (36, 0.90, "VIX ≥ 36", "vix36"), (40, 1.00, "VIX ≥ 40", "vix40")],
           "credit_block": 0.80},
    "us": {"name": "美股", "lev": "QLD", "bul": "SGOV", "base": 0.60, "rsi_refill": 75,
           "mid": [("ma60", 0.0, 0.65, "跌破季線", "ma60"), ("ma120", 0.0, 0.70, "跌破半年線", "ma120"), ("ma120", -0.05, 0.75, "低於半年線 5%", "ma120_5")],
           "vix": [(35, 0.85, "VIX ≥ 35", "vix35"), (40, 1.00, "VIX ≥ 40", "vix40")]},
}

def market(close, key):
    R = RULES[key]
    df = pd.DataFrame({"close": close})
    for k in [20, 60, 120, 240]:
        df[f"ma{k}"] = close.rolling(k).mean()
    df["ath"] = close.cummax(); df["dd"] = close / df["ath"] - 1
    rsi = wrsi(close); df["rsi_w"] = rsi.reindex(df.index, method="ffill")
    v = vix.reindex(df.index, method="ffill") if vix is not None else pd.Series(np.nan, index=df.index)
    if key == "tw":
        v = v.shift(1)                       # 歷史：美股前一晚收盤 = 台股開盤前已知
        if vix is not None and len(v): v.iloc[-1] = float(vix.iloc[-1])   # 今天：用最新一筆 VIX
    df["vix"] = v
    last = df.iloc[-1]
    # tiers
    tiers = []
    ath_date = df.index[df["close"] == df["close"].cummax()][-1]
    ep = df.loc[ath_date:]                   # 本波（自最近一次創高以來）
    for col, off, w, label, tid in R["mid"]:
        cond = ep["close"] <= ep[col] * (1 + off)
        first = cond[cond].index.min() if cond.any() else None
        now = bool(last["close"] <= last[col] * (1 + off))
        tiers.append({"id": tid, "group": "中期回調", "label": label, "target": w, "active": now,
                      "line": round(float(last[col] * (1 + off)), 2),
                      "gap": float(last["close"] / (last[col] * (1 + off)) - 1),
                      "first_this_wave": first.strftime("%Y-%m-%d") if first is not None else None})
    for th, w, label, tid in R["vix"]:
        cond = ep["vix"] >= th; first = cond[cond].index.min() if cond.any() else None
        tiers.append({"id": tid, "group": "恐慌加碼", "label": label, "target": w, "active": bool(last["vix"] >= th),
                      "line": th, "gap": float(last["vix"] / th - 1) if pd.notna(last["vix"]) else None,
                      "first_this_wave": first.strftime("%Y-%m-%d") if first is not None else None})
    if R.get("deep") is not None:
        dl = R["deep"]; cond = ep["dd"] <= dl; first = cond[cond].index.min() if cond.any() else None
        prev = df.loc[df["dd"] <= dl]
        tiers.append({"id": "dd30", "group": "恐慌加碼", "label": "距高點 −30%", "target": 1.00, "active": bool(last["dd"] <= dl),
                      "line": round(float(last["ath"] * (1 + dl)), 2), "gap": float(last["close"] / (last["ath"] * (1 + dl)) - 1),
                      "first_this_wave": first.strftime("%Y-%m-%d") if first is not None else None,
                      "last_seen": prev.index[-1].strftime("%Y-%m-%d") if len(prev) else None})
    credit = None
    if R.get("credit_block") is not None and baa is not None and len(baa) > 64:
        cs = (baa - baa.shift(63)) > R["credit_block"]; run = 0
        for x in cs.values[::-1]:
            if not x: break
            run += 1
        chg = float(baa.iloc[-1] - baa.iloc[-64]); blk = 0 < run <= 30     # 利差 3 個月擴大超過門檻：暫停恐慌加碼，最多 30 個交易日
        credit = {"chg": round(chg, 2), "th": R["credit_block"], "block": bool(blk), "days": run, "asof": baa.index[-1].strftime("%Y-%m-%d")}
        if blk:
            for t in tiers:
                if t["group"] == "恐慌加碼":
                    t["reached"] = t["active"]; t["active"] = False
    active = [t for t in tiers if t["active"]]
    target = max([R["base"]] + [t["target"] for t in active])
    refill = bool(last["rsi_w"] > R["rsi_refill"])
    if refill and not active:
        state, target = "refill", R["base"]
    elif any(t["group"] == "恐慌加碼" for t in active):
        state = "panic"
    elif active:
        state = "dip"
    else:
        state = "normal"
    # history for charts (last ~2.5y)
    h = df.loc[df.index >= df.index[-1] - pd.Timedelta(days=900)]
    hist = {"date": [d.strftime("%Y-%m-%d") for d in h.index]}
    for c in ["close", "ma20", "ma60", "ma120", "ma240", "dd", "vix"]:
        hist[c] = [None if pd.isna(x) else round(float(x), 4 if c == "dd" else 2) for x in h[c]]
    rw = rsi.loc[rsi.index >= h.index[0]]
    hist_rsi = {"date": [d.strftime("%Y-%m-%d") for d in rw.index], "rsi": [round(float(x), 1) for x in rw]}
    # past trigger markers (first day of each tier episode) within window
    # 每一波（以創新高分段）每一級只標第一次
    wave = (df["close"] >= df["ath"]).cumsum().loc[h.index]
    def firsts(c):
        c = c.fillna(False); return [d for d in c[c].groupby(wave[c]).head(1).index]
    marks = []
    for col, off, w, label, tid in R["mid"]:
        marks += [{"date": d.strftime("%Y-%m-%d"), "label": label, "id": tid, "target": w, "kind": "dip"} for d in firsts(h["close"] <= h[col] * (1 + off))]
    if R.get("deep") is not None:
        marks += [{"date": d.strftime("%Y-%m-%d"), "label": "距高點 −30%", "id": "dd30", "target": 1.0, "kind": "panic"} for d in firsts(h["dd"] <= R["deep"])]
    for th, w, label, tid in R["vix"]:
        marks += [{"date": d.strftime("%Y-%m-%d"), "label": label, "id": tid, "target": w, "kind": "panic"} for d in firsts(h["vix"] >= th)]
    rw2 = h["rsi_w"] > R["rsi_refill"]; st = rw2 & ~rw2.shift(1, fill_value=False)
    marks += [{"date": d.strftime("%Y-%m-%d"), "label": f"週 RSI > {R['rsi_refill']}（補子彈）", "id": "refill", "target": R["base"], "kind": "refill"} for d in st[st].index]
    return {
        "name": R["name"], "lev": R["lev"], "bul": R["bul"], "base": R["base"], "rsi_refill": R["rsi_refill"],
        "asof": df.index[-1].strftime("%Y-%m-%d"),
        "vix_asof": (vix.index[-1].strftime("%Y-%m-%d") if vix is not None else None),
        "close": round(float(last["close"]), 2), "chg1d": float(close.iloc[-1] / close.iloc[-2] - 1),
        "ath": round(float(last["ath"]), 2), "ath_date": ath_date.strftime("%Y-%m-%d"), "dd": float(last["dd"]),
        "lev_dd": float(np.prod(1 + 2 * close.loc[ath_date:].pct_change().dropna().values) - 1),
        "ma": {k: round(float(last[f"ma{k}"]), 2) for k in [20, 60, 120, 240]},
        "rsi_w": round(float(last["rsi_w"]), 1), "vix": None if pd.isna(last["vix"]) else round(float(last["vix"]), 2),
        "tiers": tiers, "target": target, "state": state, "refill": refill, "credit": credit,
        "hist": hist, "hist_rsi": hist_rsi, "marks": sorted(marks, key=lambda m: m["date"]),
    }

out = {"generated": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%MZ"), "sources": src_status}
if taiex is not None:
    out["tw"] = market(taiex["close"].astype(float), "tw")
if qqq is not None:
    out["us"] = market(qqq["Close"].astype(float), "us")
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

# ---------------- 我的庫存用的收盤價（只放在完整版）----------------
PF_TICKERS = {"2330": "台積電", "00685L": "群益臺灣加權正2", "00631L": "元大台灣50正2", "00713": "元大台灣高息低波",
              "00918": "大華優利高填息30", "00830": "國泰費城半導體", "00670L": "富邦NASDAQ正2", "00865B": "國泰US短期公債",
              "00662": "富邦NASDAQ", "00924": "復華S&P500成長", "009815": "大華美國MAG7+"}
prices = {}
start_px = (dt.date.today() - dt.timedelta(days=20)).isoformat()
for tk, nm in PF_TICKERS.items():
    try:
        d = finmind("TaiwanStockPrice", tk, start_px)
        d = d[d["close"] > 0]
        if len(d): prices[tk] = {"name": nm, "close": float(d["close"].iloc[-1]), "date": d.index[-1].strftime("%Y-%m-%d")}
    except Exception as e:
        prices[tk] = {"name": nm, "close": None, "date": None}
out["prices"] = prices


# ---------------- 訊號變化（給每日排程推播用）----------------
def _sig(m):
    if not m: return {}
    return {"state": m.get("state"), "tiers": {t["id"]: t["active"] for t in m.get("tiers", [])}, "refill": m.get("refill")}
NAMES = {"normal": "平常狀態", "dip": "中期回調（薪資全買正二）", "panic": "恐慌加碼", "refill": "過熱調節"}
changes = []
prev_path = sys.argv[2] if len(sys.argv) > 2 else None
if prev_path and os.path.exists(prev_path):
    try:
        prev = json.load(open(prev_path))
        for key in ["tw", "us"]:
            if key not in out or key not in prev: continue
            a, b = _sig(prev[key]), _sig(out[key]); m = out[key]
            lev = m["lev"]; nm = m["name"]
            if a.get("state") != b.get("state"):
                msg = f"{nm}：{NAMES.get(a.get('state'), a.get('state'))} → {NAMES.get(b['state'], b['state'])}"
                if b["state"] in ("panic",): msg += f"，{lev} 加到 {round(m['target']*100)}%"
                if b["state"] == "refill": msg += f"，{lev} 調回 {round(m['base']*100)}%"
                changes.append(msg)
            pc, nc = (prev[key].get("credit") or {}).get("block"), (m.get("credit") or {}).get("block")
            if nc and not pc: changes.append(f"{nm}：信用利差 3 個月擴大超過 {m['credit']['th']}，恐慌加碼暫停")
            if pc and not nc: changes.append(f"{nm}：信用利差暫停解除，恐慌加碼恢復")
            for t in m["tiers"]:
                if t["group"] == "恐慌加碼" and t["active"] and not a.get("tiers", {}).get(t["id"], False) and a.get("state") == "panic":
                    changes.append(f"{nm}：新觸發 {t['label']}，{lev} 加到 {round(t['target']*100)}%")
    except Exception as e:
        changes.append(f"(比對失敗: {type(e).__name__})")

os.makedirs(f"{OUT}/full", exist_ok=True); os.makedirs(f"{OUT}/friends", exist_ok=True)
with open(f"{OUT}/full/data.json", "w") as f:
    json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
us_only = {k: v for k, v in out.items() if k not in ("tw", "prices")}
us_only["sources"] = {k: v for k, v in src_status.items() if k != "FinMind 加權指數"}
with open(f"{OUT}/friends/data.json", "w") as f:
    json.dump(us_only, f, ensure_ascii=False, separators=(",", ":"))
print("CHANGES: " + ("；".join(changes) if changes else "none"))
print("ok", out["generated"], {k: out[k]["state"] for k in ["tw", "us"] if k in out}, src_status)
