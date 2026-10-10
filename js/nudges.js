// NUDGE RULES — collaborators can edit wording and routing here.
const value=(guide,label)=>guide.fields[label.toLowerCase()]||"";
const formatTimeRange=value=>String(value).replace(/\b([01]\d|2[0-3])([0-5]\d)\s*-\s*([01]\d|2[0-3])([0-5]\d)/g,(_,startHour,startMinute,endHour,endMinute)=>{const clock=(hour,minute)=>{const numeric=Number(hour);return (numeric%12||12)+":"+minute+" "+(numeric>=12?"PM":"AM");};return clock(startHour,startMinute)+" - "+clock(endHour,endMinute);});

export function buildNudge(guide,lvoState,state={},fallback) {
  const charge=value(guide,"Charge Entry"),completion=value(guide,"Consult Completion Rule");
  const ctPerfusion=value(guide,"CT Perfusion"),ai=value(guide,"AI"),order=value(guide,"Order Entry");
  const orderSet=value(guide,"Order Set Name"),noteTitle=value(guide,"Required Note Title");
  const rounding=value(guide,"When Do We Round?"),timing=value(guide,"Rounding Timing");

  // Hard stops always outrank advisories and routine next-step guidance.
  if(state.signoff&&charge==="Yes"&&!state.chargeEntered)return {title:"Record the required encounter charge",copy:"This hospital requires the tele-neurology encounter charge before sign-off.",steps:["Record the encounter charge.","Return to Sign-off and complete the consult."],source:"Hard stop · Sign-off · Charge Entry"};
  if(state.signoff&&completion)return {title:"Obtain confirmation before sign-off",copy:completion,steps:["Confirm the plan with the hospital provider.","Then complete the consult."],source:"Hard stop · Sign-off · Consult Completion Rule"};

  // Encounter Steps are the source of truth for the main red panel. Event-specific
  // advisories arrive from the backend, while this panel always advances to the first
  // incomplete workflow step once a completed step is checked off.
  return fallback||{title:"Continue the hospital workflow",copy:"No state-driven nudge is active.",steps:[],source:"Next workflow step"};
}

export function actionsFor(guide,lvoState){const order=value(guide,"Order Entry"),rounding=value(guide,"Rounding Process"),charge=value(guide,"Charge Entry"),lvoAvailable=Boolean(value(guide,"LVO Protocol"));return [{key:"lvo",label:"Run LVO protocol",detail:value(guide,"LVO Protocol")||"No LVO protocol in this CSV.",disabled:!lvoAvailable||lvoState==="no",reason:lvoState==="no"?"Not relevant when LVO is No.":!lvoAvailable?"No protocol in this guideline.":""},{key:"order",label:"Enter thrombolytic order",detail:order||"No order entry instruction in this CSV.",disabled:!order,reason:!order?"No order entry instruction in this CSV.":""},{key:"round",label:"Initiate rounding",detail:rounding||"No rounding instruction in this CSV.",disabled:!rounding,reason:!rounding?"No rounding instruction in this guideline.":""},{key:"charge",label:"Record charge",detail:charge==="Yes"?"Charge entry is required for this guideline.":charge||"No charge entry instruction in this CSV.",disabled:charge!=="Yes",reason:charge!=="Yes"?"Charge entry is not required by this guideline.":""}];}

