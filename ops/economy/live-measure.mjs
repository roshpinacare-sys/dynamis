// economy-live · מנוע-המדידה-הציבורי-החי · §62
// מודד-את-השרשרת-ואת-הרץ-בכל-ריצה · אפס-תלות (Node 22 fetch טהור) · אפס-סודות
// כל-המספרים-נמדדים-עכשיו — הקובץ-הציבורי לעולם-לא-ישן-יותר-מ-15-דקות.
import { readFileSync, writeFileSync, appendFileSync, mkdirSync } from "node:fs";

mkdirSync("receipts/economy", { recursive: true });

const FLEET = ["headcorner","hcsoldier1","hcsoldier2","hcsoldier3","hcsoldier4","hcsoldier5","hcsoldier6","israelnews","tov","haran","lsa","macrame","wic","wog","woq","cashmachine","siq"];
const FLEET_SET = new Set(FLEET);
const RPCS = ["https://steemapi.boylikegirl.club", "https://api.steemit.com"];
const now = () => new Date().toISOString();
const num = (s) => parseFloat(String(s));

async function rpc(method, params) {
  let lastErr = "no-rpc";
  for (const base of RPCS) {
    try {
      const r = await fetch(base, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ jsonrpc: "2.0", id: 1, method, params }),
        signal: AbortSignal.timeout(20000),
      });
      if (!r.ok) { lastErr = `${base} HTTP ${r.status}`; continue; }
      const j = await r.json();
      if (j.error) { lastErr = `${base} ${j.error.message || "rpc-error"}`; continue; }
      return { result: j.result, via: base };
    } catch (e) { lastErr = `${base} ${e.message}`; }
  }
  throw new Error(lastErr);
}

const flags = { accounts: false, orders: false, history: false, runner: false, feed: false };

// ── 1. יתרות-נזילות ──
let balances = {};
try {
  const { result } = await rpc("condenser_api.get_accounts", [FLEET]);
  for (const a of result) balances[a.name] = { steem: num(a.balance), sbd: num(a.sbd_balance) };
  flags.accounts = true;
} catch (e) { console.error("accounts-fail:", e.message); }

// ── 2. פקודות-פתוחות + ספר ──
// sell_price: base=min_to_receive (מה-שהוא-רוצה) · quote=amount_to_sell (מה-שהוא-נותן) — נמדד-ותוקן-ב-§62
let orders = [], book = { bid: null, ask: null, spreadPct: null };
try {
  for (const a of FLEET) {
    const { result } = await rpc("condenser_api.get_open_orders", [a]);
    for (const o of result) orders.push({ owner: a, ...o });
  }
  const buys = [], sells = [];
  for (const o of orders) {
    const base = o.sell_price.base, quote = o.sell_price.quote;
    const [bAmt, bAsset] = String(base).split(" "), [qAmt, qAsset] = String(quote).split(" ");
    if (bAsset === "SBD" && qAsset === "STEEM") buys.push(num(bAmt) / num(qAmt));   // נותן-SBD·רוצה-STEEM → קנייה (bid) = SBD/STEEM
    else if (bAsset === "STEEM" && qAsset === "SBD") sells.push(num(qAmt) / num(bAmt)); // נותן-STEEM·רוצה-SBD → מכירה (ask)
  }
  if (buys.length) book.bid = Math.max(...buys);
  if (sells.length) book.ask = Math.min(...sells);
  if (book.bid && book.ask && book.ask > book.bid) {
    const mid = (book.bid + book.ask) / 2;
    book.spreadPct = +(((book.ask - book.bid) / mid) * 100).toFixed(3);
  }
  flags.orders = true;
} catch (e) { console.error("orders-fail:", e.message); }

// ── 2b. ספר-השוק-המלא (כולל-חוץ) — עוגן-התאמה למדידה-המקומית ──
let market = { bid: null, ask: null, spreadPct: null };
try {
  const { result } = await rpc("condenser_api.get_order_book", [50]);
  const priceOf = (e) => {
    const b = e.order_price.base, q = e.order_price.quote;
    const [bA, bC] = String(b).split(" "), [qA, qC] = String(q).split(" ");
    if (bC === "SBD" && qC === "STEEM") return num(bA) / num(qA);
    if (bC === "STEEM" && qC === "SBD") return num(qA) / num(bA);
    return null;
  };
  const bids = (result.bids || []).map(priceOf).filter(v => v !== null);
  const asks = (result.asks || []).map(priceOf).filter(v => v !== null);
  if (bids.length) market.bid = Math.max(...bids);
  if (asks.length) market.ask = Math.min(...asks);
  if (market.bid && market.ask && market.ask > market.bid) {
    const mid = (market.bid + market.ask) / 2;
    market.spreadPct = +(((market.ask - market.bid) / mid) * 100).toFixed(3);
  }
} catch (e) { console.error("orderbook-fail:", e.message); }

// ── 3. היסטוריית-מילויים (דו-צדדי · ייחודי · פנימי/חוץ) ──
const fills = new Map();
const conversions = [];
let extFlows = new Map();
try {
  // פגינציה-אחורה-עד-כיסוי-4-ימים לכל-חשבון (מילויים+המרות-יחד); הפילוג-המסונן-לא-נתמך-בצמתים-הציבוריים (args==3 · נמדד)
  const coverUntil = Date.now() - 4 * 86400 * 1000;
  for (const a of FLEET) {
    let from = -1;
    for (let chunk = 0; chunk < 4; chunk++) {
      const { result } = await rpc("condenser_api.get_account_history", [a, from, 1000]);
      if (!result || !result.length) break;
      for (const [seq, ev] of result) {
        const [opName, op] = ev.op;
        if (opName === "fill_order") {
          const key = `${op.open_owner}|${op.open_seq}|${op.timestamp}|${op.current_owner}`;
          if (!fills.has(key)) fills.set(key, { ts: op.timestamp, open_owner: op.open_owner, current_owner: op.current_owner, open_pays: op.open_pays, current_pays: op.current_pays });
        }
        if (opName === "convert") {
          const mat = new Date(new Date(ev.timestamp).getTime() + 3.5 * 86400 * 1000).toISOString();
          if (new Date(mat) > new Date()) conversions.push({ owner: a, amount: op.amount, maturesAt: mat });
        }
      }
      const firstSeq = result[0][0], firstTs = new Date(result[0][1].timestamp).getTime();
      if (firstTs <= coverUntil || firstSeq <= 1) break;
      from = firstSeq - 1;
      await new Promise(res => setTimeout(res, 300));
    }
  }
  for (const f of fills.values()) {
    const internal = FLEET_SET.has(f.open_owner) && FLEET_SET.has(f.current_owner);
    if (internal) continue;
    const ext = FLEET_SET.has(f.open_owner) ? f.current_owner : f.open_owner;
    const extPays = FLEET_SET.has(f.open_owner) ? f.current_pays : f.open_pays;
    const extGets = FLEET_SET.has(f.open_owner) ? f.open_pays : f.current_pays;
    if (!extFlows.has(ext)) extFlows.set(ext, { fills: 0, paidSbd: 0, paidSteem: 0, gotSbd: 0, gotSteem: 0, last: f.ts });
    const rec = extFlows.get(ext);
    rec.fills++;
    if (f.ts > rec.last) rec.last = f.ts;
    const p = num(String(extPays).split(" ")[0]), g = num(String(extGets).split(" ")[0]);
    if (String(extPays).includes("SBD")) rec.paidSbd += p; else rec.paidSteem += p;
    if (String(extGets).includes("SBD")) rec.gotSbd += g; else rec.gotSteem += g;
  }
  flags.history = true;
} catch (e) { console.error("history-fail:", e.message); }

// ── 4. הרץ-החי — דופק-המנוע-בלבד (הצילום-הציבורי-הנדחף-ברציפות) ──
// grids/state/state.json-הציבורי ישן (נתפס-10-21) — אסור-להשתמש; הדופק-האמת = db/state-snapshot.json
// שהקיפר-דוחף-ברציפות + pushed_at-של-הריפו. רק-מה-שטרי-ציבורית-ומדוד — אפס-טענות-ממקורות-מתים.
let runner = null;
try {
  const r2 = await fetch("https://raw.githubusercontent.com/roshpinacare-sys/saos-dex/main/db/state-snapshot.json", { signal: AbortSignal.timeout(20000) });
  if (r2.ok) {
    const snap = await r2.json();
    const st = snap.state || {};
    runner = { heartbeatAt: snap.savedAt, height: st.height ?? null, source: "saos-dex db/state-snapshot.json (continuous keeper flush)" };
  }
  const r3 = await fetch("https://api.github.com/repos/roshpinacare-sys/saos-dex", { headers: { "User-Agent": "economy-live", Accept: "application/vnd.github+json" }, signal: AbortSignal.timeout(20000) });
  if (r3.ok) { const rj = await r3.json(); if (runner) runner.repoPushedAt = rj.pushed_at; }
  if (runner) flags.runner = true;
} catch (e) { console.error("runner-fail:", e.message); }

// ── 5. מחיר-פיד ──
let feed = null;
try {
  const { result } = await rpc("condenser_api.get_current_median_history_price", []);
  const b = num(String(result.base).split(" ")[0]), q = num(String(result.quote).split(" ")[0]);
  feed = { sbdPerSteem: +(q / b).toFixed(6), note: "base=SBD quote=STEEM ← median feed" };
  flags.feed = true;
} catch (e) { console.error("feed-fail:", e.message); }

// ── 6. הרכבת-הקבלה ──
const liquidSteem = Object.values(balances).reduce((s, b) => s + b.steem, 0);
const liquidSbd = Object.values(balances).reduce((s, b) => s + b.sbd, 0);
// הון-שנצבר-בפקודות = base (מה-שהבעלים-נותן-ונעול): קונה-נותן-SBD · מוכר-נותן-STEEM — הוכח-אמפירית-§62
const onBookSteem = orders.filter(o => String(o.sell_price.base).split(" ")[1] === "STEEM").reduce((s, o) => s + num(String(o.sell_price.base).split(" ")[0]), 0);
const onBookSbd = orders.filter(o => String(o.sell_price.base).split(" ")[1] === "SBD").reduce((s, o) => s + num(String(o.sell_price.base).split(" ")[0]), 0);

const cutoff24h = new Date(Date.now() - 86400 * 1000).toISOString();
const recent = [...fills.values()].filter(f => f.ts >= cutoff24h);
const recentExt = recent.filter(f => !(FLEET_SET.has(f.open_owner) && FLEET_SET.has(f.current_owner)));

const extList = [...extFlows.entries()].map(([cp, v]) => ({ counterparty: cp, fills: v.fills, paidSbd: +v.paidSbd.toFixed(3), paidSteem: +v.paidSteem.toFixed(3), gotSbd: +v.gotSbd.toFixed(3), gotSteem: +v.gotSteem.toFixed(3), last: v.last })).sort((a, b) => b.fills - a.fills);

const receipt = {
  schema: "economy-live/1",
  measuredAt: now(),
  freshness: { cadenceMinutes: 15, promise: "measured by the autonomous engine on every run — never a hand-pushed snapshot", nextRunNote: "keeper wakes this workflow if any run is >25 min stale" },
  flags, // אמת-לכל-מקור · false = מקור-נכשל-הריצה-הזו (fail-closed-כנה)
  fleetAccounts: FLEET.length,
  liquid: { steem: +liquidSteem.toFixed(3), sbd: +liquidSbd.toFixed(3) },
  onBook: { steem: +onBookSteem.toFixed(3), sbd: +onBookSbd.toFixed(3) },
  workingCapital: { steem: +(liquidSteem + onBookSteem).toFixed(3), sbd: +(liquidSbd + onBookSbd).toFixed(3) },
  openOrders: { total: orders.length },
  book: { bid: book.bid ? +book.bid.toFixed(6) : null, ask: book.ask ? +book.ask.toFixed(6) : null, spreadPct: book.spreadPct, note: "fleet-only top-of-book" },
  marketBook: { bid: market.bid ? +market.bid.toFixed(6) : null, ask: market.ask ? +market.ask.toFixed(6) : null, spreadPct: market.spreadPct, note: "whole-market top-of-book (get_order_book 50)" },
  fills: { window: "24h", unique: recent.length, external: recentExt.length, scannedTotal: fills.size },
  internalFillsAll: [...fills.values()].filter(f => FLEET_SET.has(f.open_owner) && FLEET_SET.has(f.current_owner)).length,
  externalFlows: { windowNote: "aggregated over the scanned history window (≈ last 4 days, backward pagination to coverage)", counterparties: extList.slice(0, 12), count: extList.length, totalPaidToFleetSbd: +extList.reduce((s, x) => s + x.paidSbd, 0).toFixed(3), totalPaidToFleetSteem: +extList.reduce((s, x) => s + x.paidSteem, 0).toFixed(3), totalPaidByFleetSbd: +extList.reduce((s, x) => s + x.gotSbd, 0).toFixed(3), totalPaidByFleetSteem: +extList.reduce((s, x) => s + x.gotSteem, 0).toFixed(3), latestExternalFill: extList.length ? extList.map(x => x.last).sort().pop() : null },
  conversions: conversions.length ? conversions : [],
  runner,
  feed,
  honesty: { note: "market-making preserves value and builds inventory; every number here is measured by this engine at measuredAt — nothing hand-curated", zeroFillsPolicy: "no fill is ever fabricated; the receipts ledger is the scoreboard", staleSourcesPolicy: "a source that stops updating is shown via flags=false or heartbeat age — never carried as a live claim" },
};

writeFileSync("receipts/economy/latest.json", JSON.stringify(receipt, null, 2) + "\n");

// ── 7. היסטוריה-ציבורית (שורה-קומפקטית-לריצה · תקרת-זיכרון-2016-שורות) ──
const histPath = "receipts/economy/history.jsonl";
let histLines = [];
try { histLines = readFileSync(histPath, "utf8").split("\n").filter(Boolean); } catch {}
histLines.push(JSON.stringify({ at: receipt.measuredAt, wc: receipt.workingCapital, orders: receipt.openOrders.total, spread: receipt.book.spreadPct, fills24: receipt.fills, extCount: receipt.externalFlows.count, runner: runner ? { asof: runner.asof, runCount: runner.runCount, realFills: runner.realFills } : null, flags }));
histLines = histLines.slice(-2016);
writeFileSync(histPath, histLines.join("\n") + "\n");

console.log(`economy-live measured at ${receipt.measuredAt}`);
console.log(`wc=${receipt.workingCapital.steem} STEEM + ${receipt.workingCapital.sbd} SBD · orders=${orders.length} · ext=${extList.length} · flags=${JSON.stringify(flags)}`);
if (!flags.accounts || !flags.history) { console.error("PARTIAL-MEASURE — receipt carries honest flags"); }
