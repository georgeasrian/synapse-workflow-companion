import {escapeHtml,guidelineFromCsv,saveImports,savedImports} from "./guideline-parser.js";
import {actionsFor,buildNudge} from "./nudges.js";
const hospitalSelect=document.querySelector("#hospital"),timeInput=document.querySelector("#consult-time"),timeSource=document.querySelector("#time-source"),lvoControls=document.querySelector("#lvo-controls"),details=document.querySelector("#guide-details"),actions=document.querySelector("#actions"),importStatus=document.querySelector("#import-status"),dropZone=document.querySelector("#drop-zone"),fileInput=document.querySelector("#csv-input");
let guidelines=[],selectedId="",lvoState="not-assessed",completed=new Set(),timeOverridden=false;
const field=(guideline,label)=>guideline.fields[label.toLowerCase()]||"";
function currentGuideline(){return guidelines.find(guideline=>guideline.id===selectedId)||guidelines[0];}
function setHospitalTime(){
  if(timeOverridden) return; const guideline=currentGuideline(); const zone=field(guideline,"Local Time Zone").match(/\(([^)]+)\)/)?.[1]||"UTC";
  const parts=new Intl.DateTimeFormat("en-CA",{timeZone:zone,year:"numeric",month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit",hourCycle:"h23"}).formatToParts(new Date());
  const map=Object.fromEntries(parts.map(part=>[part.type,part.value])); timeInput.value="${map.year}-${map.month}-${map.day}T${map.hour}:${map.minute}"; timeSource.textContent="Auto-populated for "+zone+"; you may override it.";
}
function renderHospitals(){hospitalSelect.innerHTML=guidelines.map(guideline=>"<option value=\\""+escapeHtml(guideline.id)+"\\">"+escapeHtml(guideline.name)+" ("+escapeHtml(guideline.id)+")"+(guideline.imported ? " · imported" : "")+"</option>").join("");selectedId=guidelines.some(g=>g.id===selectedId)?selectedId:guidelines[0]?.id;hospitalSelect.value=selectedId;}
function render(){
  const guideline=currentGuideline();if(!guideline)return;
  details.innerHTML=guideline.rows.map(row=>"<dt>"+escapeHtml(row.field)+"</dt><dd>"+escapeHtml(row.value)+"</dd>").join("");
  [...lvoControls.querySelectorAll("button")].forEach(button=>button.classList.toggle("is-selected",button.dataset.lvo===lvoState));
  actions.innerHTML=actionsFor(guideline,lvoState).map(action=>"<div class=\\"action-item\\"><div><p>"+escapeHtml(action.label)+"</p><small>"+escapeHtml(action.detail)+(action.reason ? " "+escapeHtml(action.reason) : "")+"</small></div><button type=\\"button\\" data-action=\\""+action.key+"\\" "+(action.disabled ? "disabled" : "")+" class=\\""+(completed.has(action.key) ? "is-selected" : "")+"\\">"+(completed.has(action.key) ? "Yes" : "No")+"</button></div>").join("");
  const nudge=buildNudge(guideline,lvoState);document.querySelector("#nudge-heading").textContent=nudge.title;document.querySelector("#nudge-copy").textContent=nudge.copy;document.querySelector("#nudge-steps").innerHTML=nudge.steps.map(step=>"<li>"+escapeHtml(step)+"</li>").join("");document.querySelector("#nudge-source").textContent=nudge.source;
}
async function loadBundled(){const manifest=await fetch("guidelines/manifest.json").then(response=>response.json());return Promise.all(manifest.map(async item=>guidelineFromCsv(await fetch("guidelines/"+item.file).then(response=>response.text()),item.file,item)));}
async function importFiles(files){
  const imported=[],failures=[];for(const file of files){try{imported.push(guidelineFromCsv(await file.text(),file.name,{imported:true}));}catch(error){failures.push(file.name+": "+error.message);}}
  if(imported.length){const ids=new Set(imported.map(item=>item.id));guidelines=[...guidelines.filter(item=>!ids.has(item.id)),...imported];saveImports(guidelines);selectedId=imported[0].id;completed.clear();timeOverridden=false;renderHospitals();setHospitalTime();render();}
  importStatus.textContent=imported.length ? "Imported "+imported.length+" hospital guideline"+(imported.length>1 ? "s" : "")+". It is available on this browser." : failures.join(" ");if(failures.length && imported.length)importStatus.textContent+=" "+failures.join(" ");
}
hospitalSelect.addEventListener("change",()=>{selectedId=hospitalSelect.value;completed.clear();timeOverridden=false;setHospitalTime();render();});
timeInput.addEventListener("input",()=>{timeOverridden=true;timeSource.textContent="Manual time override.";});
lvoControls.addEventListener("click",event=>{const state=event.target.dataset.lvo;if(!state)return;lvoState=state;completed.clear();render();});
actions.addEventListener("click",event=>{const key=event.target.dataset.action;if(!key)return;completed.has(key)?completed.delete(key):completed.add(key);render();});
fileInput.addEventListener("change",event=>importFiles([...event.target.files]));
["dragenter","dragover"].forEach(type=>dropZone.addEventListener(type,event=>{event.preventDefault();dropZone.classList.add("is-dragging");}));
["dragleave","drop"].forEach(type=>dropZone.addEventListener(type,event=>{event.preventDefault();dropZone.classList.remove("is-dragging");}));
dropZone.addEventListener("drop",event=>importFiles([...event.dataTransfer.files].filter(file=>/\.csv$/i.test(file.name))));
try{guidelines=[...await loadBundled(),...savedImports()];renderHospitals();setHospitalTime();render();}catch(error){importStatus.textContent="Unable to load bundled guidelines: "+error.message;}
