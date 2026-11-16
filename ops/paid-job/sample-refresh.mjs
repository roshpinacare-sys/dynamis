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
const model = process.env.NIM_MODEL || "nvidia/nemotron-3.5-lightning-30b-a3b";

const t0 = Date.now();
const r = await fetch(base + "/chat/completions", {
  method: "POST",
  headers: { "Content-Type": "application/json", Authorization: "Bearer " + key },
  body: JSON.stringify({
    model,
    messages: [
      { role: "system", content: "You are SAOS Sovereign AI — a paid, frontier-grade work engine. Answer precisely, truthfully, completely. No filler." },
      { role: "user", content: SAMPLE_PROMPT },
    ],
    max_tokens: 700, // רמת-micro בדיוק — מה ש-$0.50 קונה
    temperature: 0.4,
  }),
  signal: AbortSignal.timeout(120000),
});
const j = await r.json();
// §54 לכידת-באג: מודלי-חשיבה (nemotron) עלולים-להחזיר content=null ואת-התשובה
// ב-reasoning_content — נפילה-חזרה-חכמה (תקף-גם-למבצה-המשלם).
const msg = j.choices?.[0]?.message;
const work = msg?.content ?? msg?.reasoning_content;
if (!work || !String(work).trim()) { console.log("nim-empty http=" + r.status + " " + JSON.stringify(j).slice(0, 200)); process.exit(1); }

const sample = {
  at: new Date().toISOString(),
  protocol: "sovereign-ai-paid sample v1 · §54",
  tier: "micro",
  usd: 0.5,
  model,
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
