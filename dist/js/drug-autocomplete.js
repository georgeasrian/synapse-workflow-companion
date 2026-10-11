// Terminology helper adapted from the Axon medication-search prototype.
// It supports documentation search only; it does not determine an allergy.
const DRUGS = [
  { generic: "alteplase", names: ["alteplase", "Activase", "Actilyse", "Cathflo Activase", "tPA", "rtPA"] },
  { generic: "tenecteplase", names: ["tenecteplase", "TNKase", "Metalyse", "TNK-tPA", "TNK"] },
  { generic: "reteplase", names: ["reteplase", "Retavase", "Retevase", "Rapilysin", "rPA"] },
  { generic: "streptokinase", names: ["streptokinase", "Streptase", "Kabikinase"] },
  { generic: "urokinase", names: ["urokinase", "Kinlytic", "Abbokinase", "uPA"] },
  { generic: "anistreplase", names: ["anistreplase", "Eminase", "APSAC"] },
  { generic: "saruplase", names: ["saruplase", "scuPA", "prourokinase"] },
  { generic: "desmoteplase", names: ["desmoteplase", "DSPA"] },
];
const normalize = value => String(value || "").toLowerCase().replace(/[^a-z0-9]/g, "");
function resultsFor(value) { const query = normalize(value); if (!query) return []; return DRUGS.flatMap(drug => drug.names.filter(name => normalize(name).includes(query)).map(name => ({ generic: drug.generic, name, score: normalize(name) === query ? 0 : normalize(name).startsWith(query) ? 1 : 2 }))).sort((a, b) => a.score - b.score || a.name.localeCompare(b.name)).slice(0, 8); }
export function attachDrugAutocomplete(input, onSelect) {
  const menu = document.createElement("div"); menu.className = "drug-suggestions"; menu.hidden = true; menu.setAttribute("role", "listbox"); input.insertAdjacentElement("afterend", menu); input.setAttribute("autocomplete", "off"); input.setAttribute("role", "combobox"); input.setAttribute("aria-autocomplete", "list");
  let results = [], active = 0;
  const close = () => { menu.hidden = true; input.setAttribute("aria-expanded", "false"); };
  const choose = item => { if (!item) return; input.value = item.name.toLowerCase() === item.generic ? item.generic : `${item.name} (${item.generic})`; input.dispatchEvent(new Event("change", { bubbles: true })); onSelect?.(item); close(); };
  const render = () => { menu.replaceChildren(); results.forEach((item, index) => { const option = document.createElement("button"); option.type = "button"; option.className = index === active ? "is-active" : ""; option.setAttribute("role", "option"); option.setAttribute("aria-selected", String(index === active)); option.innerHTML = `<strong>${item.name}</strong>${item.name.toLowerCase() === item.generic ? "" : `<span>${item.generic}</span>`}`; option.addEventListener("mousedown", event => { event.preventDefault(); choose(item); }); menu.append(option); }); menu.hidden = !results.length; input.setAttribute("aria-expanded", String(results.length > 0)); };
  input.addEventListener("input", () => { results = resultsFor(input.value); active = 0; render(); });
  input.addEventListener("keydown", event => { if (!results.length) return; if (event.key === "ArrowDown" || event.key === "ArrowUp") { event.preventDefault(); active = (active + (event.key === "ArrowDown" ? 1 : results.length - 1)) % results.length; render(); } else if (event.key === "Enter") { event.preventDefault(); choose(results[active]); } else if (event.key === "Escape") close(); });
  input.addEventListener("blur", () => setTimeout(close, 120));
}
