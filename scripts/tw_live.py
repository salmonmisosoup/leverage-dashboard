"""盤中監控：期交所台指 VIX、證交所加權指數（台股交易時間每 20 分鐘），寫入 docs/twlive.json"""
import json, urllib.request, os, datetime as dt
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"}
def req(u, data=None, h=None):
    r = urllib.request.Request(u, data=data, headers={**UA, **(h or {})})
    return urllib.request.urlopen(r, timeout=30).read()
out = {"t": dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")}
try:
    q = json.loads(req("https://mis.taifex.com.tw/futures/api/getQuoteListVIX", b"{}", {"Content-Type": "application/json"}))["RtData"]["QuoteList"][0]
    out["vix"] = float(q["CLastPrice"]); out["vix_t"] = q.get("CTime", "")[:4]; out["vix_d"] = q.get("CDate")
except Exception as e:
    out["vix_err"] = type(e).__name__
try:
    s = req("https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch=tse_t00.tw&json=1&delay=0").decode("utf-8", "ignore")
    m = json.loads(s[s.index("{"):])["msgArray"][0]
    z = m.get("z"); out["taiex"] = float(z if z not in (None, "-", "") else m["y"]); out["taiex_t"] = m.get("%", "")[:5]
except Exception as e:
    out["taiex_err"] = type(e).__name__
d = json.load(open("docs/data.json"))["tw"]; H = d["hist"]; today = out["t"][:10]
if "taiex" in out:
    k = 20 if H["date"][-1] != today else 21          # 20 個交易日前的收盤
    out["r20"] = round(out["taiex"] / H["close"][-k] - 1, 4)
p = d["rule"]["panic"]
out["baa_chg"] = p["baa_chg"]
out["on"] = bool(out.get("vix", 0) >= 40 and out.get("r20", 0) <= -0.10 and p["baa_chg"] < 0.3 and not p["blocked"])
prev = {}
try: prev = json.load(open("docs/twlive.json"))
except Exception: pass
json.dump(out, open("docs/twlive.json", "w"), ensure_ascii=False)
print(out)
if out["on"] and not (prev.get("on") and prev.get("t", "")[:10] == today):
    print("NEWON")
