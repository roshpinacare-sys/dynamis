#!/usr/bin/env node
/* verify-and-work.mjs — §52 · THE PUBLIC MONEY DOOR · מבצע-העבודה-הבתשלום
 * ═════════════════════════════════════════════════════════════════════════════
 * אישיו-חדש-עם-תבנית-paid_job → אימות-התשלום מול-Base (USDC-Transfer-לכתובת-הקבלה)
 * → אם-אומת: ביצוע-העבודה במנוע-ה-NIM → פרסום-התוצר-כתגובה + קבלה-ציבורית.
 * חוק-ברזל: fail-closed — תשלום-לא-מאומת = אין-עבודה. אפס-סודות-בפלט.
 * Node-22 טהור · אפס-תלויות.
 */
import { execFileSync } from "node:child_process";

const RPCS_BASE = ["https://mainnet.base.org", "https://base-rpc.publicnode.com"];
const USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913";
const TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef";
const RECEPTION_EVM = [
  "0x2767e8146c11baD1d9B0784f11325375195c1b0f", // headcorner — הקנוני
  "0x0FB6C1807d8D7945B5E3a14ea3679e19795cb545", "0xdB073ae7De5fD56e635C1aAD97599892b3288C42",
  "0x4702Ed075a368023A26BDc651D0eC282c8Aa4E84", "0x505BbaA179827A1759b2875d50806eb7933E9add",
  "0x174465Ded517d129CC6B7424671Da8C181413A55", "0xc2bF134836c93a1B88da025639609882cB67368b",
  "0x0eBb322CE1E54738ccAD27F524754AD859677360", "0x004085135371bd271345daB84bc8bE8B677d1733",
  "0x9b47dB08Fc1bc552856A69872d0a15486447c5Cb", "0x9978ab0F642bBf0b75E92db0E639EE863e053aC4",
  "0xd1e528b99632dA73De8BB494b76644273c9433B8",
];
const TIERS = {
  micro: { usd: 0.5, maxChars: 600, note: "micro" },
  standard: { usd: 2.0, maxChars: 2500, note: "standard" },
  deep: { usd: 5.0, maxChars: 10000, note: "deep" },
};

function parseField(body, id) {
  const re = new RegExp(`### ${id}\\s*\\n+([\\s\\S]*?)(?:\\n### |$)`, "i");
  const m = String(body ?? "").match(re);
  return m ? m[1].trim() : null;
}

async function rpcAny(method, params) {
  let lastErr = null;
  for (const url of RPCS_BASE) {
    try {
      const r = await fetch(url, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ jsonrpc: "2.0", id: 1, method, params }),
        signal: AbortSignal.timeout(20000),
      });
      const j = await r.json();
      if (j.error) { lastErr = "rpc:" + j.error.message; continue; }
      return { result: j.result, via: url };
    } catch (e) { lastErr = String(e.message).slice(0, 60); }
  }
  throw new Error(lastErr ?? "all-rpcs-failed");
}

function addrToTopic(a) { return "0x" + a.toLowerCase().replace(/^0x/, "").padStart(64, "0"); }

async function verifyBaseUsdc(txid) {
  let rc = null;
  try {
    const got = await rpcAny("eth_getTransactionReceipt", [txid]);
    rc = got.result;
  } catch (e) {
    return { ok: false, reason: "tx-not-verifiable-on-base (" + String(e.message).slice(0, 60) + ")" };
  }
  if (!rc || !rc.logs) return { ok: false, reason: "tx-not-found-on-base" };
  if (rc.status !== "0x1") return { ok: false, reason: "tx-reverted" };
  for (const lg of rc.logs) {
    if (String(lg.address).toLowerCase() !== USDC.toLowerCase()) continue;
    if (String(lg.topics?.[0]).toLowerCase() !== TRANSFER_TOPIC) continue;
    const to = "0x" + String(lg.topics[2]).slice(-40);
    const hit = RECEPTION_EVM.find(a => a.toLowerCase() === to.toLowerCase());
    if (!hit) continue;
    const amount = Number(BigInt(lg.data)) / 1e6;
    return { ok: true, amount, to, txid, block: parseInt(rc.blockNumber, 16) };
  }
  return { ok: false, reason: "no-usdc-transfer-to-reception-network-in-tx" };
}

// §54 · בחירת-מודל-לפי-מדרגה (נמדד-חי: 33-מודלים-זמינים):
// micro = מודל-ישיר-מהיר (ההבטחה-בדף-המוצר: "direct") · standard = מאוזן ·
// deep = חשיבה-מלאה. דריסה-בסביבה נשמרת (NIM_MODEL לכל-הרמות או פר-רמה).
function pickModel(tierId) {
  if (process.env.NIM_MODEL) return process.env.NIM_MODEL;
  if (tierId === "micro") return process.env.NIM_MODEL_MICRO || "google/gemma-4-31b-it";
  if (tierId === "deep") return process.env.NIM_MODEL_DEEP || "nvidia/nemotron-3.5-lightning-30b-a3b";
  return process.env.NIM_MODEL_STANDARD || "nvidia/nemotron-3.5-lightning-30b-a3b";
}

async function nimWork(prompt, tierId) {
  const base = process.env.NVIDIA_BASE_URL || "https://integrate.api.nvidia.com/v1";
  const key = process.env.NVIDIA_NIM_KEY || process.env.NVIDIA_API_KEY || process.env.NIM_API_KEY;
  if (!key) throw new Error("nim-key-missing (fail-closed)");
  const model = pickModel(tierId);
  const r = await fetch(base.replace(/\/$/, "") + "/chat/completions", {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: "Bearer " + key },
    body: JSON.stringify({
      model,
      messages: [
        { role: "system", content: "You are SAOS Sovereign AI — a paid, frontier-grade work engine. Answer precisely, truthfully, completely. No filler." },
        { role: "user", content: prompt },
      ],
      max_tokens: tierId === "deep" ? 2600 : tierId === "standard" ? 1600 : 700,
      temperature: 0.4,
    }),
    signal: AbortSignal.timeout(120000),
  });
  const j = await r.json();
  // §54 לכידת-באג-מוצר (נתפס-בדוגמה-החיה): מודלי-חשיבה מחזירים-לפעמים content=null
  // ואת-העבודה ב-reasoning_content — בלי-נפילה-חזרה לקוח-משלם-היה-מקבל-כישלון.
  const msg = j.choices?.[0]?.message;
  const work = msg?.content ?? msg?.reasoning_content;
  if (!work || !String(work).trim()) throw new Error("nim-empty-completion http=" + r.status);
  return { work, model };
}

function gh(method, path, body) {
  const args = ["api", "--method", method, path];
  if (body) args.push("--input", "-");
  const out = execFileSync("gh", args, {
    input: body ? JSON.stringify(body) : "",
    env: { ...process.env, GH_TOKEN: process.env.GH_TOKEN, GH_HOST: "github.com" },
    encoding: "utf8", timeout: 30000,
  }).toString();
  return out ? JSON.parse(out) : null;
}

async function main() {
  const issueNum = process.env.ISSUE_NUMBER;
  const repo = process.env.GITHUB_REPOSITORY;
  const issue = gh("GET", `/repos/${repo}/issues/${issueNum}`);
  const txid = parseField(issue.body, "Payment txid \\(Base network\\)") || parseField(issue.body, "Payment txid (Base network)");
  const tierRaw = parseField(issue.body, "Tier — מדרגת-העבודה") || parseField(issue.body, "Tier — מדרגת-העבודה") || "";
  const prompt = parseField(issue.body, "Prompt — העבודה המבוקשת") || "";
  const callback = parseField(issue.body, "Callback URL \\(optional\\)") || null;
  const tierId = /micro/i.test(tierRaw) ? "micro" : /standard/i.test(tierRaw) ? "standard" : /deep/i.test(tierRaw) ? "deep" : null;
  const tier = TIERS[tierId];

  console.log(`[door] issue #${issueNum} · tier=${tierId} · txid=${txid?.slice(0, 18)}… · prompt=${prompt.length}B`);

  if (!txid || !tier || !prompt.trim()) {
    gh("POST", `/repos/${repo}/issues/${issueNum}/comments`, { body: "**דחייה-כנה (fail-closed):** חסרים-שדות-חובה (txid/tier/prompt). מלא-מחדש-לפי-התבנית." });
    return;
  }
  if (prompt.length > tier.maxChars) {
    gh("POST", `/repos/${repo}/issues/${issueNum}/comments`, { body: `**דחייה:** ה-prompt (${prompt.length} תווים) חורג-מהמדרגה (מקסימום ${tier.maxChars}).` });
    return;
  }

  // ── אימות-התשלום מול-השרשרת (Base) ──
  const v = await verifyBaseUsdc(txid).catch(e => ({ ok: false, reason: "verify-error:" + e.message }));
  if (!v.ok) {
    gh("POST", `/repos/${repo}/issues/${issueNum}/comments`, { body: `**תשלום-לא-אומת — fail-closed.** סיבה: \`${v.reason}\`. ה-txid נבדק-מול-Base-הציבורי (USDC → רשת-הקבלה). אין-עבודה-בלי-תשלום-מאומת.` });
    gh("PATCH", `/repos/${repo}/issues/${issueNum}`, { state: "closed", labels: [...(issue.labels?.map(l => l.name) ?? []), "payment-rejected"] });
    return;
  }
  if (v.amount < tier.usd) {
    gh("POST", `/repos/${repo}/issues/${issueNum}/comments`, { body: `**תשלום-חלקי:** שולם $${v.amount.toFixed(2)} · נדרש $${tier.usd.toFixed(2)} (${tierId}). fail-closed.` });
    gh("PATCH", `/repos/${repo}/issues/${issueNum}`, { state: "closed", labels: [...(issue.labels?.map(l => l.name) ?? []), "payment-underpaid"] });
    return;
  }

  // ── התשלום-אומת → ביצוע-העבודה ──
  let out;
  try {
    out = await nimWork(prompt, tierId);
  } catch (e) {
    gh("POST", `/repos/${repo}/issues/${issueNum}/comments`, { body: `**התשלום-אומת (txid \`${txid.slice(0, 18)}…\` · $${v.amount.toFixed(2)}) — אך-ביצוע-העבודה-נכשל-זמנית** (\`${String(e.message).slice(0, 120)}\`). האישיו-נשאר-פתוח-והמנוע-ינסה-שוב. הכסף-לא-ילך-לאיבוד.` });
    return;
  }

  const receipt = [
    "## ✅ SOVEREIGN AI WORK — קבלה-ציבורית",
    "",
    `- **תשלום:** $${v.amount.toFixed(2)} USDC (Base) · txid \`${txid}\` · block ${v.block}`,
    `- **יעד:** \`${v.to}\` (כתובת-קבלה-ריבונית)`,
    `- **מדרגה:** ${tierId} ($${tier.usd.toFixed(2)})`,
    `- **מנוע:** ${out.model}`,
    `- **מועד:** ${new Date().toISOString()}`,
    "",
    "---",
    "",
    out.work,
  ].join("\n");
  gh("POST", `/repos/${repo}/issues/${issueNum}/comments`, { body: receipt });

  if (callback && /^https:\/\//.test(callback)) {
    try {
      await fetch(callback, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ txid, tier: tierId, usd: v.amount, work: out.work, at: new Date().toISOString() }),
        signal: AbortSignal.timeout(15000),
      });
    } catch { /* פרסום-האישיו-הוא-הערוץ-הקנוני */ }
  }

  gh("PATCH", `/repos/${repo}/issues/${issueNum}`, { state: "closed", labels: [...(issue.labels?.map(l => l.name) ?? []), "paid-work-delivered"] });
  console.log(`[door] PAID WORK DELIVERED · issue #${issueNum} · $${v.amount.toFixed(2)} · ${out.work.length} chars`);
}

main().catch(e => { console.error("[door] FATAL", e.message); process.exit(1); });
