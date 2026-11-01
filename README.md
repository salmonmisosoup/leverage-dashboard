# Leverage Dashboard · 正二加碼儀表板

**[English](#english) · [中文](#中文)**

**👉 https://salmonmisosoup.github.io/leverage-dashboard/home/**

![Nasdaq dashboard](docs/img/us-en.png)

---

## English

A free dashboard that tells you, every trading day, when to add to a 2x leveraged ETF position and when to trim it back, using rules backtested over 1990–2026. Enter your holdings and it works out exactly what to buy or sell.

> ⚠️ This is a rules-based signal from historical backtests, not investment advice. Leveraged ETFs can lose most of their value in a long bear market (backtested maximum drawdown around −85%). Decide based on your own finances and risk tolerance.

### Two versions

| Version | Link | For |
|---|---|---|
| **Nasdaq** | https://salmonmisosoup.github.io/leverage-dashboard/us/ | US investors (QLD + SGOV) or European investors (LQQ + IB01). English and Chinese. |
| **Taiwan + US** | https://salmonmisosoup.github.io/leverage-dashboard/ | Investors using a Taiwan broker: Taiwan 2x (00685L) plus US 2x (00830). Chinese only. |

### Rules

| | Taiwan | US (Nasdaq) |
|---|---|---|
| Base mix | 2x 60% / reserve 40% (00685L / 00713) | 2x 60% / T-bills 40% |
| Pullback | Close below the 60-day MA: all new money into 2x | Same |
| Panic buy | VIX ≥ 28 / 32 / 36 / 40 → 2x at 80 / 85 / 90 / 100% | VIX ≥ 35 → 85%; ≥ 40 → 100% |
| Pause | US BAA credit spread widens > 0.8 pt over 3 months: pause panic buying (max 30 trading days) | — |
| Trim | Weekly RSI > 80: trim 2x back to 60% | Weekly RSI > 75: trim 2x back to 60% |

Design notes, backtest comparisons and the main risks are under **How to use** on each page.

### Features

- Signals update every trading day; intraday VIX updates hourly during US market hours.
- **Your holdings**: type a ticker and share count, and the price fills in automatically. The page shows your current mix and the exact trades for today's signal, including how to split this month's savings. With no holdings yet, it tells you how to build the starting mix.
  - Taiwan: every TWSE / TPEx stock and ETF
  - US: any ticker
  - Europe: about 15,000 stocks and ETFs across European exchanges, by ticker or ISIN. If a ticker matches several securities (e.g. SAN = Santander or Sanofi), the page asks you to add the exchange suffix.
- Holdings are saved only in your own browser and never uploaded.
- Email alerts when a signal changes (when you run your own copy).

### Run your own copy

1. Fork this repository.
2. **GitHub Pages**: Settings → Pages → Source: *Deploy from a branch*, branch `main`, folder `/docs`.
3. **Actions write access**: Settings → Actions → General → Workflow permissions: *Read and write permissions*.
4. **FinMind token** (recommended): Settings → Secrets and variables → Actions → New repository secret, named `FINMIND_TOKEN`.
5. **Alerts** (optional):
   - By default, a GitHub Issue is opened when a signal changes, and GitHub emails your account.
   - Gmail directly: add secrets `MAIL_USERNAME`, `MAIL_PASSWORD` (a Gmail app password, not your login password) and `MAIL_TO`.
   - WhatsApp via CallMeBot: add secrets `WA_PHONE` and `WA_APIKEY`.

Secrets are encrypted and stay hidden even in a public repository. Never put tokens or passwords in code or pages.

### Schedules

| Workflow | When | What |
|---|---|---|
| `update.yml` | Weekdays 12:50 UTC, plus hourly during US market hours | `scripts/build_data.py`: fetches CBOE, FRED, FinMind, TWSE / TPEx and Yahoo data, computes the signals, updates `docs/data.json`, `docs/us/data.json` and `docs/prices.json` |
| `eu.yml` | Weekdays 17:10 UTC, after the European close | `scripts/build_eu.py`: updates European prices (`docs/us/eu.json`) and US ticker names (`docs/us/usn.json`) |

### Data sources

CBOE (VIX), FRED (credit spreads), FinMind (Taiwan and US prices), Taiwan Stock Exchange, Taipei Exchange, Yahoo Finance (European prices, FX). The ticker list comes from [FinanceDatabase](https://github.com/JerBouma/FinanceDatabase) (MIT).

### Feedback

Questions and ideas are welcome in [Discussions](https://github.com/salmonmisosoup/leverage-dashboard/discussions). Please report bugs in [Issues](https://github.com/salmonmisosoup/leverage-dashboard/issues).

### License

MIT

---

## 中文

用回測過的規則，每個交易日告訴你什麼時候把子彈轉成正二（加碼），什麼時候把漲多的正二調回基準（補子彈）。輸入自己的持股，還會直接算出要買賣哪幾檔、幾股。

> ⚠️ 這是依 1990–2026 年歷史回測整理的規則提示，不是投資建議。槓桿 ETF 在長期熊市中可能大幅虧損（回測最大回檔約 −85%），請依自身資金與風險承受度決定。

### 兩個版本

| 版本 | 網址 | 適合 |
|---|---|---|
| **納指版** | https://salmonmisosoup.github.io/leverage-dashboard/us/ | 美股（QLD＋SGOV）或歐洲券商（LQQ＋IB01），中英切換 |
| **雙市場版** | https://salmonmisosoup.github.io/leverage-dashboard/ | 用台灣券商：台股正二 00685L＋美股正二 00830，中文 |

### 規則摘要

| | 台股 | 美股（納指）|
|---|---|---|
| 基準 | 正二 60%／子彈 40%（00685L／00713）| 正二 60%／短期美債 40% |
| 中期回調 | 收盤在季線下方：當月薪資全買正二 | 同左 |
| 恐慌加碼 | VIX ≥ 28／32／36／40 → 正二 80／85／90／100% | VIX ≥ 35 → 85%；≥ 40 → 100% |
| 暫停條件 | 美國 BAA 利差 3 個月擴大超過 0.8 個百分點：恐慌加碼暫停（最多 30 個交易日）| — |
| 過熱調節 | 週 RSI > 80：正二調回 60% | 週 RSI > 75：正二調回 60% |

設計理由、回測對照與最大風險，請看各頁面上的「使用說明」。

### 功能

- 每個交易日自動更新燈號，美股盤中每小時更新 VIX。
- **你的持股**：輸入代號和股數，價格自動帶入，算出目前比例、今天燈號要買賣多少，以及這個月的錢怎麼分。還沒有持股的話，會告訴你第一次怎麼建立組合。
  - 台股：所有上市、上櫃股票和 ETF
  - 美股：任何代號
  - 歐股：歐洲各交易所約 15,000 檔股票和 ETF，可輸入代號或 ISIN。同一個代號對到好幾檔時（例如 SAN 可能是 Santander 或 Sanofi），會提示你加上交易所代碼。
- 持股只存在你自己的瀏覽器，不會上傳。
- 燈號改變時寄 Email 通知（自己架設時可開啟）。

### 自己架一份

1. Fork 這個 repo。
2. **GitHub Pages**：Settings → Pages → Source 選 *Deploy from a branch*，Branch `main`、資料夾 `/docs`。
3. **Actions 寫入權限**：Settings → Actions → General → Workflow permissions 選 *Read and write permissions*。
4. **FinMind token**（建議）：Settings → Secrets and variables → Actions → New repository secret，名稱 `FINMIND_TOKEN`。
5. **通知**（選用）：
   - 預設燈號改變時會開 GitHub Issue，GitHub 會寄信到你帳號的信箱。
   - Gmail 直接寄：新增 Secrets `MAIL_USERNAME`、`MAIL_PASSWORD`（Gmail 應用程式密碼，不是登入密碼）、`MAIL_TO`。
   - WhatsApp（CallMeBot）：新增 Secrets `WA_PHONE`、`WA_APIKEY`。

Secrets 加密保存，公開 repo 也看不到。請不要把 token、密碼寫進程式碼或網頁。

### 自動更新

| Workflow | 時間 | 做什麼 |
|---|---|---|
| `update.yml` | 台北時間週一到週五 20:50，加上美股盤中每小時 | `scripts/build_data.py`：抓 CBOE、FRED、FinMind、證交所／櫃買中心、Yahoo 的資料，計算燈號，更新 `docs/data.json`、`docs/us/data.json`、`docs/prices.json` |
| `eu.yml` | 歐洲收盤後（UTC 17:10）| `scripts/build_eu.py`：更新歐股價格 `docs/us/eu.json` 和美股名稱 `docs/us/usn.json` |

### 資料來源

CBOE（VIX）、FRED（利差）、FinMind（台股、美股價格）、臺灣證券交易所、櫃買中心、Yahoo Finance（歐股價格、匯率）。代號清單來自 [FinanceDatabase](https://github.com/JerBouma/FinanceDatabase)（MIT 授權）。

### 意見回饋

有問題或想法，歡迎到 [Discussions](https://github.com/salmonmisosoup/leverage-dashboard/discussions) 留言；發現錯誤請開 [Issue](https://github.com/salmonmisosoup/leverage-dashboard/issues)。

### 授權

MIT
