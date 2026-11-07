"""盤中即時監控（取代每 20 分鐘的 tw_live.py）

GitHub Actions 在台股、美股交易時段各啟動一次，這支程式在時段內每 LOOP 秒抓一次：
  台股時段：期交所台指 VIX、證交所加權指數
  美股時段：CBOE VIX（延遲約 15 分鐘）
結果寫成 live.json，推到 live 分支（只保留一個 commit），儀表板每次重整直接從 GitHub API 讀，
不用等 Pages 重新部署。

台股急跌規則的盤中通知（條件：近 20 日跌 ≥ 10%、美國信用利差 3 個月擴大 < 0.3、沒有在利差暫停期）：
  台指 VIX 盤中 ≥ 40 → 寄「注意」通知（每天一次）
  台指 VIX 盤中 ≥ 45 → 寄「立即加碼」通知（每天一次），依規則當下就把二倍槓桿加到 100%
"""
import json, os, subprocess, time, smtplib, urllib.request, datetime as dt
from email.mime.text import MIMEText

LOOP = int(os.environ.get("LOOP", "60"))
TZ8 = dt.timezone(dt.timedelta(hours=8))
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"}
WARN, BUY = 40.0, 45.0


def req(u, data=None, h=None, timeout=20):
    r = urllib.request.Request(u, data=data, headers={**UA, **(h or {})})
    return urllib.request.urlopen(r, timeout=timeout).read()


def num(x):
    try:
        v = float(str(x).replace(",", ""))
        return v if v > 0 else None
    except Exception:
        return None


def tw_vix():
    q = json.loads(req("https://mis.taifex.com.tw/futures/api/getQuoteListVIX", b"{}", {"Content-Type": "application/json"}))["RtData"]["QuoteList"][0]
    return num(q.get("CLastPrice")), num(q.get("CHighPrice")), str(q.get("CTime", ""))[:4], str(q.get("CDate", ""))


def taiex():
    s = req("https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch=tse_t00.tw&json=1&delay=0").decode("utf-8", "ignore")
    m = json.loads(s[s.index("{"):])["msgArray"][0]
    return num(m.get("z")) or num(m.get("y")), num(m.get("l")), str(m.get("%", ""))[:5], str(m.get("d", ""))


def us_vix():
    q = json.loads(req("https://cdn-api.cboe.com/api/global/delayed_quotes/quotes/_VIX.json"))["data"]
    return num(q.get("current_price")), num(q.get("high")), str(q.get("last_trade_time", ""))[:16]


def mail(subject, body):
    u, p, to = os.environ.get("MAIL_USERNAME"), os.environ.get("MAIL_PASSWORD"), os.environ.get("MAIL_TO")
    if not (u and p and to):
        return
    try:
        msg = MIMEText(body, "plain", "utf-8"); msg["Subject"] = subject; msg["From"] = f"加碼儀表板 <{u}>"; msg["To"] = to
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as s:
            s.login(u, p); s.sendmail(u, [x.strip() for x in to.split(",")], msg.as_string())
    except Exception as e:
        print("mail failed", type(e).__name__)


def issue(title, body):
    try:
        subprocess.run(["gh", "issue", "create", "--title", title, "--body", body], check=False, timeout=60)
    except Exception as e:
        print("issue failed", type(e).__name__)


def push(out):
    """live 分支只放一個檔案、一個 commit（每次覆蓋），不會觸發 Pages 部署"""
    d = "/tmp/livebr"
    os.makedirs(d, exist_ok=True)
    json.dump(out, open(f"{d}/live.json", "w"), ensure_ascii=False)
    url = subprocess.run(["git", "remote", "get-url", "origin"], capture_output=True, text=True).stdout.strip()
    env = {**os.environ, "GIT_DIR": f"{d}/.git", "GIT_WORK_TREE": d}
    if not os.path.isdir(f"{d}/.git"):
        subprocess.run(["git", "init", "-q", "-b", "live"], env=env, check=True)
        subprocess.run(["git", "remote", "add", "origin", url], env=env, check=True)
        hdr = subprocess.run(["git", "config", "--get-regexp", r"http\..*\.extraheader"], capture_output=True, text=True).stdout.split("\n")[0]
        if hdr:
            k, v = hdr.split(" ", 1); subprocess.run(["git", "config", k, v], env=env, check=True)
        subprocess.run(["git", "config", "user.name", "github-actions[bot]"], env=env)
        subprocess.run(["git", "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com"], env=env)
    subprocess.run(["git", "add", "live.json"], env=env, check=True)
    subprocess.run(["git", "commit", "-q", "--amend" if subprocess.run(["git", "rev-parse", "-q", "--verify", "HEAD"], env=env, capture_output=True).returncode == 0 else "--allow-empty", "-m", "live"], env=env, check=False)
    r = subprocess.run(["git", "push", "-q", "-f", "origin", "HEAD:live"], env=env, capture_output=True, text=True)
    if r.returncode:
        print("push failed", r.stderr[-300:])


def load_prev():
    try:
        return json.loads(req("https://raw.githubusercontent.com/" + os.environ.get("GITHUB_REPOSITORY", "") + f"/live/live.json?t={int(time.time())}"))
    except Exception:
        return {}


def main():
    D = json.load(open("docs/data.json"))["tw"]; H = D["hist"]; p = D["rule"]["panic"]
    out = load_prev() or {}
    sent = out.get("sent", {})
    utc = dt.datetime.now(dt.timezone.utc)
    tw_session = utc.hour < 8                     # 00:55 UTC 啟動的是台股時段，其餘是美股時段
    end = utc + dt.timedelta(minutes=int(os.environ.get("MAX_MIN", "350")))
    stop = utc.replace(hour=5, minute=40) if tw_session else utc.replace(hour=21, minute=10)
    end = min(end, stop)
    last = None; first = True
    while first or dt.datetime.now(dt.timezone.utc) < end:
        first = False
        now8 = dt.datetime.now(TZ8); today = now8.strftime("%Y-%m-%d")
        out["t"] = now8.strftime("%Y-%m-%d %H:%M:%S")
        if tw_session:
            try:
                v, hi, tt, dd = tw_vix()
                qd = f"{dd[:4]}-{dd[4:6]}-{dd[6:8]}" if len(dd) >= 8 else today   # 報價日期（週末、假日是上一個交易日）
                if v:
                    if out.get("tw_d") != qd:
                        out["tw_hi"] = None
                    out.update(tw_vix=v, tw_t=tt, tw_d=qd)
                    out["tw_hi"] = max(x for x in (v, hi, out.get("tw_hi")) if x)
            except Exception as e:
                out["tw_err"] = type(e).__name__
            try:
                px, lo, tt, dd = taiex()
                if px:
                    out.update(taiex=px, taiex_t=tt)
                    k = 20 if H["date"][-1] < (out.get("tw_d") or today) else 21
                    out["r20"] = round(px / H["close"][-k] - 1, 4)
            except Exception as e:
                out["taiex_err"] = type(e).__name__
            out["baa_chg"] = p["baa_chg"]; out["blocked"] = bool(p["blocked"])
            live_today = out.get("tw_d") == today and now8.weekday() < 5          # 只在今天真的有交易時通知
            cond = out.get("r20", 0) <= -0.10 and p["baa_chg"] < 0.3 and not p["blocked"]
            v = out.get("tw_vix") or 0
            out["cond"] = bool(cond)
            out["w40"] = bool(cond and v >= WARN)
            out["b45"] = bool(cond and v >= BUY)
            info = f"台指 VIX {v}（{out.get('tw_t','')}）、加權指數 {out.get('taiex')}、近 20 日 {out.get('r20',0)*100:.1f}%、信用利差 3 個月 {p['baa_chg']:+.2f}"
            if live_today and out["b45"] and sent.get("b45") != today:
                sent["b45"] = today; sent["w40"] = today
                t_ = "❗ 盤中台指 VIX ≥ 45：台股急跌規則成立，現在加到 100%"
                b_ = f"{info}\n\n依規則現在就把台股二倍槓桿加到 100%：先賣 0050，不夠再賣 00713，買 00685L。\nhttps://salmonmisosoup.github.io/leverage-dashboard/"
                mail(t_, b_); issue(t_ + f" {today}", b_)
            elif live_today and out["w40"] and sent.get("w40") != today:
                sent["w40"] = today
                t_ = "注意：盤中台指 VIX ≥ 40，台股急跌條件接近"
                b_ = f"{info}\n\n盤中 ≥ 45 會立即觸發加碼；收盤 ≥ 40 則明天收盤前加碼。請留意盤中變化。\nhttps://salmonmisosoup.github.io/leverage-dashboard/"
                mail(t_, b_)
        try:
            v, hi, lt = us_vix()
            if v:
                out.update(us_vix=v, us_hi=hi, us_t=lt)
        except Exception as e:
            out["us_err"] = type(e).__name__
        out["sent"] = sent
        key = {k: out.get(k) for k in ("tw_vix", "tw_hi", "taiex", "us_vix", "us_t", "sent")}
        if key != last:
            push(out); last = key
        print(out["t"], out.get("tw_vix"), out.get("taiex"), out.get("us_vix"), flush=True)
        time.sleep(LOOP)


if __name__ == "__main__":
    main()
