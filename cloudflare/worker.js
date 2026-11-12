// 儀表板「打開／重整時」抓即時報價用的小型轉接程式（部署在你自己的 Cloudflare Workers 免費帳號）
// 只在有人打開網頁時才抓，不做背景輪詢；只抓下面三個固定網址，不是公開代理。
// 同一份結果快取 30 秒，避免短時間內重複向資料來源要資料。
const ORIGINS = ["https://salmonmisosoup.github.io"];
const UA = { "User-Agent": "Mozilla/5.0 (compatible; leverage-dashboard/1.0)" };

const num = x => { const v = parseFloat(String(x ?? "").replace(/,/g, "")); return v > 0 ? v : null; };

async function twVix() {
  const r = await fetch("https://mis.taifex.com.tw/futures/api/getQuoteListVIX", {
    method: "POST", headers: { ...UA, "Content-Type": "application/json" }, body: "{}" });
  const q = (await r.json()).RtData.QuoteList[0]; const d = String(q.CDate || "");
  return { tw_vix: num(q.CLastPrice), tw_hi: num(q.CHighPrice), tw_t: String(q.CTime || "").slice(0, 4),
           tw_d: d.length >= 8 ? `${d.slice(0, 4)}-${d.slice(4, 6)}-${d.slice(6, 8)}` : null };
}
async function taiex() {
  const r = await fetch("https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch=tse_t00.tw&json=1&delay=0", { headers: UA });
  const t = await r.text(); const m = JSON.parse(t.slice(t.indexOf("{"))).msgArray[0]; const d = String(m.d || "");
  return { taiex: num(m.z) || num(m.y), taiex_t: String(m.t || "").slice(0, 5), taiex_d: d.length >= 8 ? `${d.slice(0, 4)}-${d.slice(4, 6)}-${d.slice(6, 8)}` : null };
}
async function usVix() {
  const r = await fetch("https://cdn-api.cboe.com/api/global/delayed_quotes/quotes/_VIX.json", { headers: UA });
  const q = (await r.json()).data;
  return { us_vix: num(q.current_price), us_hi: num(q.high), us_t: String(q.last_trade_time || "").slice(0, 16) };
}

export default {
  async fetch(req, env, ctx) {
    const origin = req.headers.get("Origin") || "";
    const cors = { "Access-Control-Allow-Origin": ORIGINS.includes(origin) ? origin : ORIGINS[0], "Vary": "Origin" };
    if (req.method === "OPTIONS") return new Response(null, { headers: { ...cors, "Access-Control-Allow-Methods": "GET" } });
    const cache = caches.default; const key = new Request("https://cache.local/live");
    let res = await cache.match(key);
    if (!res) {
      const out = { t: new Date(Date.now() + 8 * 3600e3).toISOString().replace("T", " ").slice(0, 19) };
      for (const [name, f] of [["tw", twVix], ["taiex", taiex], ["us", usVix]]) {
        try { Object.assign(out, await f()); } catch (e) { out[name + "_err"] = String(e).slice(0, 80); }
      }
      res = new Response(JSON.stringify(out), { headers: { "Content-Type": "application/json", "Cache-Control": "max-age=30" } });
      ctx.waitUntil(cache.put(key, res.clone()));
    }
    const h = new Headers(res.headers); for (const [k, v] of Object.entries(cors)) h.set(k, v);
    return new Response(res.body, { headers: h });
  }
};
