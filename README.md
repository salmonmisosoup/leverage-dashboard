# 正二加碼儀表板

用回測過的規則，每個交易日告訴你兩件事：什麼時候把子彈轉成正二（加碼），什麼時候把漲多的正二調回基準（補子彈）。

- **雙市場版**（台股 00685L＋美股 QLD）：`https://<你的帳號>.github.io/<repo 名稱>/`
- **納指版**（美股 QLD／SGOV，含中英切換與歐洲替代標的）：`https://<你的帳號>.github.io/<repo 名稱>/us/`

> ⚠️ 這是依歷史回測整理的規則提示，不是投資建議。槓桿 ETF 在長期熊市中可能大幅虧損（回測最大回檔 −77% 到 −87%），請依自身資金與風險承受度決定。

## 規則摘要

| | 台股 | 美股 |
|---|---|---|
| 基準 | 00685L 60%／00713 40% | QLD 60%／SGOV 40% |
| 中期回調 | 收盤在季線下方：當月薪資全買正二 | 同左 |
| 恐慌加碼 | VIX ≥ 28／32／36／40 → 正二 80／85／90／100% | VIX ≥ 35 → 85%；≥ 40 → 100% |
| 暫停條件 | 美國 BAA 利差 3 個月擴大 > 0.8 個百分點：恐慌加碼暫停（最多 30 個交易日） | — |
| 過熱調節 | 週 RSI > 80：正二調回 60% | 週 RSI > 75：正二調回 60% |

完整的設計理由、回測對照與最大風險，請看頁面上的「使用說明」。

## 自動更新

`.github/workflows/update.yml` 會在台北時間週一到週五 20:50 執行 `scripts/build_data.py`，抓取 CBOE、FRED、FinMind、CNN 恐懼貪婪（GitHub）與 Siblis 的資料，更新 `docs/data.json` 與 `docs/us/data.json` 並提交。也可以在 Actions 頁面按 **Run workflow** 手動執行。

## 設定步驟

1. **開啟 GitHub Pages**：Settings → Pages → Source 選 *Deploy from a branch*，Branch 選 `main`、資料夾選 `/docs`。
2. **允許 Actions 寫入**：Settings → Actions → General → Workflow permissions 選 *Read and write permissions*。
3. **FinMind token**（建議，避免免費額度不足）：Settings → Secrets and variables → Actions → New repository secret，名稱 `FINMIND_TOKEN`。
4. **通知**（燈號改變時）：
   - 預設會開一個 GitHub Issue，GitHub 會寄 Email 到你帳號的信箱，不需要設定。
   - **Email 直接寄到指定信箱**（選用，Gmail）：新增 Secrets `MAIL_USERNAME`（寄件 Gmail）、`MAIL_PASSWORD`（Gmail 的應用程式密碼，不是登入密碼）、`MAIL_TO`（收件信箱）。
   - **WhatsApp**（選用，CallMeBot 免費服務）：依 https://www.callmebot.com/blog/free-api-whatsapp-messages/ 取得 API key，新增 Secrets `WA_PHONE`（含國碼，例如 `+8869xxxxxxxx`）、`WA_APIKEY`。

Secrets 加密保存，公開 repo 也不會被看到。請不要把 token、密碼寫進程式碼或網頁。

## 隱私

在頁面計算器輸入的持股市值，只存在你自己瀏覽器的本機儲存空間，不會上傳到任何地方。

## 授權

MIT
