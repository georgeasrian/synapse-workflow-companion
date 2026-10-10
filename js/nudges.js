// NUDGE RULES — collaborators can change alert text and routing here without touching CSV imports or layout.
const value=(guideline,label)=>guideline.fields[label.toLowerCase()]||"";
export function buildNudge(guideline,lvoState) {
  const lvo=value(guideline,"LVO Protocol"), thrombolytic=value(guideline,"Thrombolytic");
  if(lvoState==="yes") return {title:"Possible LVO: follow the hospital’s escalation pathway",copy:lvo || "No LVO pathway is specified in this guideline.",steps:["Document the suspected LVO.","Notify the responsible ED provider.","Complete the transfer or thrombectomy pathway specified above."],source:"Triggered by: Current LVO state = Yes"};
  if(lvoState==="not-assessed") return {title:"Assess for LVO before closing the consult",copy:"The LVO pathway is available once an assessment is recorded.",steps:["Review imaging and clinical findings.","Record Yes or No for the current LVO state.","Continue with the applicable hospital workflow."],source:"Triggered by: Current LVO state = Not assessed"};
  return {title:"Proceed with the standard hospital workflow",copy:thrombolytic ? "Thrombolytic: "+thrombolytic+"." : "Review the selected guideline details.",steps:["Confirm the consultation documentation.","Use the order-entry and rounding instructions below when applicable.","Record required charge entry."],source:"Triggered by: Current LVO state = No"};
}
export function actionsFor(guideline,lvoState) {
  const orderEntry=value(guideline,"Order Entry"),rounding=value(guideline,"Rounding Process"),charge=value(guideline,"Charge Entry"),lvoAvailable=Boolean(value(guideline,"LVO Protocol"));
  return [
    {key:"lvo",label:"Run LVO protocol",detail:value(guideline,"LVO Protocol") || "No LVO protocol in this CSV.",disabled:!lvoAvailable || lvoState==="no",reason:lvoState==="no" ? "Not relevant when LVO is No." : !lvoAvailable ? "No protocol in this guideline." : ""},
    {key:"order",label:"Enter thrombolytic order",detail:orderEntry || "No order entry instruction in this CSV.",disabled:!orderEntry,reason:!orderEntry ? "No order entry instruction in this guideline." : ""},
    {key:"round",label:"Initiate rounding",detail:rounding || "No rounding instruction in this CSV.",disabled:!rounding,reason:!rounding ? "No rounding instruction in this guideline." : ""},
    {key:"charge",label:"Record charge",detail:charge==="Yes" ? "Charge entry is required for this guideline." : charge || "No charge entry instruction in this CSV.",disabled:charge!=="Yes",reason:charge!=="Yes" ? "Charge entry is not required by this guideline." : ""}
  ];
}
