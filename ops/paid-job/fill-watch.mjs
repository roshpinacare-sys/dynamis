#!/usr/bin/env node
/* fill-watch.mjs — §52 · צופה-המילוי-החוץ · מדידה-שעתית-של-דולר-חי-ברשת-הקבלה
 * ═════════════════════════════════════════════════════════════════════════════
 * סורק-36-כתובות-קבלה (12×EVM על-Base+ETH · 12×TRON · 12×SOL) ליתרות-USDC/USDT
 * → מגיש-קבלה-ציבורית (receipts/fill/latest.json) → אם-נמצא-מילוי: פותח-אישיו-הכרזה.
 * Node-22-טהור · אפס-תלויות · אפס-מפתחות (קריאה-ציבורית-בלבד).
 */
import { execFileSync } from "node:child_process";
import { mkdirSync, writeFileSync, readFileSync, appendFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const RPC_BASE = "https://base-rpc.publicnode.com";
const RPC_ETH = "https://ethereum-rpc.publicnode.com";
const USDC_BASE = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913";
const USDC_ETH = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48";
const USDT_TRC20_HEX = "41A614F803B6FD7CA98DF2D7C48F9101B2E1FBB7F";
const USDT_SOL_MINT = "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB";

const AGENTS = [
  { name: "headcorner", evm: "0x2767e8146c11baD1d9B0784f11325375195c1b0f", tron: "TG6SrsMJjRqnqAyYM8kGZu1rgkpsgizKEn", sol: "9knfnFMLmhUNjKRDbR1BmVnVkq4BRczyYjJ7BqiZSgiL" },
  { name: "cashmachine", evm: "0x0FB6C1807d8D7945B5E3a14ea3679e19795cb545", tron: "TT7whWFon5EdDVFUBUUP9EY6y3VCtL7Bre", sol: "HBBdhpbpFP3BwqcvrxJ44hAyKSid3D6AB4SFvtrN736s" },
  { name: "haran", evm: "0xdB073ae7De5fD56e635C1aAD97599892b3288C42", tron: "TMaxNtRVdBmXyQUdsHFRaAm1jPpFAG9d7K", sol: "Fy3yhHVQ7et1bVV9gBsoK6BNHhTXbn478Wfyf1QA7zdU" },
  { name: "israelnews", evm: "0x4702Ed075a368023A26BDc651D0eC282c8Aa4E84", tron: "TQErSnQCdTTtL3Tf8KiX2FxFhbhYQCDx3F", sol: "7j3CcQwHxtZPP22eE97CoWMvZd7rdkQgcDwaYiZeA4Cj" },
  { name: "lsa", evm: "0x505BbaA179827A1759b2875d50806eb7933E9add", tron: "TJ57aAHB44NiwT8up5y7P3Fcfko6vbcbYK", sol: "Edfokgh7rkCp421R6VgGfMWMwTDzzaBB2UG3sNaswpki" },
  { name: "macrame", evm: "0x174465Ded517d129CC6B7424671Da8C181413A55", tron: "TJg2YiPuczmz72nJq5tmT2vrod5BDgZDmS", sol: "7n7hEERGWuLUL6juDmzVespteQVSepXHjTGLLFFEjwu" },
  { name: "siq", evm: "0xc2bF134836c93a1B88da025639609882cB67368b", tron: "TNgaDWYknRz46deiLkXdUXhn3gjcobnxhE", sol: "2auNobnA9YBbsMVTxyBEEHS9QCYYNLtM2FHax5NsD7p8" },
  { name: "tov", evm: "0x0eBb322CE1E54738ccAD27F524754AD859677360", tron: "TL7EvaXWtYQwuQdEDpkgGJCryY8t5PRzwH", sol: "AGfuexrFc6S9eSrnTfn4NHn34p5nLfPBnMV4S6r2uUjX" },
  { name: "wic", evm: "0x004085135371bd271345daB84bc8bE8B677d1733", tron: "TBR2ffp74mp9oUinrA4BbjKKTttFr5Ng2u", sol: "CY7FEenVet8v8ZMB9JxvphtBhQZeVFRRUq9tzVKCSEbJ" },
  { name: "wog", evm: "0x9b47dB08Fc1bc552856A69872d0a15486447c5Cb", tron: "TLDEWjWWyTCWrtaEk9CmJG68NgPMjKLuZp", sol: "8SGkrAjepscF3ttD5UzxyFwX8DgREUBD3cjNe5ZEmnCk" },
  { name: "woq", evm: "0x9978ab0F642bBf0b75E92db0E639EE863e053aC4", tron: "TDCXLokdY1PGjKEMtWG7we9Dt8279hF46m", sol: "8tPSpQ91n9Z4Vr3wsmpdnDfUbNNWYwUxDrupWS8hDdCM" },
  { name: "ynet", evm: "0xd1e528b99632dA73De8BB494b76644273c9433B8", tron: "TVESRr1TX1RaKzsN6TKszutJBFDPEGPx1e", sol: "3aU9a8ghqe6dUUtot8rNafFVpASH9jxbxRc1GfKkNKrB" },
];

const sleep = (ms) => new Promise(r => setTimeout(r, ms));

async function evmBalance(rpc, token, holder) {
  const r = await fetch(rpc, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ jsonrpc: "2.0", id: 1, method: "eth_call", params: [{ to: token, data: "0x70a08231" + holder.toLowerCase().replace(/^0x/, "").padStart(64, "0") }, "latest"] }),
    signal: AbortSignal.timeout(15000),
  });
  const j = await r.json();
  return Number(BigInt(j.result ?? "0x0")) / 1e6;
}

function tronHex(addr) {
  const B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz";
  let n = 0n;
  for (const c of addr) { const i = B58.indexOf(c); if (i < 0) return null; n = n * 58n + BigInt(i); }
  let h = n.toString(16); if (h.length % 2) h = "0" + h;
  return h.startsWith("41") ? h.slice(0, 42) : null;
}

async function tronUsdt(addr) {
  const hex = tronHex(addr);
  if (!hex) return 0;
  const r = await fetch("https://api.trongrid.io/wallet/triggerconstantcontract", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ owner_address: hex, contract_address: USDT_TRC20_HEX, function_selector: "balanceOf(address)", parameter: hex.slice(2).padStart(64, "0"), visible: false }),
    signal: AbortSignal.timeout(15000),
  });
  const j = await r.json();
  const raw = j.constant_result?.[0];
  return raw ? Number(BigInt("0x" + raw)) / 1e6 : 0;
}

async function solUsdt(addr) {
  const r = await fetch("https://api.mainnet-beta.solana.com", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ jsonrpc: "2.0", id: 1, method: "getTokenAccountsByOwner", params: [addr, { mint: USDT_SOL_MINT }, { encoding: "jsonParsed" }] }),
    signal: AbortSignal.timeout(15000),
  });
  const j = await r.json();
  let t = 0;
  for (const a of j.result?.value ?? []) t += a.account.data.parsed.info.tokenAmount.uiAmount ?? 0;
  return t;
}

function gh(method, path, body) {
  const args = ["api", "--method", method, path];
  if (body) args.push("--input", "-");
  return JSON.parse(execFileSync("gh", args, {
    input: body ? JSON.stringify(body) : "",
    env: { ...process.env, GH_TOKEN: process.env.GH_TOKEN },
    encoding: "utf8", timeout: 30000,
  }).toString() || "null");
}

async function main() {
  const at = new Date().toISOString();
  const balances = [];
  const errors = [];
  for (const a of AGENTS) {
    for (const [chain, rpc, token] of [["base", RPC_BASE, USDC_BASE], ["ethereum", RPC_ETH, USDC_ETH]]) {
      try { const v = await evmBalance(rpc, token, a.evm); if (v > 0) balances.push({ chain, agent: a.name, symbol: "USDC", amount: v }); }
      catch (e) { errors.push(`${chain}/${a.name}:${String(e.message).slice(0, 40)}`); }
      await sleep(90);
    }
    try { const v = await tronUsdt(a.tron); if (v > 0) balances.push({ chain: "tron", agent: a.name, symbol: "USDT", amount: v }); } catch { errors.push(`tron/${a.name}`); }
    await sleep(120);
    try { const v = await solUsdt(a.sol); if (v > 0) balances.push({ chain: "solana", agent: a.name, symbol: "USDT", amount: v }); } catch { errors.push(`sol/${a.name}`); }
    await sleep(120);
  }
  const totalUsd = Math.round(balances.reduce((s, b) => s + b.amount, 0) * 1e4) / 1e4;

  // קבלה-ציבורית
  const receipt = {
    at, protocol: "fill-watch v1 · §52", totalUsd, balances, errors: errors.slice(0, 10),
    scanned: { evmBase: AGENTS.length, evmEth: AGENTS.length, tron: AGENTS.length, sol: AGENTS.length },
    reception: { baseUsdc: AGENTS[0].evm, note: "wallets-public digest 4442c2b9 · 12 agents × 10 chains" },
  };
  const dir = join(HERE, "..", "..", "receipts", "fill");
  mkdirSync(dir, { recursive: true });
  writeFileSync(join(dir, "latest.json"), JSON.stringify(receipt, null, 1));
  console.log(`[fill-watch] total=$${totalUsd} · balances=${balances.length} · errors=${errors.length}`);

  // היסטוריה (מדלגים-אם-אין-שינוי — דה-דופליקציה)
  const histPath = join(dir, "history.jsonl");
  let prevTotal = -1;
  try {
    const lines = readFileSync(histPath, "utf8").trim().split("\n").filter(Boolean);
    prevTotal = JSON.parse(lines[lines.length - 1]).totalUsd;
  } catch { /* ראשון */ }
  if (prevTotal !== totalUsd) {
    appendFileSync(histPath, JSON.stringify({ at, totalUsd, balances: balances.length }) + "\n");
    if (totalUsd > 0 && prevTotal !== totalUsd) {
      // מילוי-חוץ-חדש/משתנה — הכרזה-ציבורית-חיה
      const title = `EXTERNAL-DOLLAR-FILL · $${totalUsd.toFixed(4)} נמדד-על-השרשרת`;
      const body = [
        "## 🟢 מילוי-חוץ-דולרי — נמדד-אוטומטית על-ידי צופה-המילוי",
        "",
        `- **סה״כ:** $${totalUsd.toFixed(4)}`,
        `- **מועד-מדידה:** ${at}`,
        ...balances.map(b => `- ${b.chain}/${b.agent}: ${b.amount} ${b.symbol} (\`${b.amount.toFixed(4)}$\`)`),
        "",
        "המילוי-נמדד-מול-השרשרות-הציבוריות (Base/ETH-TRON-SOL) בכתובות-הקבלה-הקנוניות של-הרשת-הריבונית.",
      ].join("\n");
      try { gh("POST", `/repos/${process.env.GITHUB_REPOSITORY}/issues`, { title, body, labels: ["external-fill"] }); console.log("[fill-watch] ANNOUNCED issue"); }
      catch (e) { console.log("[fill-watch] announce-failed (כנות):", String(e.message).slice(0, 80)); }
    }
  }
}
main().catch(e => { console.error("[fill-watch] FATAL", e.message); process.exit(1); });
