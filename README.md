# 正二加碼儀表板 · Leveraged ETF Signal Dashboard

用回測過的規則，每個交易日告訴你：什麼時候把子彈轉成正二（加碼），什麼時候把漲多的正二調回基準（補子彈）。輸入自己的持股，還會直接算出要買賣哪幾檔、幾股。

A free dashboard that tells you, every trading day, when to add to a 2x Nasdaq (or Taiwan) ETF position and when to trim it back — using rules backtested over 1990–2026. Enter your holdings and it works out what to buy or sell.

**👉 開啟儀表板 / Open the dashboard**

| | 網址 / Link | 適合 / For |
|---|---|---|
| **納指版 Nasdaq** | https://salmonmisosoup.github.io/leverage-dashboard/us/ | 美股 QLD＋SGOV，或歐洲 LQQ＋IB01；中英切換 · US or EU investors, English/中文 |
| **雙市場版 Taiwan + US** | https://salmonmisosoup.github.io/leverage-dashboard/ | 台股 00685L＋美股 00830（台灣券商可買） |

![Nasdaq dashboard](docs/img/us-en.png)

> ⚠️ 這是依歷史回測整理的規則提示，不是投資建議。槓桿 ETF 在長期熊市中可能大幅虧損（回測最大回檔 −85% 左右），請依自身資金與風險承受度決定。
> This is a rules-based signal from historical backtests, not investment advice. Leveraged ETFs can lose most of their value in a long bear market (backtested max drawdown around −85%).

## 規則摘要 · Rules

| | 台股 Taiwan | 美股 US (Nasdaq) |
|---|---|---|
| 基準 Base | 00685L 60%／00713 40% | 2x 60%／T-bills 40% |
| 中期回調 Pullback | 收盤在季線下方：當月薪資全買正二 | Close below 60-day MA: all new money into 2x |
| 恐慌加碼 Panic buy | VIX ≥ 28／32／36／40 → 正二 80／85／90／100% | VIX ≥ 35 → 85%; ≥ 40 → 100% |
| 暫停 Pause | BAA 利差 3 個月擴大 > 0.8 個百分點：恐慌加碼暫停（最多 30 個交易日） | — |
| 過熱調節 Trim | 週 RSI > 80：正二調回 60% | Weekly RSI > 75: trim 2x back to 60% |

設計理由、回測對照與最大風險，請看頁面上的「使用說明」。Design notes, backtest comparisons and risks are in **How to use** on the page.

## 功能 · Features

- 每個交易日自動更新燈號，盤中 VIX 每小時更新 · Signals update daily; intraday VIX hourly
- 「你的持股」：輸入代號和股數，自動帶入價格，算出目前比例和要買賣多少 · Holdings: auto prices, current mix, exact trades
  - 台股：所有上市、上櫃股票和 ETF · All TWSE/TPEx stocks and ETFs
  - 美股：任何代號 · Any US ticker
  - 歐股：歐洲各交易所約 15,000 檔股票和 ETF，可輸入代號或 ISIN · ~15,000 European stocks and ETFs, by ticker or ISIN
- 持股只存在你自己的瀏覽器，不會上傳 · Holdings stay in your browser; nothing is uploaded
- 燈號改變時寄 Email 通知（自己架設時可開啟）· Email alerts when a signal changes (when self-hosted)

## 自己架一份 · Run your own copy

1. Fork 這個 repo。
2. **GitHub Pages**：Settings → Pages → Source 選 *Deploy from a branch*，Branch `main`、資料夾 `/docs`。
3. **Actions 寫入權限**：Settings → Actions → General → Workflow permissions 選 *Read and write permissions*。
4. **FinMind token**（建議）：Settings → Secrets and variables → Actions → New repository secret，名稱 `FINMIND_TOKEN`。
5. **通知**（選用）：
   - 預設燈號改變時會開 GitHub Issue，GitHub 會寄信到帳號信箱。
   - Gmail 直接寄：新增 Secrets `MAIL_USERNAME`、`MAIL_PASSWORD`（Gmail 應用程式密碼）、`MAIL_TO`。
   - WhatsApp（CallMeBot）：新增 Secrets `WA_PHONE`、`WA_APIKEY`。

Secrets 加密保存，公開 repo 也看不到。請不要把 token、密碼寫進程式碼或網頁。

### 自動更新 · Schedules

| Workflow | 時間 | 做什麼 |
|---|---|---|
| `update.yml` | 台北時間週一到週五 20:50，加上美股盤中每小時 | `scripts/build_data.py`：抓 CBOE、FRED、FinMind、台灣證交所／櫃買中心、Yahoo，計算燈號，更新 `docs/data.json`、`docs/us/data.json`、`docs/prices.json` |
| `eu.yml` | 歐洲收盤後（UTC 17:10）| `scripts/build_eu.py`：更新歐股價格 `docs/us/eu.json` |

## 資料來源 · Data sources

CBOE（VIX）、FRED（利差）、FinMind（台股、美股）、臺灣證券交易所、櫃買中心、Yahoo Finance（歐股、匯率）。歐股代號清單來自 [FinanceDatabase](https://github.com/JerBouma/FinanceDatabase)（MIT）。

## 意見回饋 · Feedback

有問題或想法，歡迎到 [Discussions](https://github.com/salmonmisosoup/leverage-dashboard/discussions) 留言，發現錯誤請開 [Issue](https://github.com/salmonmisosoup/leverage-dashboard/issues)。
Questions and ideas welcome in Discussions; bugs in Issues.

## 授權 · License

MIT
