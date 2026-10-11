const $ = selector => document.querySelector(selector);

function insertDiagnosticFields() {
  const workflow = $("#workflow-state");
  if (!workflow) return;
  const lvo = workflow.querySelector('[data-lvo]')?.closest(".lvo-fieldset");
  const cta = workflow.querySelector('[data-cta]')?.closest(".lvo-fieldset");
  const ctHead = $("#ct-head-controls")?.closest(".lvo-fieldset");
  addField(lvo, "occlusion-site", "Occlusion site", "Optional");
  addField(cta, "cta-interpretation", "Interpretation", "Optional");
  addField(ctHead, "ct-head-interpretation", "Interpretation", "Optional");
}

function addField(fieldset, id, label, placeholder) {
  if (!fieldset || document.getElementById(id)) return;
  const wrap = document.createElement("label");
  wrap.className = "diagnostic-text";
  wrap.htmlFor = id;
  wrap.textContent = label;
  const input = document.createElement("input");
  input.id = id;
  input.type = "text";
  input.placeholder = placeholder;
  input.addEventListener("input", () => window.dispatchEvent(new Event("axon:context")));
  wrap.append(input);
  fieldset.append(wrap);
}

function showThrombolyticPrompt() {
  const panel = $("#consult-nudge");
  if (!panel || $("#workflow-state [data-step=\"imaging\"]")?.classList.contains("is-selected") === false) return;
  $("#nudge-heading").textContent = "Thrombolytic orders";
  $("#nudge-copy").textContent = "Diagnostics complete — document the hospital-specific thrombolytic decision and order status.";
  $("#nudge-steps").innerHTML = "<li>Review the selected hospital's thrombolytic pathway.</li><li>Record whether thrombolytic was given and whether the order was placed.</li>";
  $("#nudge-source").textContent = "Workflow state · Diagnostics completed";
  panel.hidden = false;
}

function updateSkipFlags() {
  const order = ["intake","history","clinicalWorkup","imaging","recommendation","note","signoff"];
  const completed = order.map(key => $("#workflow-state [data-step=\""+key+"\"]")?.classList.contains("is-selected"));
  const highest = completed.lastIndexOf(true);
  const missing = highest > 0 ? order.slice(0, highest).filter((key, i) => !completed[i]) : [];
  const alert = $("#workflow-sequence-alert");
  if (!alert) return;
  if (!missing.length) return;
  const names = {intake:"1. Intake",history:"2. History",clinicalWorkup:"3. Clinical Workup",imaging:"4. Diagnostics",recommendation:"5. Recommendation",note:"6. Note"};
  alert.hidden = false;
  alert.innerHTML = "<strong>Missed step flag:</strong> complete "+missing.map(key => names[key]).join(", ")+".";
}

function mountQualityChecks() {
  const card = $("#run-validation")?.closest(".card");
  if (!card || $("#run-browser-quality-checks")) return;
  const button = document.createElement("button");
  button.id = "run-browser-quality-checks";
  button.type = "button";
  button.textContent = "Run workflow checks";
  const output = document.createElement("div");
  output.id = "browser-quality-results";
  output.className = "reference-list";
  button.addEventListener("click", () => {
    const checks = [
      ["Hospital selected", Boolean($("#hospital")?.value)],
      ["Hospital-local consultation time set", Boolean($("#consult-time")?.value)],
      ["Consult type selected", Boolean([...document.querySelectorAll("[data-consult-type].is-selected")].length)],
      ["No skipped encounter steps", !$("#workflow-sequence-alert") || $("#workflow-sequence-alert").hidden],
      ["CTA request explicitly documented", Boolean($("#workflow-state [data-cta].is-selected"))],
    ];
    output.innerHTML = checks.map(([name, pass]) => "<article><strong>"+(pass ? "Pass" : "Needs attention")+"</strong><p>"+name+"</p></article>").join("");
  });
  card.querySelector("#validation-status")?.before(button);
  card.append(output);
}

function enhance() {
  insertDiagnosticFields();
  updateSkipFlags();
  mountQualityChecks();
  const nihss = $("#nihss-score");
  if (nihss && !$("#nihss-ranges")) {
    const help = document.createElement("small");
    help.id = "nihss-ranges";
    help.textContent = "NIHSS: 0 = no stroke symptoms; 1–4 minor; 5–15 moderate; 16–20 moderate–severe; 21–42 severe.";
    nihss.closest("label")?.append(help);
  }
}

const workflow = $("#workflow-state");
workflow?.addEventListener("click", event => {
  const step = event.target.closest("[data-step]")?.dataset.step;
  if (!step) return;
  requestAnimationFrame(() => {
    enhance();
    if (step === "imaging" && $("#workflow-state [data-step=\"imaging\"]")?.classList.contains("is-selected")) showThrombolyticPrompt();
  });
});
new MutationObserver(() => requestAnimationFrame(enhance)).observe(workflow, {childList:true, subtree:false});
function moveImportCardsToRightRail() {
  const nudge = $("#consult-nudge");
  const guideCard = $("#drop-zone")?.closest("section");
  const storyboardCard = $("#storyboard-drop-zone")?.closest("section");
  if (!nudge || !guideCard || !storyboardCard || $("#library-side")) return;
  const rail = document.createElement("aside");
  rail.id = "library-side";
  rail.setAttribute("aria-label", "Guideline imports");
  rail.append(guideCard, storyboardCard);
  nudge.after(rail);
}
moveImportCardsToRightRail();
function updateCtStatus() {
  const panel = $("#workflow-state [data-workflow-key=\"imaging\"] .imaging-inputs");
  if (!panel) return;
  panel.querySelector(".cta-service-status")?.remove();
  let status = panel.querySelector("#ct-state-status");
  if (!status) {
    status = document.createElement("p");
    status.id = "ct-state-status";
    status.className = "cta-service-status";
    panel.append(status);
  }
  const yesNo = selector => panel.querySelector(selector+" .is-selected")?.textContent || "Not assessed";
  status.innerHTML = "<strong>CT status</strong><span>CT Head: "+yesNo("#ct-head-controls")+" · CTA: "+yesNo("[data-cta]")+"</span>";
}
function simplifyCopy() {
  document.querySelector(".case-head .eyebrow")?.remove();
  document.querySelector(".case-head p:not(.eyebrow)")?.remove();
  document.querySelector(".intake-inputs h2")?.remove();
  document.querySelector("#time-source")?.remove();
  document.querySelector(".allergy-search small")?.remove();
  document.querySelector(".encounter-steps")?.previousElementSibling?.remove();
  const intro = document.querySelector(".encounter-steps")?.previousElementSibling;
  if (intro?.classList.contains("muted")) intro.remove();
  const ranges = $("#nihss-ranges");
  if (ranges) ranges.textContent = ranges.textContent.replace(/^NIHSS:\s*/, "");
}
function placeTopStatus() {
  document.querySelector(".status-pill")?.remove();
}
$("#support-button")?.addEventListener("click",()=>alert("Customer support is not configured in this demo."));
workflow?.addEventListener("click",()=>requestAnimationFrame(updateCtStatus));
new MutationObserver(()=>requestAnimationFrame(()=>{updateCtStatus();simplifyCopy();placeTopStatus();})).observe(workflow,{childList:true,subtree:false});
updateCtStatus();simplifyCopy();placeTopStatus();
function buildRightRail() {
  const layout = document.querySelector(".layout");
  const nudge = $("#consult-nudge");
  const chat = $("#axon-chat-title")?.closest("section");
  const library = $("#library-side");
  const info = $("#info-panel");
  if (!layout || !nudge || !chat || $("#right-rail")) return;
  const rail = document.createElement("aside");
  rail.id = "right-rail";
  rail.setAttribute("aria-label", "Guidance and support");
  rail.append(nudge);
  if (library) rail.append(library);
  rail.append(chat);
  if (info) rail.append(info);
  layout.append(rail);
}
function hideEmptyNudge() {
  const panel = $("#consult-nudge");
  if (!panel) return;
  const title = $("#nudge-heading")?.textContent.trim();
  const copy = $("#nudge-copy")?.textContent.trim();
  panel.hidden = !title && !copy;
}
buildRightRail();
hideEmptyNudge();
new MutationObserver(hideEmptyNudge).observe($("#consult-nudge"), {childList:true,subtree:true,characterData:true});
enhance();
