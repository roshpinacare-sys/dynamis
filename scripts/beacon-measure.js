// מגדלור-הכלכלה · גרסת-Actions (Node טהור · אפס-סודות · מדידה-ישירה-מהשרשרת)
// כותב receipts/economy/latest.json לספריית-הריצה · שדות-רץ-מקומי=null בכנות
const RPC = process.env.STEEM_RPC || "https://steemapi.boylikegirl.club";
const RPC2 = "https://api.justyy.com";
const FLEET = ["headcorner","hcsoldier1","hcsoldier2","hcsoldier3","hcsoldier4","hcsoldier5","hcsoldier6","israelnews","tov","haran","lsa","macrame","wic","wog","woq","cashmachine","siq"];

async function rpcOn(base, method, params) {
  try {
    const r = await fetch(base, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ jsonrpc: "2.0", id: 1, method, params }) });
    const j = await r.json();
    return j?.result ?? null;
  } catch { return null; }
}
const rpc = async (m, p) => (await rpcOn(RPC, m, p)) ?? (await rpcOn(RPC2, m, p));
const assetOf = (s) => (s || "").split(" ")[1] || "?";

(async () => {
  const gp = await rpc("condenser_api.get_dynamic_global_properties", []);
  if (!gp || !gp.head_block_number) { console.error("FAIL-CLOSED: chain-head-not-measured"); process.exit(2); }

  let liqSteem = 0, liqSbd = 0;
  const accts = await rpc("condenser_api.get_accounts", [FLEET]);
  for (const a of accts || []) if (a) { liqSteem += parseFloat(a.balance); liqSbd += parseFloat(a.sbd_balance); }

  let buys = 0, sells = 0, bookSteem = 0, bookSbd = 0;
  for (const a of FLEET) {
    const oo = await rpc("condenser_api.get_open_orders", [a]);
    for (const o of oo || []) {
      const sale = o.for_sale / 1000;
      if (assetOf(o.sell_price.base) === "SBD") { buys++; bookSbd += sale; } else { sells++; bookSteem += sale; }
    }
  }

  let price = null, spreadPct = null;
  const book = await rpc("condenser_api.get_order_book", [10]);
  if (book?.bids?.[0] && book?.asks?.[0]) {
    const bid = parseFloat(book.bids[0].real_price), ask = parseFloat(book.asks[0].real_price);
    price = Math.round(((bid + ask) / 2) * 1e9) / 1e9;
    spreadPct = Math.round(((ask - bid) / ((ask + bid) / 2)) * 10000) / 100;
  }

  const pendingConvert = [];
  for (const a of ["headcorner","hcsoldier1","hcsoldier2","hcsoldier3","hcsoldier4","hcsoldier5","hcsoldier6"]) {
    const conv = await rpc("condenser_api.get_conversion_requests", [a]);
    for (const c of conv || []) pendingConvert.push({ sbd: parseFloat(c.amount), maturesAt: c.conversion_date });
  }

  const payload = {
    at: new Date().toISOString(),
    kind: "sovereign-economy-live-beacon",
    source: "github-actions (10-min cadence · measures chain directly · zero secrets)",
    liveness: { headBlock: gp.head_block_number, chainTime: gp.time, note: "הבלוק-מתקדם-כל-3-ש' — אם-לא-זז-בין-ריצות השרשרת-קפאה" },
    liquid: { steem: Math.round(liqSteem * 1000) / 1000, sbd: Math.round(liqSbd * 1000) / 1000 },
    openOrders: { total: buys + sells, buys, sells, onBookSteem: Math.round(bookSteem * 1000) / 1000, onBookSbd: Math.round(bookSbd * 1000) / 1000 },
    market: { midPrice: price, spreadPct },
    protocolConvert: pendingConvert,
    runner: null,
    runnerNote: "מספרי-הרץ-המקומי מתעדכנים-מהסנדבוקס-במחזורים-הנמוכים-בתדירות (3/יום) — כאן-כנות-מלאה-על-מה-שנמדד-עכשיו",
    externalFlow: { counterparties: 7, paidToFleet: { sbd: 5.099, steem: 27.532 }, paidByFleet: { sbd: 2.802, steem: 47.923 }, measuredAt: "2026-11-17T15:45Z", receipt: "fill-probe-20261117T154524.txt" },
    honesty: { note: "כל-השדות החיים נמדדו-ישירות-מהשרשרת בריצה-זו · realizedSbd שלילי = מסחר-משמר-ערך, לא-רווח-ממומש", realizedSbd: null },
  };

  const fs = require("fs");
  fs.mkdirSync("receipts/economy", { recursive: true });
  fs.writeFileSync("receipts/economy/latest.json", JSON.stringify(payload, null, 2));
  console.log(`beacon-actions · block=${gp.head_block_number} · orders=${buys + sells}(${buys}/${sells}) · spread=${spreadPct}% · convert=${pendingConvert.length}`);
})();
