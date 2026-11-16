// §54 · מחולל-הדוגמה-החיה — פלט-אמיתי-מהמנוע ברמת-micro ($0.50) לדף-המוצר.
// חוקים: אותו-מנוע-ואותה-רמה-בדיוק-כמו-לקוח-משלם · אפס-סודות-בפלט ·
// הקבלה-מתעדת-מודל/השהיה/אסימונים · הכל-מודד-בפועל (שום-דבר-לא-נכתב-ביד).
import { execFileSync } from "node:child_process";
import { writeFileSync, mkdirSync } from "node:fs";

const SAMPLE_PROMPT = `You are being sampled as a paid work engine. A buyer pays $0.50 for this exact tier. Produce, in both English and Hebrew:
1. Exactly 5 crisp bullets on why HTTP-402 native payments (x402, USDC on Base) change machine-to-machine commerce.
2. One 4-field JSON example of a purchase receipt (txid, usd, work, status).
Keep it under 160 words per language. No filler.`;

const base = (process.env.NVIDIA_BASE_URL || "https://integrate.api.nvidia.com/v1").replace(/\/$/, "");
const key = process.env.NVIDIA_NIM_KEY || process.env.NVIDIA_API_KEY || process.env.NIM_API_KEY;
if (!key) { console.log("nim-key-missing (fail-closed)"); process.exit(1); }
// §54 · מועמדים-במקביל (Promise.any): המודל-החם-הראשון-מנצח — נלמד-חי:
// מודלי-flash קרים-למפתח (75ש' פר-מודל בטור = 150ש' המתנה). במקביל: שניות.
const MODEL_CANDIDATES_MICRO = [
  process.env.NIM_MODEL_MICRO,
  "z-ai/glm-5.3-flash",
  "minimaxai/minimax-m3.1-flash",
  "deepseek-ai/deepseek-v4.1-flash",
  "openai/gpt-oss-20b",
  "google/gemma-3-12b-it",
  "nvidia/nemotron-3.5-lightning-30b-a3b", // עוגן-מוכח (עונה-תמיד-ב-4-5ש')
].filter(Boolean);
if (process.env.NIM_MODEL) MODEL_CANDIDATES_MICRO.splice(0, MODEL_CANDIDATES_MICRO.length, process.env.NIM_MODEL);

async function callModel(cand) {
  const t = Date.now();
  const r = await fetch(base + "/chat/completions", {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: "Bearer " + key },
    body: JSON.stringify({
      model: cand,
      messages: [
        { role: "system", content: "You are SAOS Sovereign AI — a paid, frontier-grade work engine. Answer precisely, truthfully, completely. No filler." },
        { role: "user", content: SAMPLE_PROMPT },
      ],
      max_tokens: 700, // רמת-micro בדיוק — מה ש-$0.50 קונה
      temperature: 0.4,
    }),
    signal: AbortSignal.timeout(75000),
  });
  const jj = await r.json();
  const mm = jj.choices?.[0]?.message;
  const ww = mm?.content ?? mm?.reasoning_content; // §54: מודלי-חשיבה מחזירים-לפעמים content=null
  if (!ww || !String(ww).trim()) throw new Error("empty-from " + cand + " http=" + r.status);
  return { cand, jj, ww: String(ww), ms: Date.now() - t };
}

// גישוש-מודלים-חי (שמות-בלבד · §54): רשימת-המודלים-הזמינים-למפתח-הזה —
// בסיס-החלטה לבחירת-מודל-ישיר (לא-חשיבה) לרמת-micro.
try {
  const mr = await fetch(base + "/models", { headers: { Authorization: "Bearer " + key }, signal: AbortSignal.timeout(20000) });
  const mj = await mr.json();
  const ids = (mj.data || []).map((m) => m.id).sort();
  console.log("models-available:", ids.length);
  console.log(ids.join("\n"));
} catch (e) {
  console.log("models-probe-failed:", String(e).slice(0, 100));
}

let model = null, j = null, work = null, t0 = Date.now();
const tried = MODEL_CANDIDATES_MICRO;
// Promise.any: המודל-החם-הראשון שעונה-תשובה-אמיתית מנצח · כל-השאר מבוטלים
model = await Promise.any(tried.map(async (cand) => {
  console.log("firing:", cand);
  const res = await callModel(cand);
  console.log("answered:", cand, res.ms + "ms");
  return res;
}));
j = model.jj; work = model.ww;
model = model.cand;
if (!work) { console.log("all-candidates-failed"); process.exit(1); }

const sample = {
  at: new Date().toISOString(),
  protocol: "sovereign-ai-paid sample v1 · §54",
  tier: "micro",
  usd: 0.5,
  model,
  modelChain: tried,
  engine: "NVIDIA-NIM (fleet compute)",
  latencyMs: Date.now() - t0,
  usage: j.usage ? { prompt: j.usage.prompt_tokens, completion: j.usage.completion_tokens } : null,
  prompt: SAMPLE_PROMPT,
  output: String(work).trim(),
  honesty: "נוצר-בהרצה-חינם-של-אותו-מנוע-ואותה-רמה בדיוק — לקוח-משלם מקבל-זהה (fail-closed בלי-תשלום-מאומת)",
};

mkdirSync("site/samples", { recursive: true });
writeFileSync("site/samples/live-sample.json", JSON.stringify(sample, null, 1) + "\n");
console.log("sample-ok model=" + model + " latencyMs=" + sample.latencyMs + " chars=" + sample.output.length);

execFileSync("git", ["config", "user.name", "roshpinacare-sys"]);
execFileSync("git", ["config", "user.email", "326012154+roshpinacare-sys@users.noreply.github.com"]);
execFileSync("git", ["add", "site/samples/live-sample.json"]);
try { execFileSync("git", ["commit", "-m", "live sample refresh (micro tier, real engine output) [skip ci]"]); } catch { console.log("no-change"); }
execFileSync("git", ["push"]);
console.log("committed+pushed");
