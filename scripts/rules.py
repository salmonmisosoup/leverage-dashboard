"""
現有規則（台股、美股相同，2026/11 回測定案）——每天模擬一次，算出今天的訊號、模型持倉與該做的動作。

三種部位：二倍槓桿 v2、一倍原型 v1、子彈 vb。每天依序檢查，前面成立就不看後面：
  1. 恐慌加碼：VIX ≥ 35 → 二倍槓桿 85%（美國 2 年期殖利率 3 個月升 > 0.5 或 BAA 利差 3 個月擴大 > 0.7 時這一階暫停）
               VIX ≥ 40 → 100%
               深跌補滿：1 年內 VIX 曾 ≥ 35、距一年高點跌 > 30%、利差 3 個月擴大 < 0.5 → 100%
               利差 3 個月擴大 > 0.8 時全部恐慌加碼暫停，最多 30 個交易日（台美相同，2026/11 美股也加入）
               加碼先用一倍原型，再用子彈
  2. 融資退燒換回：融資訊號關閉滿 315 個交易日（約 15 個月）且收盤在季線上 → 一倍原型全部換回二倍槓桿
  3. RSI 過熱調節：週 RSI > 75（美股）／80（台股）且二倍槓桿 > 63% → 調回 60%，賣出的錢買子彈
  4. 融資過熱：訊號成立、恐慌加碼後已過 60 個交易日、VIX < 35、不在深跌區 → 二倍槓桿全部轉一倍原型
     美股訊號：FINRA 融資年增 > 50%；台股訊號：融資÷指數一年增加 > 20% 且融資兩年增長 > 20%，或美股訊號成立
台股另有：近 20 日跌 ≥ 5%、台指 VIX ≥ 40、美國信用利差 3 個月擴大 < 0.3 → 視同 VIX ≥ 40，加到 100%
每月薪資：收盤在季線下方全部買二倍槓桿，否則 60／40；融資轉換條件成立時，二倍槓桿那一份改買一倍原型。
"""
import numpy as np, pandas as pd

BASE = 0.60
COOL = 60
REOFF = 315
CFG = {"tw": {"rsi": 80, "shift": True, "brun": True}, "us": {"rsi": 75, "shift": False, "brun": True}}


def wrsi(close, n=14):
    wk = close.resample("W-FRI").last().dropna(); d = wk.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n).mean(); dn = (-d.clip(upper=0)).ewm(alpha=1 / n).mean()
    return 100 - 100 / (1 + up / dn)


def us_margin_yoy(debt):
    """debt: 月資料（index = 該月第一天）。次月下旬公布 → 用再下個月初起才算已知"""
    s = debt.sort_index(); y = s / s.shift(12) - 1
    y.index = y.index + pd.offsets.MonthBegin(2)
    return y.dropna()


def run(key, close, vix, baa, dgs2, tw_margin=None, us_debt=None, start="2015-01-01", vix_today=None, vixtwn=None):
    c = CFG[key]; th = c["rsi"]
    P = close.dropna().astype(float); D = P.index
    ma60 = P.rolling(60).mean(); r60 = P / ma60 - 1
    rsi = wrsi(P).reindex(D, method="ffill")
    V = vix.reindex(D, method="ffill")
    lvl = baa.reindex(D, method="ffill"); y2 = dgs2.reindex(D, method="ffill")
    if c["shift"]:                       # 台股開盤前只知道美股前一晚的收盤
        V = V.shift(1); lvl = lvl.shift(1); y2 = y2.shift(1)
        if vix_today is not None: V.iloc[-1] = vix_today
    BAAC = (lvl - lvl.shift(63)).fillna(0)
    Y2C = (y2 - y2.shift(63)).fillna(0)
    G1 = (Y2C < 0.5) & (BAAC < 0.7)
    DGATE = BAAC < 0.5
    DD = P / P.rolling(252, min_periods=1).max() - 1
    # 台股限定：台股自己急跌（近 20 日跌 ≥ 5%）、台指 VIX ≥ 40、美國信用利差 3 個月擴大 < 0.3 → 視同 VIX ≥ 40，加到 100%
    USV = V.copy(); TWC = None; TWV = None; R20 = P / P.shift(20) - 1
    if key == "tw" and vixtwn is not None and len(vixtwn):
        TWV = vixtwn.reindex(D, method="ffill", limit=5).shift(1)
        TWV.iloc[-1] = float(vixtwn.iloc[-1])           # 今天：用最新一筆
        TWC = (TWV >= 40) & (R20 <= -0.05) & (BAAC < 0.3)
        V = pd.Series(np.where(TWC.values, np.fmax(V.values, 40.0), V.values), index=D)
    VM = V.rolling(252, min_periods=1).max()
    USM = us_margin_yoy(us_debt).reindex(D, method="ffill").fillna(0) if us_debt is not None else pd.Series(0., index=D)
    if key == "tw":
        L = tw_margin.dropna().astype(float)
        Ls = L.shift(1)
        TWY = (Ls / Ls.shift(250) - 1).reindex(D, method="ffill").fillna(0)
        Lr = L.shift(1).reindex(D, method="ffill"); TW2 = (Lr / Lr.shift(500) - 1).fillna(0)
        # 台股融資過熱：融資餘額÷加權報酬指數 一年增加 > 20%（融資增加得比股價快），且融資兩年增長 > 20%；或美股訊號成立
        RR = Lr / P; TWR = (RR / RR.shift(250) - 1).fillna(0)
        MG = ((TWR > 0.20) & (TW2 > 0.20)) | (USM > 0.50)
    else:
        TWY = TW2 = TWR = None
        MG = USM > 0.50
    brun = np.zeros(len(D), int)
    if c["brun"]:
        b = BAAC.values
        for i in range(len(D)): brun[i] = (brun[i - 1] + 1 if i else 1) if b[i] > 0.8 else 0
    offrun = np.zeros(len(D), int)
    m_ = MG.values
    for i in range(len(D)): offrun[i] = 0 if m_[i] else (offrun[i - 1] + 1 if i else 1)

    r = P.pct_change().fillna(0).values
    ix = np.where(D >= pd.Timestamp(start))[0]
    v2, v1, vb = BASE, 0.0, 1 - BASE
    la = -10 ** 9; ev = []
    Vv, G1v, DGv, DDv, VMv, RSv, R60 = V.values, G1.values, DGATE.values, DD.values, VM.values, rsi.values, r60.values
    for i in ix:
        v2 *= 1 + 2 * r[i]; v1 *= 1 + r[i]; tot = v2 + v1 + vb; w = v2 / tot
        vv = Vv[i] if not np.isnan(Vv[i]) else 0
        blk = c["brun"] and 0 < brun[i] <= 30
        deep_raw = DDv[i] <= -0.30 and VMv[i] >= 35
        t = 0.0; why = None
        if not blk:
            if vv >= 35 and G1v[i]: t, why = 0.85, "panic1"
            if vv >= 40: t, why = 1.0, ("twvix" if TWC is not None and TWC.values[i] and not (USV.values[i] >= 40) else "panic2")
            if deep_raw and DGv[i] and t < 1: t, why = 1.0, "deep"
        act = None
        if t > w + 0.03:
            need = (t - w) * tot; u1 = min(v1, need); v1 -= u1; v2 += u1; need -= u1
            u = min(vb, need); vb -= u; v2 += u; la = i; act = why
        elif offrun[i] >= REOFF and v1 > 0 and R60[i] > 0:
            v2 += v1; v1 = 0.0; act = "re"
        elif RSv[i] > th and w > BASE + 0.03:
            x = (w - BASE) * tot; v2 -= x; vb += x; act = "rsi"
        elif m_[i] and i - la > COOL and vv < 35 and not deep_raw and v2 > 0:
            v1 += v2; v2 = 0.0; act = "mg"
        if act: ev.append((D[i].strftime("%Y-%m-%d"), act))
        s = v2 + v1 + vb; v2, v1, vb = v2 / s, v1 / s, vb / s   # 正規化，避免數值漂移

    i = len(D) - 1; vv = None if np.isnan(Vv[i]) else float(Vv[i])
    blk = bool(c["brun"] and 0 < brun[i] <= 30)
    deep_raw = bool(DDv[i] <= -0.30 and VMv[i] >= 35)
    days_since_add = int(i - la) if la > 0 else None
    cool = days_since_add is not None and days_since_add <= COOL
    panic_zone = vv is not None and vv >= 35
    conv_ok = bool(m_[i] and not cool and not panic_zone and not deep_raw)
    t = 0.0; why = None
    if not blk:
        if vv is not None and vv >= 35 and G1v[i]: t, why = 0.85, "panic1"
        if vv is not None and vv >= 40: t, why = 1.0, ("twvix" if TWC is not None and TWC.values[i] and not (USV.values[i] >= 40) else "panic2")
        if deep_raw and DGv[i] and t < 1: t, why = 1.0, "deep"
    hi252 = float(P.iloc[-252:].max())
    last_vix35 = USV[USV >= 35]; usv = None if np.isnan(USV.values[i]) else float(USV.values[i])
    out = {
        "base": BASE, "rsi_th": th, "cool_days": COOL, "reoff_days": REOFF,
        "close": round(float(P.iloc[-1]), 2), "ma60": round(float(ma60.iloc[-1]), 2), "below60": bool(R60[i] <= 0),
        "rsi": round(float(RSv[i]), 1), "rsi_hot": bool(RSv[i] > th),
        "vix": usv,
        "twvix": None if TWV is None else {"v": None if np.isnan(TWV.values[i]) else round(float(TWV.values[i]), 2), "asof": vixtwn.index[-1].strftime("%Y-%m-%d"),
                  "r20": round(float(R20.iloc[-1]), 4), "on": bool(TWC.values[i])},
        "panic": {"target": t, "why": why, "blocked": blk, "brun": int(brun[i]),
                  "g1": bool(G1v[i]), "y2_chg": round(float(Y2C.iloc[-1]), 2), "baa_chg": round(float(BAAC.iloc[-1]), 2),
                  "deep": {"dd": round(float(DDv[i]), 4), "hi252": round(hi252, 2), "line": round(hi252 * 0.7, 2),
                           "vix_max252": round(float(VMv[i]), 2), "credit_ok": bool(DGv[i]), "on": bool(deep_raw and DGv[i])},
                  "last_vix35": last_vix35.index[-1].strftime("%Y-%m-%d") if len(last_vix35) else None},
        "margin": {"on": bool(m_[i]), "us_yoy": round(float(USM.iloc[-1]), 4),
                   "tw_yoy": round(float(TWY.iloc[-1]), 4) if TWY is not None else None,
                   "tw_2y": round(float(TW2.iloc[-1]), 4) if TW2 is not None else None,
                   "tw_ratio": round(float(TWR.iloc[-1]), 4) if TWR is not None else None,
                   "off_days": int(offrun[i]), "reentry_ready": bool(offrun[i] >= REOFF and R60[i] > 0)},
        "cool": {"days_since_add": days_since_add, "active": bool(cool)},
        "conv_ok": conv_ok, "panic_zone": bool(panic_zone), "deep_zone": deep_raw,
        "model": {"w2": round(v2, 4), "w1": round(v1, 4), "wb": round(vb, 4)},
        "events": ev[-40:],
    }
    # 今天模型做了什麼（就是規則今天要你做的事）
    out["today"] = ev[-1][1] if ev and ev[-1][0] == D[-1].strftime("%Y-%m-%d") else None
    # 每月薪資
    out["salary"] = {"all": out["below60"], "to": "1x" if conv_ok else "2x"}
    return out
