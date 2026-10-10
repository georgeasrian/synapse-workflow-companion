const STORAGE_KEY = "synapse-imported-guidelines-v1";
export function parseCsv(text) {
  const rows=[]; let row=[],cell="",quoted=false;
  for(let i=0;i<text.length;i+=1){ const char=text[i],next=text[i+1]; if(char === '"' && quoted && next === '"'){cell+='"';i+=1;} else if(char === '"') quoted=!quoted; else if(char === "," && !quoted){row.push(cell.trim());cell="";} else if((char === "\n" || char === "\r") && !quoted){if(char === "\r" && next === "\n") i+=1;row.push(cell.trim());if(row.some(Boolean)) rows.push(row);row=[];cell="";} else cell+=char; }
  row.push(cell.trim());if(row.some(Boolean)) rows.push(row);return rows;
}
function titleFromFilename(fileName){return fileName.replace(/\.csv$/i,"").replace(/[_-]+/g," ").replace(/\b\w/g,c=>c.toUpperCase()).replace(/Challenge \d+ Guide Syn \d+ /i,"").replace(/\(\d+\)/g,"").trim();}
export function guidelineFromCsv(text,fileName,metadata={}) {
  const parsed=parseCsv(text); if(parsed.length<2 || parsed[0].length<2) throw new Error("Use a two-column CSV with headers such as “Guide Field,Synthetic Value”.");
  const rows=parsed.slice(1).filter(row=>row[0] && row[1]).map(([field,value])=>({field,value}));
  if(!rows.length) throw new Error("No guideline rows were found in this CSV.");
  const fields=Object.fromEntries(rows.map(({field,value})=>[field.trim().toLowerCase(),value.trim()]));
  const identifier=metadata.id || text.match(/\bSYN[-_ ]?\d{3}\b/i)?.[0]?.replace(/[_ ]/g,"-") || fileName.match(/syn[_-]?\d{3}/i)?.[0]?.replace(/[_ ]/g,"-").toUpperCase() || "CUSTOM-"+(fields["hospital id"] || fields["hospital name"] || titleFromFilename(fileName)).replace(/[^a-z0-9]+/gi,"-").replace(/^-|-$/g,"").toUpperCase();
  return {id:identifier.toUpperCase(),name:metadata.name || fields["hospital name"] || titleFromFilename(fileName),rows,fields,imported:Boolean(metadata.imported),fileName};
}
export function savedImports(){try{return JSON.parse(localStorage.getItem(STORAGE_KEY)||"[]");}catch{return [];}}
export function saveImports(guidelines){localStorage.setItem(STORAGE_KEY,JSON.stringify(guidelines.filter(guideline=>guideline.imported)));}
export function escapeHtml(value){return String(value).replace(/[&<>"']/g,character=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[character]));}
