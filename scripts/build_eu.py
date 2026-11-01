"""每天抓一次歐洲各交易所的股票和 ETF 收盤價，給朋友版「你的持股」查價用。
代號清單來自 FinanceDatabase（MIT 授權，https://github.com/JerBouma/FinanceDatabase），價格來自 Yahoo Finance。
輸出 docs/us/eu.json：
  p: {代號: [原幣價格, 幣別, 名稱]}
  a: {沒有交易所代碼的代號: 完整代號}     例 SAP -> SAP.DE
  m: {同代號但不同公司: [完整代號, ...]}  例 SAN -> [SAN.MC, SAN.PA]
  i: {ISIN: 完整代號}
另外輸出 docs/us/usn.json：{美股代號: 名稱}
  fx: {EURUSD: ..., EURGBP: ...}"""
import sys, json, time, urllib.request, datetime as dt
from concurrent.futures import ThreadPoolExecutor
import financedatabase as fd

OUT = sys.argv[1] if len(sys.argv) > 1 else "docs/us/eu.json"
EXCH = ["GER", "PAR", "AMS", "BRU", "MIL", "MCE", "LIS", "ISE", "HEL", "STO", "CPH", "OSL", "EBS", "VIE", "LSE"]
EU_ISIN = set("DE FR NL BE IT ES PT IE LU FI SE DK NO CH AT GB JE GG IM".split())
HOME = {"DE": "GER", "FR": "PAR", "NL": "AMS", "BE": "BRU", "IT": "MIL", "ES": "MCE", "PT": "LIS", "FI": "HEL", "SE": "STO",
        "DK": "CPH", "NO": "OSL", "CH": "EBS", "AT": "VIE", "GB": "LSE", "JE": "LSE", "GG": "LSE", "IM": "LSE"}

def get(url, tries=3):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=40) as r: return json.loads(r.read().decode())
        except Exception as e:
            last = e; time.sleep(3 * (i + 1))
    raise last

US_EXCH = ["NMS", "NYQ", "NGM", "NCM", "ASE", "PCX", "BTS"]
dfs = (fd.Equities().select(), fd.ETFs().select())
# 美股名稱（價格由網頁向 FinMind 即時查）
usn = {}
for df in dfs:
    for sym, r in df[df["exchange"].isin(US_EXCH)].iterrows():
        sym = str(sym).upper()
        if "." in sym or (r.get("delisted") is True): continue
        if isinstance(r["name"], str) and sym not in usn: usn[sym] = r["name"][:44]
json.dump(usn, open(OUT.replace("eu.json", "usn.json"), "w"), ensure_ascii=False, separators=(",", ":"))
print(f"美股名稱 {len(usn)} 檔", {k: usn.get(k) for k in ["NVDA", "QLD", "GOOG", "GGLL", "SPCX", "SGOV"]})
rows = []
for df in dfs:
    df = df[df["exchange"].isin(EXCH)]
    if "delisted" in df: df = df[df["delisted"] != True]
    for sym, r in df.iterrows():
        isin = r["isin"] if isinstance(r["isin"], str) and len(r["isin"]) == 12 else ""
        if isin and isin[:2] not in EU_ISIN: continue          # 歐洲交易所掛的美股等，請直接用原本的代號
        rows.append((str(sym).upper(), isin, r["exchange"], str(r["name"] or "")[:48]))
syms = sorted({r[0] for r in rows})
print(f"候選 {len(syms)} 檔")

def spark(batch):
    try: j = get("https://query1.finance.yahoo.com/v7/finance/spark?symbols=" + ",".join(batch) + "&range=5d&interval=1d")
    except Exception: return []
    res = []
    for it in (j.get("spark") or {}).get("result") or []:
        try:
            m = it["response"][0]["meta"]; p = m.get("regularMarketPrice"); cur = m.get("currency"); t = m.get("regularMarketTime") or 0
            if p and cur and time.time() - t < 15 * 86400:
                if cur in ("GBp", "GBX"): p, cur = p / 100, "GBP"
                res.append((it["symbol"].upper(), float(p), cur))
        except Exception: pass
    return res

batches = [syms[i:i + 20] for i in range(0, len(syms), 20)]
px = {}
with ThreadPoolExecutor(4) as ex:
    for res in ex.map(spark, batches):
        for s, p, c in res: px[s] = (p, c)
fx = {}
for c in ["USD", "GBP", "CHF", "SEK", "DKK", "NOK", "PLN"]:
    try: fx["EUR" + c] = round(get(f"https://query1.finance.yahoo.com/v8/finance/chart/EUR{c}=X?range=5d&interval=1d")["chart"]["result"][0]["meta"]["regularMarketPrice"], 5)
    except Exception: pass
ok_cur = {"EUR"} | {k[3:] for k in fx}
print(f"有價格 {len(px)} 檔")

PREF = ["GER", "PAR", "AMS", "MIL", "MCE", "BRU", "LIS", "ISE", "HEL", "STO", "CPH", "OSL", "LSE", "EBS", "VIE"]
OVERRIDE = {"LQQ": "LQQ.PA", "IB01": "IB01.L", "CSPX": "CSPX.L", "CNDX": "CNDX.L", "ERNE": "ERNE.L"}
P, info = {}, {}
for sym, isin, exch, name in rows:
    if sym not in px or px[sym][1] not in ok_cur or sym in P: continue
    p, c = px[sym]; P[sym] = [round(p, 4), c, name]; info[sym] = (isin, exch)
# 主要掛牌：公司本國交易所 > 歐元計價 > 交易所順序
def rank(sym):
    isin, exch = info[sym]
    return (0 if exch == HOME.get(isin[:2]) else 1 if P[sym][1] == "EUR" else 2, PREF.index(exch))
by_isin, by_base = {}, {}
for sym, (isin, exch) in info.items():
    if isin: by_isin.setdefault(isin, []).append(sym)
    by_base.setdefault(sym.rsplit(".", 1)[0], []).append(sym)
I = {k: min(v, key=rank) for k, v in by_isin.items()}
A, M = {}, {}
for b, ls in by_base.items():
    if b in P: continue
    isins = {info[x][0] for x in ls if info[x][0]}
    if len(isins) <= 1: A[b] = min(ls, key=rank)                       # 同一檔（或缺 ISIN）：選主要掛牌
    else: M[b] = sorted(min([x for x in ls if info[x][0] == k], key=rank) for k in isins)
for b, sym in OVERRIDE.items():
    if sym in P: A[b] = sym; M.pop(b, None)
doc = {"d": dt.date.today().isoformat(), "fx": fx, "p": P, "a": A, "m": M, "i": I}
json.dump(doc, open(OUT, "w"), ensure_ascii=False, separators=(",", ":"))
print(f"輸出 {len(P)} 檔，免交易所代碼 {len(A)}，同代號多檔 {len(M)}")
for t in ["SAP", "SAN", "ASML", "VWCE", "IB01", "LQQ", "NESN", "AZN", "CSPX", "MT", "RACE", "SHEL", "IWDA"]:
    print(t, A.get(t), M.get(t))
