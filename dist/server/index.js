const recentRequests = new Map();
const NUDGE_EXAMPLES = [
  { id: "N1", event: "LVO present = Yes at SYN-002", expected: "Advisory: not thrombectomy capable; tell the ED provider to activate the transfer center; preferred destination is Metro Neuroscience Institute.", fields: "LVO Protocol" },
  { id: "N2", event: "LVO present = Yes at SYN-006 outside the EVT window", expected: "Advisory: ED provider initiates transfer; do not suggest activating the EVT team.", fields: "LVO Protocol" },
  { id: "N3", event: "Last known well = Unknown at SYN-003", expected: "Advisory: wake-up protocol is in use.", fields: "Wake Up Protocol" },
  { id: "N4", event: "Thrombolytic given = Yes at SYN-004", expected: "Advisory: teleneurologist does not enter medication orders; hospital provider uses the local order set; no order-set-name nudge.", fields: "Order Entry; Order Set Name" },
  { id: "N5", event: "Complete clicked; charge not entered at SYN-007", expected: "Hard stop: tele-neurology encounter charge required before sign-off.", fields: "Charge Entry" },
  { id: "N6", event: "CTA done = Yes at SYN-005", expected: "Info: CT perfusion not available; AI is ClarityLVO.", fields: "CT Perfusion; AI" },
  { id: "N7", event: "Complete clicked at SYN-004 general neuro", expected: "Hard stop: do not complete until the hospital provider confirms the plan.", fields: "Consult Completion Rule" },
  { id: "N8", event: "Allergies entered: none at SYN-002", expected: "No nudge; staying quiet is correct.", fields: "(none)" },
  { id: "N9", event: "Sunday rounding encounter opened at SYN-001", expected: "Info: rounds Monday-Friday only; check why a Sunday rounding encounter exists.", fields: "When Do We Round?" },
];



const response = (body, status = 200) => new Response(JSON.stringify(body), {
  status,
  headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" },
});

function rateLimit(request) {
  const ip = request.headers.get("cf-connecting-ip") || "anonymous";
  const now = Date.now();
  const windowMs = 60_000;
  const timestamps = (recentRequests.get(ip) || []).filter(value => now - value < windowMs);
  if (timestamps.length >= 8) return false;
  timestamps.push(now);
  recentRequests.set(ip, timestamps);
  return true;
}

function safePayload(input) {
  const hospital = input?.hospital || {};
  const rows = Array.isArray(input?.guidelineRows) ? input.guidelineRows.slice(0, 60) : [];
  return {
    hospital: {
      id: String(hospital.id || "").slice(0, 64),
      name: String(hospital.name || "").slice(0, 120),
      timezone: String(hospital.timezone || "").slice(0, 64),
    },
    guidelineRows: rows.map(row => ({
      field: String(row?.field || "").slice(0, 100),
      value: String(row?.value || "").slice(0, 500),
    })),
    encounterState: input?.encounterState || {},
    fallback: input?.fallback || {},
  };
}

async function recommendation(request, env) {
  if (request.method !== "POST") return response({ error: "Method not allowed" }, 405);
  if (!rateLimit(request)) return response({ error: "Please wait before requesting another recommendation." }, 429);
  if (!env.OPENAI_API_KEY) return response({ error: "AI recommendation is not configured." }, 503);

  let input;
  try { input = safePayload(await request.json()); }
  catch { return response({ error: "Invalid recommendation request." }, 400); }

  const upstream = await fetch("https://api.openai.com/v1/responses", {
    method: "POST",
    headers: {
      "authorization": "Bearer " + env.OPENAI_API_KEY,
      "content-type": "application/json",
    },
    body: JSON.stringify({
      model: "gpt-5-mini",
      reasoning: { effort: "low" },
      instructions: "You are Axon, a hospital-workflow assistant operating on synthetic or de-identified demo data only. Use only the supplied hospital guideline rows and encounter state as the source of truth. The reference examples show the desired nudge tiers and behavior: hard stops outrank advisories; an advisory or informational nudge must be tied to an applicable guide field; and if nothing applies, do not invent an alert. Never copy another hospital's rule into the current hospital. Recommend exactly one hospital-specific operational next step. Do not diagnose, determine eligibility, invent protocols, provide treatment advice beyond the supplied guideline, or override a hard stop. Keep the wording concise and practical. Return only the requested JSON.",
      input: JSON.stringify({ referenceExamples: NUDGE_EXAMPLES, currentRequest: input }),
      text: {
        format: {
          type: "json_schema",
          name: "axon_workflow_nudge",
          strict: true,
          schema: {
            type: "object",
            additionalProperties: false,
            properties: {
              title: { type: "string" },
              copy: { type: "string" },
              steps: { type: "array", items: { type: "string" }, minItems: 1, maxItems: 3 },
              source: { type: "string" },
            },
            required: ["title", "copy", "steps", "source"],
          },
        },
      },
    }),
  });

  if (!upstream.ok) return response({ error: "The AI service is temporarily unavailable." }, 502);
  const result = await upstream.json();
  try {
    const nudge = JSON.parse(result.output_text);
    return response(nudge);
  } catch {
    return response({ error: "The AI response could not be read." }, 502);
  }
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === "/api/recommendation") return recommendation(request, env);
    if (env.ASSETS?.fetch) return env.ASSETS.fetch(request);
    return new Response("Not found", { status: 404 });
  },
};

