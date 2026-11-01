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
# 朋友版：歐洲上市標的（Yahoo Finance），統一換算成歐元。主要指數成分股＋常見 UCITS ETF
EU_UNIVERSE = """
LQQ.PA IB01.L XEON.DE EQQQ.DE SXRV.DE CNDX.L CSPX.L VUAA.DE ZPR1.DE ERNE.L
VWCE.DE VWRL.AS VWRL.L VWRA.L VWRP.L IWDA.AS IWDA.L SWDA.L EUNL.DE SXR8.DE VUSA.AS VUSA.L VUSD.L VUAA.L IUSQ.DE ISAC.L SSAC.L
EIMI.L IS3N.DE EMIM.AS VFEM.AS XDWD.DE EXSA.DE EXS1.DE EQQQ.L QDVE.DE IUIT.L XDWT.DE SXRT.DE MEUD.PA CW8.PA EWLD.PA PANX.PA
PUST.PA ESE.PA PE500.PA CL2.PA WSML.L ZPRV.DE ZPRX.DE VHYL.AS VHYL.L TDIV.AS ISPA.DE 4GLD.DE SGLD.L EGLN.L IGLN.L CSH2.L
IBTA.L IDTL.L DTLA.L AGGH.L EUNA.DE XDEM.DE IWVL.L IWMO.L IWQU.L SPPW.DE SPYI.DE IMAE.AS CSNDX.SW CSSPX.SW VEUR.AS VEVE.AS
IUSA.DE QQQ3.L QQQS.L DBPG.DE VVSM.DE SMH.L SPYW.DE IQQH.DE IUSN.DE ZPRS.DE VGWL.DE VGWD.DE EXW1.DE SXRZ.DE EXX5.DE
ADS.DE AIR.DE ALV.DE BAS.DE BAYN.DE BEI.DE BMW.DE BNR.DE CBK.DE CON.DE 1COV.DE DTG.DE DBK.DE DB1.DE DHL.DE DTE.DE EOAN.DE
FRE.DE G1A.DE HEI.DE HEN3.DE HNR1.DE IFX.DE MBG.DE MRK.DE MTX.DE MUV2.DE P911.DE PAH3.DE QIA.DE RHM.DE RWE.DE SAP.DE SRT3.DE
SIE.DE SHL.DE SY1.DE VNA.DE VOW3.DE ZAL.DE ENR.DE LHA.DE TUI1.DE PUM.DE BOSS.DE KGX.DE LEG.DE FRA.DE EVK.DE HLAG.DE TLX.DE
AIXA.DE NEM.DE SDF.DE WCH.DE FME.DE TKA.DE HFG.DE JEN.DE AFX.DE NDA.DE KBX.DE EVT.DE G24.DE HOT.DE SAX.DE BC8.DE TMV.DE
NDX1.DE RENK.DE 8TRA.DE DHER.DE AT1.DE LXS.DE KRN.DE FNTN.DE SZG.DE HAG.DE TEG.DE O2D.DE IOS.DE R3NK.DE
AI.PA AIR.PA ALO.PA MT.AS CS.PA BNP.PA EN.PA CAP.PA CA.PA ACA.PA BN.PA DSY.PA EDEN.PA ENGI.PA EL.PA ERF.PA RMS.PA KER.PA
OR.PA LR.PA MC.PA ML.PA ORA.PA RI.PA PUB.PA RNO.PA SAF.PA SGO.PA SAN.PA SU.PA GLE.PA STLAP.PA STMPA.PA TEP.PA HO.PA TTE.PA
URW.PA VIE.PA DG.PA AC.PA AM.PA BOL.PA BVI.PA COV.PA DIM.PA ELIS.PA FGR.PA GET.PA RXL.PA SOP.PA SW.PA TFI.PA UBI.PA VK.PA
VIV.PA AF.PA ATO.PA FDJ.PA NEX.PA RCO.PA SESG.PA SK.PA SPIE.PA TE.PA AMUN.PA AYV.PA EXENS.PA
ABN.AS ADYEN.AS AGN.AS AD.AS AKZA.AS ASM.AS ASML.AS ASRNL.AS BESI.AS DSFIR.AS EXO.AS HEIA.AS IMCD.AS INGA.AS KPN.AS NN.AS
PHIA.AS PRX.AS RAND.AS REN.AS SHELL.AS UMG.AS UNA.AS WKL.AS AALB.AS ARCAD.AS BAMNB.AS FUR.AS SBMO.AS VPK.AS JDEP.AS INPST.AS
BFIT.AS CTPNV.AS FLOW.AS
ABI.BR ACKB.BR AGS.BR ARGX.BR COFB.BR ELI.BR GBLB.BR KBC.BR LOTB.BR MELE.BR PROX.BR SOF.BR SOLB.BR SYENS.BR UCB.BR UMI.BR
WDP.BR AED.BR DIE.BR VGP.BR
A2A.MI AMP.MI AZM.MI BAMI.MI BGN.MI BMED.MI BMPS.MI BPE.MI BZU.MI CPR.MI DIA.MI ENEL.MI ENI.MI ERG.MI RACE.MI FBK.MI G.MI
HER.MI IG.MI INW.MI ISP.MI IVG.MI LDO.MI MB.MI MONC.MI NEXI.MI PIRC.MI PST.MI PRY.MI REC.MI SPM.MI SRG.MI STLAM.MI STMMI.MI
TEN.MI TIT.MI TRN.MI UCG.MI UNI.MI IP.MI
ACS.MC ACX.MC AENA.MC ANA.MC ANE.MC BBVA.MC BKT.MC CABK.MC CLNX.MC COL.MC ELE.MC ENG.MC FDR.MC FER.MC GRF.MC IAG.MC IBE.MC
IDR.MC ITX.MC LOG.MC MAP.MC MRL.MC MTS.MC NTGY.MC PUIG.MC RED.MC REP.MC ROVI.MC SAB.MC SAN.MC SCYR.MC SLR.MC TEF.MC UNI.MC
EDP.LS EDPR.LS GALP.LS JMT.LS BCP.LS NOS.LS SON.LS CTT.LS RENE.LS
NOKIA.HE NESTE.HE FORTUM.HE KNEBV.HE UPM.HE STERV.HE SAMPO.HE ELISA.HE WRT1V.HE KESKOB.HE ORNBV.HE OUT1V.HE METSO.HE
NDA-FI.HE KCR.HE TYRES.HE VALMT.HE HUH1V.HE
RYA.IR KRX.IR BIRG.IR A5G.IR GL9.IR
EBS.VI OMV.VI VER.VI VOE.VI RBI.VI ANDR.VI WIE.VI BG.VI POST.VI CAI.VI UQA.VI VIG.VI
NESN.SW NOVN.SW ROG.SW UBSG.SW ZURN.SW ABBN.SW CFR.SW LONN.SW SIKA.SW GIVN.SW ALC.SW HOLN.SW SREN.SW SCMN.SW PGHN.SW GEBN.SW
PARG.SW SLHN.SW LOGN.SW SOON.SW STMN.SW KNIN.SW SGSN.SW UHR.SW TEMN.SW BALN.SW BAER.SW AMS.SW VACN.SW HELN.SW LISN.SW LISP.SW
EMSN.SW BUCN.SW SCHP.SW SQN.SW BARN.SW FHZN.SW DKSH.SW ADEN.SW CLN.SW GALD.SW SDZ.SW SRAIL.SW
ABB.ST ALFA.ST ASSA-B.ST ATCO-A.ST ATCO-B.ST AZN.ST BOL.ST ELUX-B.ST ERIC-B.ST ESSITY-B.ST EVO.ST GETI-B.ST HEXA-B.ST HM-B.ST
INVE-B.ST KINV-B.ST NDA-SE.ST NIBE-B.ST SAND.ST SBB-B.ST SCA-B.ST SEB-A.ST SHB-A.ST SINCH.ST SKA-B.ST SKF-B.ST SWED-A.ST
TEL2-B.ST TELIA.ST VOLV-B.ST SAAB-B.ST EQT.ST INDU-C.ST LIFCO-B.ST EPI-A.ST ADDT-B.ST AAK.ST HUSQ-B.ST SECU-B.ST TREL-B.ST
SOBI.ST BALD-B.ST LATO-B.ST AXFO.ST HOLM-B.ST CAST.ST FABG.ST SAGA-B.ST BEIJ-B.ST THULE.ST
NOVO-B.CO MAERSK-B.CO MAERSK-A.CO DSV.CO CARL-B.CO COLO-B.CO DANSKE.CO DEMANT.CO GMAB.CO GN.CO ISS.CO JYSK.CO NKT.CO NSIS-B.CO
ORSTED.CO PNDORA.CO ROCK-B.CO RBREW.CO TRYG.CO VWS.CO ZEAL.CO BAVA.CO AMBU-B.CO NETC.CO FLS.CO SYDB.CO
EQNR.OL DNB.OL MOWI.OL NHY.OL ORK.OL TEL.OL YAR.OL AKRBP.OL SALM.OL KOG.OL GJF.OL STB.OL SUBC.OL TOM.OL NOD.OL AKER.OL FRO.OL
VAR.OL NAS.OL BAKKA.OL AUTO.OL SCHA.OL KAHOT.OL MPCC.OL HAFNI.OL BWLPG.OL AFG.OL
AZN.L SHEL.L HSBA.L ULVR.L BP.L RIO.L GSK.L REL.L DGE.L LSEG.L BATS.L NG.L RR.L GLEN.L LLOY.L BARC.L CPG.L AAL.L PRU.L BA.L
EXPN.L TSCO.L HLN.L NWG.L VOD.L IMB.L III.L SSE.L STAN.L ABF.L AHT.L ANTO.L AV.L BKG.L BNZL.L BT-A.L BRBY.L CNA.L CCH.L
CRDA.L DCC.L ENT.L FRES.L HL.L HLMA.L HSX.L IAG.L IHG.L IMI.L INF.L ITRK.L JD.L KGF.L LAND.L LGEN.L MKS.L MNDI.L MNG.L NXT.L
PSN.L PSON.L RKT.L RMV.L RTO.L SBRY.L SDR.L SGE.L SGRO.L SMIN.L SMT.L SN.L SPX.L SVT.L TW.L UU.L WEIR.L WPP.L WTB.L AUTO.L
BEZ.L HWDN.L ICG.L PHNX.L UTG.L GAW.L DPLM.L BME.L EZJ.L FCIT.L
"""
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
us_only["sources"] = {k: v for k, v in src_status.items() if k not in ("FinMind 加權指數", "證交所收盤價", "櫃買中心收盤價", "FRED BAA 利差")}
with open(f"{OUT}/friends/data.json", "w") as f:
    json.dump(us_only, f, ensure_ascii=False, separators=(",", ":"))
print("CHANGES: " + ("；".join(changes) if changes else "none"))
print("ok", out["generated"], {k: out[k]["state"] for k in ["tw", "us"] if k in out}, src_status)
