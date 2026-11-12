"""台股盤中監控：台北時間 09:00–13:40 每 20 分鐘跑一次（一次只抓一筆，幾秒就結束）
抓期交所台指 VIX（含當日最高）、證交所加權指數，寫進 docs/twlive.json。
台股急跌規則的盤中通知（近 20 日跌 ≥ 10%、信用利差 3 個月擴大 < 0.3、沒有在利差暫停期）：
  台指 VIX ≥ 40 → 注意（每天一次）
  台指 VIX ≥ 45 → 依規則立即加到 100%（每天一次）
要寄的通知寫到 GITHUB_OUTPUT 的 alert=w40 / b45，由 workflow 寄信、開 issue。
"""
import json, os, urllib.request, datetime as dt

UA = {"User-Agent": "Mozilla/5.0 (compatible; leverage-dashboard/1.0)"}
now8 = dt.datetime.now(dt.timezone(dt.timedelta(hours=8))); today = now8.strftime("%Y-%m-%d")


def num(x):
    try:
        v = float(str(x).replace(",", "")); return v if v > 0 else None
    except Exception:
        return None


try:
    prev = json.load(open("docs/twlive.json"))
except Exception:
    prev = {}
out = {"t": now8.strftime("%Y-%m-%d %H:%M:%S"), "sent": prev.get("sent", {})}
try:
    r = urllib.request.Request("https://mis.taifex.com.tw/futures/api/getQuoteListVIX", data=b"{}", headers={**UA, "Content-Type": "application/json"})
    q = json.loads(urllib.request.urlopen(r, timeout=20).read())["RtData"]["QuoteList"][0]
    cd = str(q.get("CDate", ""))
    out["tw_d"] = f"{cd[:4]}-{cd[4:6]}-{cd[6:8]}" if len(cd) >= 8 else today
    out["tw_vix"] = num(q.get("CLastPrice")); out["tw_t"] = str(q.get("CTime", ""))[:4]
    hi = [x for x in (num(q.get("CHighPrice")), out["tw_vix"], prev.get("tw_hi") if prev.get("tw_d") == out["tw_d"] else None) if x]
    out["tw_hi"] = max(hi) if hi else None
except Exception as e:
    out["tw_err"] = type(e).__name__
try:
    r = urllib.request.Request("https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch=tse_t00.tw&json=1&delay=0", headers=UA)
    s = urllib.request.urlopen(r, timeout=20).read().decode("utf-8", "ignore"); m = json.loads(s[s.index("{"):])["msgArray"][0]
    out["taiex"] = num(m.get("z")) or num(m.get("y")); out["taiex_t"] = str(m.get("t", ""))[:5]
except Exception as e:
    out["taiex_err"] = type(e).__name__

D = json.load(open("docs/data.json"))["tw"]; H = D["hist"]; p = D["rule"]["panic"]
qd = out.get("tw_d") or today
if out.get("taiex"):
    k = 20 if H["date"][-1] < qd else 21
    out["r20"] = round(out["taiex"] / H["close"][-k] - 1, 4)
out["baa_chg"] = p["baa_chg"]; out["blocked"] = bool(p["blocked"])
v = out.get("tw_vix") or 0
out["cond"] = bool(out.get("r20", 0) <= -0.10 and p["baa_chg"] < 0.3 and not p["blocked"])
out["w40"] = bool(out["cond"] and v >= 40); out["b45"] = bool(out["cond"] and v >= 45)

alert = ""
if qd == today:                                   # 只在今天真的有交易時通知
    if out["b45"] and out["sent"].get("b45") != today:
        alert = "b45"; out["sent"]["b45"] = today; out["sent"]["w40"] = today
    elif out["w40"] and out["sent"].get("w40") != today:
        alert = "w40"; out["sent"]["w40"] = today
json.dump(out, open("docs/twlive.json", "w"), ensure_ascii=False)
info = f"台指 VIX {v}（{out.get('tw_t','')}）、加權指數 {out.get('taiex')}、近 20 日 {out.get('r20',0)*100:.1f}%、信用利差 3 個月 {p['baa_chg']:+.2f}"
if alert and os.environ.get("GITHUB_OUTPUT"):
    with open(os.environ["GITHUB_OUTPUT"], "a") as f:
        f.write(f"alert={alert}\ninfo={info}\n")
print(alert or "-", info)
