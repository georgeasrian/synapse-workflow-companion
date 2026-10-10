const $ = selector => document.querySelector(selector);
const form = $("#axon-chat-form");
const input = $("#axon-chat-input");
const transcript = $("#axon-chat-transcript");
const status = $("#axon-chat-status");
const submit = $("#axon-chat-submit");
let context = { hospital: null, guidelineRows: [], encounterState: {}, lvoState: "not-assessed", consultationTime: "" };
const conversation = [];

function escapeHtml(value) {
  const div = document.createElement("div");
  div.textContent = String(value || "");
  return div.innerHTML;
}

function renderMessage(role, text, sources = [], caution = "") {
  transcript.querySelector(".chat-empty")?.remove();
  const item = document.createElement("article");
  item.className = "chat-message chat-message-" + role;
  const citations = sources.length ? `<p class="chat-sources"><strong>Guideline source</strong> ${sources.map(source => `${escapeHtml(source.field)}: ${escapeHtml(source.value)}`).join(" · ")}</p>` : "";
  item.innerHTML = `<strong>${role === "user" ? "You" : "Axon"}</strong><p>${escapeHtml(text)}</p>${citations}${caution ? `<small>${escapeHtml(caution)}</small>` : ""}`;
  transcript.append(item);
  transcript.scrollTop = transcript.scrollHeight;
}

function setAvailability() {
  const ready = Boolean(context.hospital && context.guidelineRows.length);
  input.disabled = !ready;
  submit.disabled = !ready;
  if (!ready) status.textContent = "Select a hospital to ask Axon.";
  else if (!status.dataset.loading) status.textContent = `Grounded in ${context.hospital.name} (${context.hospital.id}).`;
}

window.addEventListener("axon:context", event => {
  context = event.detail;
  setAvailability();
});

form.addEventListener("submit", async event => {
  event.preventDefault();
  const question = input.value.trim();
  const base = String(window.AXON_CHAT_API_BASE_URL || "").replace(/\/$/, "");
  if (!question || !context.hospital || !base) return;
  renderMessage("user", question);
  conversation.push({ role: "user", content: question });
  input.value = "";
  input.disabled = true;
  submit.disabled = true;
  status.dataset.loading = "true";
  status.textContent = "Axon is checking this hospital's guideline…";
  try {
    const response = await fetch(base + "/api/chat", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ ...context, question, conversation: conversation.slice(-6) }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || "Axon is temporarily unavailable.");
    renderMessage("assistant", data.answer, data.sources || [], data.caution || "");
    conversation.push({ role: "assistant", content: data.answer });
    status.textContent = "Answer grounded in the selected hospital guideline.";
  } catch (error) {
    renderMessage("assistant", error.message || "Axon is temporarily unavailable. Use the visible guideline.");
    status.textContent = "Chat unavailable; the workflow recommendation remains available.";
  } finally {
    delete status.dataset.loading;
    setAvailability();
  }
});
