"use strict";
// UI calculations are presentation only. Never infer a missing observation.
const $ = id => document.getElementById(id);
const node = (tag, text, className) => { const n = document.createElement(tag); if (text !== undefined) n.textContent = text; if (className) n.className = className; return n; };
const validValue = metric => metric.availability === "published" && metric.value !== null && Number.isFinite(metric.value);
// Formatting runs in the canvas paint path. Reuse formatters across frames.
const numberFormats = new Map();
const fmt = (n, digits = 0) => {
  if(!numberFormats.has(digits))numberFormats.set(digits,new Intl.NumberFormat("en-PH",{maximumFractionDigits:digits}));
  return numberFormats.get(digits).format(n);
};
const compactFormat = new Intl.NumberFormat("en-PH",{notation:"compact",maximumFractionDigits:2});
const compact = n => compactFormat.format(n);
const MODES = {
  exposure: {label:"AI task exposure", title:"Generative-AI task exposure by occupation", description:"Model-estimated · each PSA task statement for a PSOC unit group was scored by an AI model at least twice; the box shows the median task score (0–5).", encoding:"Box area grows with the cube of the PSA task statements listed for the group (stretched so differences show), NOT employment. Colour = median technical task exposure. Faint boxes have no score.", note:"Exposure describes how much of an occupation's tasks generative AI could assist with or perform. It is not an estimate of automation, displacement, layoffs or future employment. Scores are model estimates and have not been independently validated."},
  employment: {label:"Employment", metric:"employment_count", title:"Employment by major occupation group", description:"PSA LFS · 2024 annual estimates · employed persons, not jobs or vacancies.", encoding:"Area = employed persons. Colour = group employment. No detailed occupational counts are inferred.", note:"The group estimates sum to one person more than the source total because of source rounding. We retain the published cells unchanged."},
  detail: {label:"Employment detail", metric:"employment_count_subgroup", level:"psoc_sub_major_group", title:"Employment by sub-major occupation group (ILO-processed LFS)", description:"ILOSTAT · 2024 annual · employed persons in each of the 43 PSOC sub-major groups, from the Philippine Labor Force Survey as tabulated by the ILO.", encoding:"Area = employed persons. Colour = group employment. Finer than PSA's published groups, but an ILO tabulation: totals differ from PSA's by about 2.7%.", note:"These counts are an ILO re-tabulation of the same survey, not PSA's published figures. Do not add them to, or compare them cell by cell with, the major-group layer."},
  earnings: {label:"Earnings", metric:"earnings_monthly_median", level:"psoc_major_group", areaFrom:"employment_count", title:"Median monthly earnings of employees by major group", description:"ILOSTAT · 2024 annual · median monthly earnings of employees (wage and salary workers) in each major occupation group, Philippine Labor Force Survey as tabulated by the ILO.", encoding:"Area = employed persons (PSA). Colour = median monthly earnings of employees. Employees only; own-account workers and employers are not included.", note:"Earnings are published for major groups, so they describe a whole group and cannot rank the occupations inside it. The mean is shown in the details panel. Managers and Professionals share the same published median; the ILO series repeats that value and we keep it unchanged."},
  education: {label:"Education", metric:"education_advanced_share", level:"psoc_major_group", areaFrom:"employment_count", title:"Employed persons with advanced education, by major group", description:"ILOSTAT · 2024 annual · share of employed persons whose highest attainment is tertiary, calculated from the ILO's published counts.", encoding:"Area = employed persons (PSA). Colour = share with advanced (tertiary) education.", note:"This shows who works in a group today, not what the occupation requires. A high share does not mean a degree is needed for the job."},
  vulnerable: {label:"Own-account & family work", metric:"vulnerable_employment_share", level:"psoc_major_group", areaFrom:"employment_count", title:"Own-account and family work as a share of employment, by major group", description:"ILOSTAT · 2024 annual · own-account workers plus contributing family workers as a share of employed persons, from the Philippine Labor Force Survey as tabulated by the ILO.", encoding:"Area = employed persons (PSA). Colour = share of own-account and family workers.", note:"This is NOT informal employment (that is unavailable for the Philippines). Many own-account workers run registered businesses and many employees hold informal jobs. It says nothing about job quality or pay."},
  wages: {label:"Wage references", title:"Wage rates by occupation × industry", description:"PSA OWS · August 2024 · average monthly wage rate, including regular cash allowances. Covered formal establishments only.", encoding:"Equal-area boxes = separate job-position × industry records, NOT worker counts. Colour = monthly wage rate (log scale).", note:"Source-native occupation codes, not reconciled to PSOC 2022. Never sum or average these industry slices into national occupational pay. Withheld records remain in table view and exports."},
  ofw: {label:"OFW distribution", metric:"ofw_distribution_share", title:"How OFWs are distributed across occupations", description:"PSA SOF · April–September 2024 · share of the survey's OFWs in each major occupation group. Not the OFW share of domestic occupations.", encoding:"Area and colour = published share of all OFWs. Not domestic employment. Missing cells are not plotted.", note:"The armed-forces percentage is blank in the source, not zero. Source rounding is retained; percentages are not renormalised. CV above 10% is flagged as less precise."}
};
let payload, records = {}, mode = "exposure", filtered = [], zoom = 1, tableMode = false, page = 0;
const MISSING_EXPOSURE = {no_psa_tasks:"No PSA task list", not_scored:"Not yet scored"};
const displayValue = r => !validValue(r) ? (MISSING_EXPOSURE[r.availability] || "Unavailable") : mode === "exposure" ? `${fmt(r.value, 1)} / 5` : mode === "wages" ? `₱${fmt(r.value, 2)}` : mode === "earnings" ? `₱${fmt(r.value)} / month` : mode === "education" ? `${fmt(r.value * 100, 1)}% advanced` : mode === "vulnerable" ? `${fmt(r.value * 100, 1)}% own-account / family` : mode === "ofw" ? `${fmt(r.value * 100, 3)}%` : `${fmt(r.value)} persons`;
const gradeLabel = r => !validValue(r) ? (MISSING_EXPOSURE[r.availability] || "Withheld / missing") : mode === "exposure" ? `Model estimate · ${r.human_review_status === "human_reviewed" ? "expert-reviewed" : "not independently validated"}` : r.coefficient_of_variation > 10 ? "Low precision · CV > 10%" : r.standard_error === null ? "Precision not supplied" : "Published sampling precision";
// PSA prints titles in capitals; display them in title case. Codes, not titles,
// identify occupations, so this is presentation only.
const KEEP_UPPER = new Set(["ICT", "TV", "IT"]), KEEP_LOWER = new Set(["and","of","in","the","for","to","or","on","with","by","a","an","as","at","excluding","except","not","elsewhere","classified"]);
const displayTitle = s => s !== s.toUpperCase() ? s : s.toLowerCase().replace(/[a-z]+/g, (w, i) => KEEP_UPPER.has(w.toUpperCase()) ? w.toUpperCase() : i && KEEP_LOWER.has(w) ? w : w[0].toUpperCase() + w.slice(1));

function assertRelease(data) {
  if (data.schema !== "trabaholens-site-payload/2" || !Array.isArray(data.occupations) || !Array.isArray(data.wage_references)) throw Error("Unsupported release schema");
  const required = ["derivation_class", "source_authority", "confidence_grade", "source_id", "source_url", "source_file_hash", "retrieved_at", "reference_period", "source_granularity", "display_granularity"];
  const inspect = metric => {
    if (metric.availability === "published") {
      if (!validValue(metric) || metric.value < 0 || required.some(k => !metric[k])) throw Error("A published record has incomplete evidence");
      if (!/^[a-f0-9]{64}$/.test(metric.source_file_hash)) throw Error("Invalid source hash");
    } else if (metric.value !== null) throw Error("A withheld record contains a value");
  };
  data.occupations.forEach(o => Object.values(o.metrics).forEach(inspect));
  data.wage_references.forEach(r => { inspect(r); if (r.classification_reconciliation !== "unmapped_source_native") throw Error("Unexpected wage classification"); });
  // A model score needs its run, versions, attempt counts and review state, or it is not shown.
  const scoreFields = ["model_id", "rubric_version", "prompt_version", "scoring_date", "human_review_status", "raw_response_reference", "task_source"];
  data.occupations.forEach(o => (o.exposure || []).forEach(e => {
    if (e.score === null) return;
    if (!Number.isFinite(e.score) || e.score < 0 || e.score > 5 || scoreFields.some(k => !e[k])) throw Error("An exposure score has incomplete provenance");
    if (!(e.successful_attempts >= 2) || !(e.attempted_attempts >= e.successful_attempts)) throw Error("An exposure score has fewer than two successful attempts");
    if (o.level !== "psoc_unit_group") throw Error("Exposure scores are only published for PSOC unit groups");
  }));
}

const median = values => { const s = [...values].sort((a,b)=>a-b), m = s.length >> 1; return s.length % 2 ? s[m] : (s[m-1]+s[m])/2; };
function neighbourContext(code) {
  const peers = payload.occupations.filter(o => o.level === "psoc_unit_group" && o.psoc_code !== code && o.psoc_code.slice(0,3) === code.slice(0,3))
    .map(o => (o.exposure || []).find(e => e.dimension === "A" && e.score !== null)).filter(Boolean).map(e => e.score);
  return peers.length ? {minor:code.slice(0,3), n:peers.length, median:median(peers)} : null;
}

function buildRecords() {
  const majors = new Map(payload.occupations.filter(o => o.level === "psoc_major_group").map(o => [o.psoc_code, displayTitle(o.title)]));
  const psaEmployment = new Map(payload.occupations.filter(o => o.metrics.employment_count && validValue(o.metrics.employment_count)).map(o => [o.psoc_code, o.metrics.employment_count.value]));
  for (const key of ["employment", "ofw", "detail", "earnings", "education", "vulnerable"]) {
    const level = MODES[key].level || "psoc_major_group", detail = level !== "psoc_major_group";
    records[key] = payload.occupations.filter(o => o.level === level && o.metrics[MODES[key].metric]).map(o => ({
      ...o.metrics[MODES[key].metric], id:`${o.occupation_id}:${key}`, title:displayTitle(o.title), code:o.psoc_code,
      category: detail ? o.psoc_major : o.psoc_code, categoryLabel: detail ? (majors.get(o.psoc_major) || o.psoc_major) : displayTitle(o.title),
      // Box area for earnings and education follows PSA employment of the same
      // group, as in the reference design; colour is the layer's own value.
      areaWeight: MODES[key].areaFrom ? psaEmployment.get(o.psoc_code) : undefined,
      meanEarnings: key === "earnings" ? o.metrics.earnings_monthly_mean : undefined}));
  }
  records.wages = payload.wage_references.map(r => ({...r, id:r.observation_id, title:r.source_occupation, code:r.source_code, category:r.industry_code, categoryLabel:r.industry}));
  const coverage = payload.exposure_coverage || {}, noTasks = new Set((coverage.unit_groups_without_psa_tasks || []).map(u => u.psoc_code));
  records.exposure = payload.occupations.filter(o => o.level === "psoc_unit_group").map(o => {
    const a = (o.exposure || []).find(e => e.dimension === "A" && e.score !== null), b = (o.exposure || []).find(e => e.dimension === "B" && e.score !== null);
    const base = {id:`${o.occupation_id}:exposure`, title:displayTitle(o.title), code:o.psoc_code, category:o.psoc_major, categoryLabel:majors.get(o.psoc_major) || o.psoc_major,
      source_id:"llm_scoring", derivation_class:"model_derived", source_authority:"project_generated", source_granularity:"psoc_unit_group", display_granularity:"psoc_unit_group",
      task_source:coverage.task_source, task_source_file_hash:coverage.task_source_file_hash, source_url:coverage.task_source_url, unit:"median task score, 0–5 ordinal"};
    // A group without a score keeps value null (never filled from siblings). Its
    // scored neighbours are shown beside it as context, labelled as such.
    if (!a) return {...base, value:null, availability: noTasks.has(o.psoc_code) ? "no_psa_tasks" : "not_scored", reference_period:"", context:neighbourContext(o.psoc_code)};
    return {...base, value:a.score, availability:"published", reference_period:a.scoring_date.slice(0,10), retrieved_at:a.scoring_date, confidence_grade:`evidence ${a.evidence_confidence} / 5`,
      model_id:a.model_id, model_provider:a.model_provider, rubric_version:a.rubric_version, prompt_version:a.prompt_version, human_review_status:a.human_review_status,
      raw_response_reference:a.raw_response_reference, attempted_attempts:a.attempted_attempts, successful_attempts:a.successful_attempts, temperature:a.temperature,
      tasks_included:a.tasks_included, tasks_total_for_occupation:a.tasks_total_for_occupation, partial_coverage:a.partial_coverage,
      score_iqr_lower:a.score_iqr_lower, score_iqr_upper:a.score_iqr_upper, score_distribution:a.score_distribution, run_disagreement_range:a.run_disagreement_range,
      stability:a.stability, human_interaction_median:b ? b.score : null, notes:a.limitations};
  });
}

function squarify(items, x, y, width, height) {
  if (!items.length || width <= 0 || height <= 0) return [];
  const results = []; let remaining = [...items], w = width, h = height;
  while (remaining.length) {
    const total = remaining.reduce((s,r)=>s+r.weight,0), vertical = w >= h, side = vertical ? h : w, depth = vertical ? w : h;
    const aspect = (group,sum) => { const thickness=depth*sum/total; return Math.max(...group.map(r=>{const length=side*r.weight/sum; return Math.max(thickness/length,length/thickness);})); };
    let row=[remaining[0]], sum=row[0].weight;
    for (let i=1;i<remaining.length;i++) { const candidate=[...row,remaining[i]], next=sum+remaining[i].weight; if (aspect(candidate,next)>aspect(row,sum)) break; row=candidate; sum=next; }
    const thickness=depth*sum/total; let offset=0;
    for (const r of row) { const length=side*r.weight/sum; results.push({...r,x:vertical?x:x+offset,y:vertical?y+offset:y,w:vertical?thickness:length,h:vertical?length:thickness}); offset+=length; }
    if(vertical){x+=thickness;w-=thickness;}else{y+=thickness;h-=thickness;}
    remaining=remaining.slice(row.length);
  }
  return results;
}

function exportCSV() {
  // Export exactly the filtered records, including nulls and full provenance.
  const fields=mode === "exposure"
    ? ["id","title","code","category","categoryLabel","value","unit","availability","score_iqr_lower","score_iqr_upper","human_interaction_median","tasks_included","tasks_total_for_occupation","partial_coverage","attempted_attempts","successful_attempts","run_disagreement_range","stability","confidence_grade","model_provider","model_id","rubric_version","prompt_version","temperature","reference_period","human_review_status","task_source","task_source_file_hash","raw_response_reference","derivation_class","source_authority","notes"]
    : ["id","title","code","category","categoryLabel","value","unit","availability","reference_period","population_scope","derivation_class","source_authority","confidence_grade","standard_error","coefficient_of_variation","uncertainty_lower","uncertainty_upper","source_id","source_url","source_file_hash","retrieved_at","source_table","source_granularity","display_granularity","notes"];
  const cell=value=>{let s=value===null||value===undefined?"":String(value);if(/^[\s]*[=+@-]/.test(s))s="'"+s;return '"'+s.replaceAll('"','""')+'"';};
  const csv=[fields.map(cell).join(","),...filtered.map(r=>fields.map(k=>cell(r[k])).join(","))].join("\r\n");
  const url=URL.createObjectURL(new Blob(["\uFEFF",csv],{type:"text/csv;charset=utf-8"})), a=node("a");a.href=url;a.download=`trabaholens-${mode}-source-records.csv`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}

// Overview charts count the selected source records, never allocated workers.
function summariseOverview(key, rows) {
  const usable=rows.filter(validValue);
  if(!usable.length)return {available:false,published:0,withheld:rows.length};
  const values=usable.map(r=>r.value), lo=Math.min(...values), hi=Math.max(...values);
  const scores=key==="exposure" ? [...new Set([...Array.from({length:11},(_,i)=>i/2),...values])].sort((a,b)=>a-b) : null;
  const bins=scores ? scores.map(score=>({lower:score,upper:score,count:values.filter(v=>v===score).length}))
    : Array.from({length:hi===lo?1:5},(_,i)=>({lower:lo+(hi-lo)*i/5,upper:hi===lo?hi:lo+(hi-lo)*(i+1)/5,count:0}));
  if(!scores)for(const value of values){const index=hi===lo?0:Math.min(4,Math.floor((value-lo)/(hi-lo)*5));bins[index].count++;}
  const tiers=key==="exposure" ? [
    {label:"Low · ≤ 1",count:values.filter(v=>v<=1).length,position:.1},
    {label:"Middle · > 1 to < 4",count:values.filter(v=>v>1&&v<4).length,position:.5},
    {label:"High · ≥ 4",count:values.filter(v=>v>=4).length,position:.9}
  ] : [];
  const taskCountsKnown=key==="exposure"&&usable.every(r=>Number.isFinite(r.tasks_included)&&Number.isFinite(r.tasks_total_for_occupation));
  const tasks=taskCountsKnown ? {included:usable.reduce((s,r)=>s+r.tasks_included,0),listed:usable.reduce((s,r)=>s+r.tasks_total_for_occupation,0)} : null;
  return {available:true,published:usable.length,withheld:rows.length-usable.length,bins,tiers,tasks};
}

// Deployed visual shell; source-native populations remain separate throughout.
// Interaction constants and thresholds follow the deployed page's script so
// hover, tap, zoom and label behaviour match; only the data semantics differ.
const UNAVAILABLE = {
  outlook: "Posting demand is unavailable: no verified job-posting dataset has been acquired. It is not an employment forecast.",
  informal: "Informal employment is unavailable: neither PSA nor ILOSTAT publishes a Philippine series by occupation. The related own-account and family work share is its own layer and is not informality."
};
const ZOOM_MIN = 1, ZOOM_MAX = 6;
let rects = [], hovered = null, selected = null, panX = 0, panY = 0, width = 0, height = 0, returnFocus = null, keyIndex = -1;
let wheelTarget = 0, compactLayout = false, gap = 1.5, zoomFrame = null, drawQueued = false, suppressClick = false, clickTimer = null, lastTap = null;
let isPanning = false, lastPan = null, pinch = null, colourRange = null;
const canvas = $("canvas"), ctx = canvas.getContext("2d"), pointers = new Map();
const visibleRecords = () => records[mode] || [];
const panelOpen = () => $("riskPanel").classList.contains("visible");
const reducedMotion = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const isCompactLayout = () => window.matchMedia("(max-width: 820px)").matches || window.matchMedia("(pointer: coarse)").matches;
function hideTooltip() { $("tooltip").classList.remove("visible"); $("tooltip").setAttribute("aria-hidden","true"); }
function requestDraw() { if (drawQueued) return; drawQueued = true; requestAnimationFrame(() => { drawQueued = false; draw(); }); }
function saveSetting(key, value) { try { localStorage.setItem(key, value); } catch {} }
function loadSetting(key) { try { return localStorage.getItem(key); } catch { return null; } }

// Colour encodes the layer's own published value. Survey layers use slate-to-sand
// so they stay visually distinct from the model-derived exposure scale. Exposure uses the
// fixed 0-5 rubric scale rather than the observed range, so a colour means
// the same score in every filter and every future run.
// Every layer uses the green > amber > red scale of Andrej Karpathy's US Job
// Market Visualizer (karpathy.ai/jobs): the same stops and the same contrast
// boost. Exposure runs green (little task exposure) to red (most). For the other
// layers green is the high end, as in the reference; own-account work is the one
// layer where high is red. The colour only orders a value. It is not a verdict,
// and the text beside it never frames exposure as risk or job loss.
const boostContrast = t => { const c = (t - .5) * 2; return Math.sign(c) * Math.pow(Math.abs(c), .55) / 2 + .5; };
function greenRed(t) {
  t = boostContrast(Math.max(0, Math.min(1, t)));
  if (t < .5) { const k = t / .5; return [Math.round(30 + k * 200), Math.round(180 - k * 20), Math.round(40 - k * 20)]; }
  const k = (t - .5) / .5; return [Math.round(230 + k * 25), Math.round(160 - k * 130), Math.round(20 - k * 5)];
}
// Counts and pay are heavily skewed, so colour follows their logarithm (as the
// reference does for pay); otherwise a few large groups would decide every colour.
const LOG_MODES = new Set(["wages", "employment", "detail", "ofw", "earnings"]);
const scaleValue = n => LOG_MODES.has(mode) && n > 0 ? Math.log(n) : n;
const HIGH_IS_RED = new Set(["exposure", "vulnerable"]);
function colourAt(t, alpha) {
  const [r, g, b] = greenRed(HIGH_IS_RED.has(mode) ? t : 1 - t);
  return `rgba(${r},${g},${b},${alpha})`;
}
function normalised(r) {
  if (!validValue(r) || !colourRange) return 0;
  const [lo, hi] = colourRange; return hi === lo ? .5 : Math.max(0, Math.min(1, (scaleValue(r.value) - lo) / (hi - lo)));
}
function tileColour(r, alpha) {
  if (!validValue(r)) return `rgba(128,128,128,${alpha * .18})`;
  const [lo, hi] = colourRange; return colourAt(hi === lo ? .5 : (scaleValue(r.value)-lo)/(hi-lo), alpha);
}

function selectMode(key) {
  if (!MODES[key] && !UNAVAILABLE[key]) key = "employment";
  if (panelOpen()) closeDetail();
  mode = key; page = 0; selected = hovered = null; resetZoom(false);
  $("search").value = "";
  $("industryFilter").replaceChildren(new Option(mode === "wages" ? "All industries" : "All groups", "all"));
  const groups = new Map(visibleRecords().map(r => [r.category, r.categoryLabel]));
  for (const [code, label] of [...groups].sort((a,b)=>a[0].localeCompare(b[0]))) $("industryFilter").append(new Option(`${code} · ${label}`, code));
  const savedFilter = loadSetting(`trabaholens_verified_filter_${mode}`);
  if (savedFilter && groups.has(savedFilter)) $("industryFilter").value = savedFilter;
  $("filterLabel").textContent = mode === "wages" ? "Industry (source grouping)" : "Occupation Group";
  document.querySelectorAll("#colorToggle button").forEach(b => { b.classList.toggle("active", b.dataset.mode === mode); b.setAttribute("aria-pressed",String(b.dataset.mode === mode)); });
  $("layerDesc").textContent = MODES[mode] ? `${MODES[mode].description} ${MODES[mode].encoding}` : UNAVAILABLE[mode];
  saveSetting("trabaholens_layer_v2", mode);
  canvas.classList.add("switching");
  update();
  requestAnimationFrame(() => requestAnimationFrame(() => canvas.classList.remove("switching")));
}

// Plain-language explanations are presentation of the existing rubric and metadata.
const SCORE_GUIDE = [
  ["No meaningful applicability", "The task depends on physical presence, handling or real-world sensing that generative AI does not provide."],
  ["Minor assistance", "AI may assist with peripheral parts, such as drafting a note. The core task stays unchanged."],
  ["A meaningful slice", "AI may draft or check a recognisable minority of the task’s content. Most remains outside that assistance."],
  ["Substantial assistance", "AI may accelerate substantial parts of the task, while people remain central to carrying it out."],
  ["Much of the content", "AI may perform or transform much of the task’s content with human oversight, judgement and verification."],
  ["Most of the content", "AI may perform most of the task’s content under realistic conditions. Verification, accountability and integration still matter."]
];
const STAT_HELP = {
  "Occupations scored":"PSOC unit groups with a published task-exposure score, out of all groups in the current view. A unit group can contain several job titles; it is not a count of workers.",
  "Median task score":"Each occupation group has a median task score. This figure is the middle of those group scores in the current view. Groups count equally; it is not weighted by employment or task count.",
  "High exposure":"The number of shown unit groups with a median technical task-exposure score of at least 4 out of 5. This is a rubric threshold, not a percentage of workers.",
  "Low exposure":"The number of shown unit groups with a median technical task-exposure score of at most 1 out of 5. These groups still need their own task evidence; a low score is not a forecast.",
  "Tasks scored":"PSA task statements included in the scored groups in this view. Each included task met the minimum of two successful scoring attempts.",
  "No PSA task list":"Shown PSOC groups whose PSA entries have no task list. They stay unscored. Neither a similar title nor a neighbouring group supplies a substitute score.",
  "Scoring model":"The model recorded in the published scoring run. Repeated attempts check reproducibility. Agreement between models does not establish that their judgements are correct.",
  "Expert review":"Human-review status in the published run. The scores remain experimental until appropriate independent review. Automated checks and the model’s own explanations are not independent validation."
};
let explanationTarget=null, explanationPinned=false, explanationTimer;
function hideExplanation(){
  clearTimeout(explanationTimer);if(!explanationTarget)return false;
  explanationTarget.removeAttribute("aria-describedby");explanationTarget=null;explanationPinned=false;$("explainPopover").hidden=true;return true;
}
function showExplanation(target,pin=false){
  clearTimeout(explanationTimer);
  if(explanationTarget!==target){hideExplanation();explanationTarget=target;}
  explanationPinned=pin||explanationPinned;
  const tip=$("explainPopover");tip.querySelector("strong").textContent=target.dataset.explainTitle;tip.querySelector("p").textContent=target.dataset.explanation;
  tip.hidden=false;target.setAttribute("aria-describedby","explainPopover");
  const anchor=target.getBoundingClientRect(), b=tip.getBoundingClientRect(), pad=12;
  tip.style.left=`${Math.max(pad,Math.min(anchor.left,innerWidth-b.width-pad))}px`;
  tip.style.top=`${Math.max(pad,anchor.bottom+b.height+12<=innerHeight?anchor.bottom+8:anchor.top-b.height-8)}px`;
}
function explainButton(label,explanation){
  const button=node("button",label,"explain-trigger");button.type="button";button.dataset.explainTitle=label;button.dataset.explanation=explanation;button.setAttribute("aria-label",`About ${label.toLowerCase()}`);return button;
}
function headingWithHelp(label,explanation){const heading=node("h3");heading.append(explainButton(label,explanation));return heading;}
function scoreExplorer(value=null){
  const container=node("div",undefined,"score-explorer"), options=node("div",undefined,"scale-options"), description=node("div",undefined,"scale-description");
  options.setAttribute("role","group");options.setAttribute("aria-label","Explore the technical task-exposure scale");
  description.setAttribute("aria-live","polite");
  let pinned=null;
  const describe=index=>{
    if(index===null){description.replaceChildren(node("strong",value===null?"What does a score mean?":`This group’s median is ${fmt(value,1)} / 5`),node("p","Hover, focus or tap a number to explore its meaning. Scores are ordered categories, not percentages."));}
    else{const [title,text]=SCORE_GUIDE[index];description.replaceChildren(node("strong",`${index} · ${title}`),node("p",text));}
    [...options.children].forEach((button,i)=>{button.classList.toggle("inspected",i===index);button.setAttribute("aria-pressed",String(i===pinned));});
  };
  SCORE_GUIDE.forEach(([title],i)=>{
    const button=node("button",String(i));button.type="button";button.setAttribute("aria-label",`Score ${i}: ${title}`);button.setAttribute("aria-pressed","false");
    if(value!==null&&i<=value)button.classList.add("within-score");
    button.addEventListener("pointerenter",e=>{if(e.pointerType!=="touch")describe(i);});button.addEventListener("focus",()=>describe(i));
    button.addEventListener("click",()=>{pinned=i;describe(i);});options.append(button);
  });
  options.addEventListener("pointerleave",()=>describe(pinned));
  options.addEventListener("focusout",e=>{if(!options.contains(e.relatedTarget))describe(pinned);});
  container.append(options,description);describe(null);return container;
}
function selectProfileTab(key,focus=false){
  hideExplanation();
  for(const button of $("profileTabs").querySelectorAll("button")){
    const active=button.dataset.profileTab===key;button.setAttribute("aria-selected",String(active));button.tabIndex=active?0:-1;
    $(button.getAttribute("aria-controls")).hidden=!active;
    if(active&&focus)button.focus({preventScroll:true});
  }
  $("riskPanel").querySelector(".risk-body").scrollTop=0;
}
let overviewData=null;
function overviewValue(value){
  if(["wages","earnings"].includes(mode))return `₱${compact(value)}`;
  if(["education","vulnerable","ofw"].includes(mode))return `${fmt(value*100,1)}%`;
  return compact(value);
}
function chartRow(label,value,fraction,colour,explanation){
  const row=node("div",undefined,"overview-bar-row"), heading=explainButton(label,explanation);heading.classList.add("chart-trigger");
  const track=node("div",undefined,"overview-track"),fill=node("span");fill.style.width=`${Math.max(0,Math.min(1,fraction))*100}%`;fill.style.background=colour;track.append(fill);
  row.append(heading,node("strong",value),track);return row;
}
function explainOverviewHeadings(){
  for(const prefix of ["distribution","breakdown","coverage"]){
    const title=$(prefix+"Title"),label=title.textContent;title.replaceChildren(explainButton(label,$(prefix+"Caption").textContent));
  }
}
function renderOverview(){
  overviewData=summariseOverview(mode,filtered);
  for(const id of ["distributionPlot","breakdownPlot","coveragePlot"])$(id).replaceChildren();
  $("distributionTitle").textContent=mode==="exposure"?"Groups by task exposure":"Distribution of source values";
  $("breakdownTitle").textContent=mode==="exposure"?"Exposure tiers":"Selected source references";
  $("coverageTitle").textContent=mode==="exposure"?"PSA task coverage":"Record coverage";
  if(!overviewData.available){
    for(const id of ["distributionPlot","breakdownPlot","coveragePlot"])$(id).append(node("div","No published values for this view","chart-empty"));
    $("distributionCaption").textContent=UNAVAILABLE[mode]||"Try changing the search or group filter.";
    $("breakdownCaption").textContent="A chart appears only when source values are available.";
    $("coverageCaption").textContent="Missing values are not shown as zero.";explainOverviewHeadings();return;
  }
  const max=Math.max(...overviewData.bins.map(b=>b.count)), histogram=node("div",undefined,"overview-histogram");
  histogram.setAttribute("role","group");histogram.setAttribute("aria-label",$("distributionTitle").textContent);
  for(const bin of overviewData.bins){
    const label=mode==="exposure"?`Median ${fmt(bin.lower,1)}`:`${overviewValue(bin.lower)}${bin.upper===bin.lower?"":`–${overviewValue(bin.upper)}`}`;
    const countLabel=`${fmt(bin.count)} ${mode==="exposure"?"PSOC unit groups":"source records"}`;
    const column=explainButton(label,`${countLabel}. ${mode==="exposure"?"Groups count equally; these are not worker counts.":"Value ranges are display bins; records retain their original values."}`);column.classList.add("chart-column");column.setAttribute("aria-label",`${label}: ${countLabel}`);column.dataset.count=bin.count;
    const track=node("span",undefined,"chart-column-track"),fill=node("i");fill.style.height=`${max?bin.count/max*100:0}%`;
    const position=mode==="exposure"?bin.lower/5:overviewData.bins.length===1 ? .5 : overviewData.bins.indexOf(bin)/(overviewData.bins.length-1);fill.style.background=colourAt(position,.85);track.append(fill);
    const tick=node("span",mode==="exposure"?fmt(bin.lower,1):"","chart-tick");column.replaceChildren(node("strong",fmt(bin.count)),track,tick);histogram.append(column);
  }
  $("distributionPlot").append(histogram);
  if(mode!=="exposure"){
    const axis=node("div",undefined,"chart-axis");axis.append(node("span",overviewValue(overviewData.bins[0].lower)),node("span",overviewValue(overviewData.bins.at(-1).upper)));$("distributionPlot").append(axis);
  }
  $("distributionCaption").textContent=mode==="exposure"?"PSOC unit groups, not workers. Half-point medians are retained.":mode==="wages"?"Job-position × industry records, not national occupation pay.":"Each source group counts once. Bins are not weighted by employment.";
  if(mode==="exposure"){
    for(const tier of overviewData.tiers)$("breakdownPlot").append(chartRow(tier.label,fmt(tier.count),tier.count/overviewData.published,colourAt(tier.position,.85),`${tier.count} shown groups in this median-score tier. Each group counts once; these are not workers.`));
    $("breakdownCaption").textContent="The tiers partition scored groups; unscored groups are excluded.";
  }else{
    const top=filtered.filter(validValue).slice().sort((a,b)=>b.value-a.value).slice(0,4),largest=top[0].value;
    for(const row of top)$("breakdownPlot").append(chartRow(row.title,overviewValue(row.value),largest>0?row.value/largest:0,tileColour(row,.85),`${row.title}${mode==="wages"?` · ${row.categoryLabel}`:""}: ${displayValue(row)}. ${sourceName(row)}.`));
    $("breakdownCaption").textContent=mode==="wages"?"Largest shown wage references. Industry slices remain separate.":mode==="education"?"Tertiary attainment among employed people, not entry requirements.":"Four largest shown values. Select a map box for its source.";
  }
  if(mode==="exposure"&&overviewData.tasks){
    const {included,listed}=overviewData.tasks;
    $("coveragePlot").append(chartRow("Included in scores",fmt(included),listed?included/listed:0,"#b8c2aa","PSA task statements with the required successful scoring attempts in these shown scored groups."),chartRow("Excluded tasks",fmt(listed-included),listed?(listed-included)/listed:0,"#777b85","Listed tasks excluded from these scores. They do not receive substitute values."));
    $("coverageCaption").textContent="Listed PSA tasks in the shown scored groups; task counts do not indicate employment.";
  }else if(mode==="exposure"){
    $("coveragePlot").append(node("div","Task counts are not supplied for this view","chart-empty"));$("coverageCaption").textContent="No task counts inferred.";
  }else{
    const total=filtered.length;
    $("coveragePlot").append(chartRow("Published",fmt(overviewData.published),overviewData.published/total,"#b8c2aa","Source records with a published value in the current view."),chartRow("Withheld / missing",fmt(overviewData.withheld),overviewData.withheld/total,"#777b85","Source records retained without a published value. They are not counted as zero-valued observations."));
    $("coverageCaption").textContent=mode==="detail"?"ILO-processed LFS. Its totals differ from PSA’s published groups.":MODES[mode].note;
  }
  explainOverviewHeadings();
}
function update() {
  hideTooltip(); hideExplanation(); hovered = null;
  const query = $("search").value.trim().toLocaleLowerCase(), category = $("industryFilter").value;
  filtered = visibleRecords().filter(r => (category === "all" || r.category === category) && `${r.title} ${r.code} ${r.categoryLabel}`.toLocaleLowerCase().includes(query));
  filtered.sort((a,b) => (b.value ?? -Infinity) - (a.value ?? -Infinity) || a.id.localeCompare(b.id));
  const usable = filtered.filter(validValue), withheld = filtered.length - usable.length;
  $("resultCount").textContent = UNAVAILABLE[mode] ? "Layer unavailable" : mode === "exposure" ? `${fmt(usable.length)} scored · ${fmt(withheld)} without a score` : `${fmt(usable.length)} available · ${fmt(withheld)} withheld / missing`;
  $("industryFilterNote").replaceChildren(explainButton("Reading this layer",UNAVAILABLE[mode] || MODES[mode].note));
  $("statTotalHeading").textContent = mode === "exposure" ? "Occupations scored" : mode === "employment" ? "Employed persons" : mode === "detail" ? "Employed persons (ILO)" : mode === "earnings" ? "Median monthly pay" : mode === "education" ? "Advanced education" : mode === "vulnerable" ? "Own-account / family" : mode === "ofw" ? "OFW distribution" : "Available source records";
  $("statTotalJobs").textContent = mode === "exposure" ? `${fmt(usable.length)}/${fmt(filtered.length)}` : !usable.length ? "—" : mode === "employment" || mode === "detail" ? compact(usable.reduce((s,r)=>s+r.value,0)) : mode === "earnings" ? `₱${compact(median(usable.map(r=>r.value)))}` : mode === "education" || mode === "vulnerable" ? `${fmt(median(usable.map(r=>r.value))*100,0)}%` : mode === "ofw" ? `${fmt(usable.reduce((s,r)=>s+r.value,0)*100,3)}%` : fmt(usable.length);
  $("statTotalLabel").textContent = UNAVAILABLE[mode] ? "no validated values" : mode === "exposure" ? "PSOC unit groups shown" : mode === "employment" ? "sum of shown group estimates" : mode === "detail" ? "sum of shown ILO sub-group counts" : mode === "earnings" ? "median across shown groups, employees only" : mode === "education" || mode === "vulnerable" ? "median share across shown groups" : mode === "ofw" ? "of all survey OFWs; not renormalised" : "occupation × industry records";
  const cv = usable.filter(r=>Number.isFinite(r.coefficient_of_variation));
  const scored = (records.exposure || []).filter(validValue);
  const exposureBlock = scored.length ? ["AI task exposure", "Model-estimated", `${fmt(scored.length)} unit groups scored`] : ["AI task exposure", "Not scored", "no accepted scoring run"];
  const stats = mode === "exposure" ? [
    ["Median task score", usable.length ? `${fmt(median(usable.map(r=>r.value)),1)}/5` : "—", "unweighted across shown groups"],
    ["High exposure", usable.length ? fmt(usable.filter(r=>r.value>=4).length) : "—", "unit groups with median ≥ 4"],
    ["Low exposure", usable.length ? fmt(usable.filter(r=>r.value<=1).length) : "—", "unit groups with median ≤ 1"],
    ["Tasks scored", usable.length ? fmt(usable.reduce((s,r)=>s+(r.tasks_included||0),0)) : "—", "PSA task statements"],
    ["No PSA task list", fmt(filtered.filter(r=>r.availability==="no_psa_tasks").length), "never given a borrowed score"],
    ["Scoring model", usable.length ? [...new Set(usable.map(r=>r.model_id))].join(", ") : "—", "≥ 2 successful attempts per task"],
    ["Expert review", usable.some(r=>r.human_review_status==="human_reviewed") ? "Partial" : "Not yet", "scores are model estimates"]
  ] : [
    ["Reference period", usable.length ? [...new Set(usable.map(r=>r.reference_period))].join("; ") : "—", "historical, not live counts"],
    ["Resolution", UNAVAILABLE[mode] ? "—" : mode === "wages" ? "Source-native" : mode === "detail" ? "Sub-major group" : "Major group", UNAVAILABLE[mode] ? "no validated values" : mode === "wages" ? "not reconciled to PSOC" : mode === "detail" ? "ILO two-digit ISCO-08 = PSOC" : "no detailed counts inferred"],
    ["Matching records", UNAVAILABLE[mode] ? "—" : fmt(filtered.length), "incl. withheld / missing"],
    ["Precision cautions", cv.length ? fmt(cv.filter(r=>r.coefficient_of_variation>10).length) : "Not assessed", "CV above 10%"],
    ["Withheld / missing", UNAVAILABLE[mode] ? "—" : fmt(withheld), "never filled with zero"],
    exposureBlock,
    ["Release status", "Research preview", "independent review pending"]
  ];
  const totalTitle=$("statTotalHeading").textContent;
  $("statTotalHeading").replaceChildren(explainButton(totalTitle,STAT_HELP[totalTitle]||`${MODES[mode]?.description||UNAVAILABLE[mode]} ${$("statTotalLabel").textContent}.`));
  // Four main measures; supporting evidence remains in a labelled disclosure.
  stats.forEach(([title,value,note],i)=>{const block=$("block"+(i+2));block.replaceChildren(headingWithHelp(title,mode === "exposure" ? STAT_HELP[title] : `${note}. ${MODES[mode]?.note||UNAVAILABLE[mode]}`),node("div",value,/^[\d.,%₱KMB—/]+$/.test(value)?"stat-big":"stat-big stat-text"),node("div",note,"stat-label"));});
  $("download").disabled = !filtered.length;
  $("canvas").hidden = tableMode;
  $("tableView").hidden = !tableMode;
  // The colour range spans the whole layer, not the filter, so a box keeps its
  // colour when the filter changes, matching the fixed legend.
  const vals = visibleRecords().filter(validValue).map(r=>r.value);
  colourRange = mode === "exposure" ? [0, 5] : vals.length ? [Math.min(...vals.map(scaleValue)), Math.max(...vals.map(scaleValue))] : [0, 0];
  const legendValue = n => mode === "wages" || mode === "earnings" ? `₱${compact(n)}` : mode === "education" || mode === "vulnerable" ? `${fmt(n*100,0)}%` : mode === "ofw" ? `${fmt(n*100,2)}%` : compact(n);
  $("legendLow").textContent = mode === "exposure" ? (vals.length ? "0 · little task exposure" : "Not scored") : vals.length ? legendValue(Math.min(...vals)) : "Unavailable";
  $("legendHigh").textContent = mode === "exposure" ? (vals.length ? "5 · most task content" : "") : vals.length ? legendValue(Math.max(...vals)) : "";
  const legend = $("gradientLegend").getContext("2d");
  for (let x = 0; x < 80; x++) { legend.fillStyle = colourAt(x/79, 1); legend.fillRect(x,0,1,8); }
  $("gradientLegend").hidden = !vals.length;
  $("legendSteps").hidden = mode!=="exposure"||!vals.length;
  renderOverview();
  if (tableMode) renderTable(); else layout();
}

function layout() {
  const prevW = width || 1, prevH = height || 1;
  compactLayout = isCompactLayout();
  width = $("wrapper").clientWidth;
  height = compactLayout ? Math.max(Math.round(width * 1.18),480) : Math.round(width * 3 / 4);
  const dpr = window.devicePixelRatio || 1, margin = compactLayout ? 8 : 12;
  gap = compactLayout ? 1 : 1.5;
  canvas.width = width*dpr; canvas.height = height*dpr;
  canvas.style.width = `${width}px`; canvas.style.height = `${height}px`;
  // Wages are equal-area and never imply worker counts. Exposure area is the cube of
  // the PSA task statements listed for the group (published count, stretched so
  // differences show; not employment); groups
  // with no list or no score get the minimum box. Unscored groups are drawn faint.
  const equalArea = mode === "wages";
  const items = filtered.filter(r=>mode === "exposure" || (validValue(r) && (mode === "wages" || (r.areaWeight ?? r.value)>0))).map(r=>({...r,weight:equalArea ? 1 : mode === "exposure" ? Math.max(1, r.tasks_total_for_occupation || 0) ** 3 : (r.areaWeight ?? r.value)}));
  // Group source-native wage records by their published industry, never by a
  // guessed PSOC match. Employment and SOF remain separate major-group maps.
  const groups = new Map();
  for (const r of items) { if(!groups.has(r.category)) groups.set(r.category,[]);groups.get(r.category).push(r); }
  const parents = [...groups].map(([id,children])=>({id,children,weight:children.reduce((s,r)=>s+r.weight,0)})).sort((a,b)=>b.weight-a.weight || a.id.localeCompare(b.id));
  // Same nesting as Karpathy's visualizer: each major group is inset by the gap
  // and each box by half the gap, so group edges are 3x the gutter between boxes.
  rects = squarify(parents,margin,margin,width-2*margin,height-2*margin).flatMap(g=>squarify(g.children,g.x+gap,g.y+gap,g.w-2*gap,g.h-2*gap));
  keyIndex = -1;
  if (zoom > 1) { panX *= width/prevW; panY *= height/prevH; }
  clampPan(); draw();
}
function clampPan() { if (zoom <= 1) { zoom = 1; panX = panY = 0; return; } panX=Math.max(width*(1-zoom),Math.min(0,panX));panY=Math.max(height*(1-zoom),Math.min(0,panY)); }
function draw() {
  drawQueued = false;
  const dpr = window.devicePixelRatio || 1;
  ctx.setTransform(dpr,0,0,dpr,0,0);ctx.fillStyle="#0a0a0f";ctx.fillRect(0,0,width,height);
  if(!rects.length){ctx.fillStyle="#888894";ctx.font="14px system-ui";ctx.fillText(UNAVAILABLE[mode] ? "This layer has no validated values. See the explanation above." : "No matching published values. Try clearing the filter.",16,40);return;}
  const g = gap/2, textScale = zoom > 1 ? Math.min(1.8, 1+(zoom-1)*.22) : 1;
  ctx.save();ctx.translate(panX,panY);ctx.scale(zoom,zoom);
  for (const r of rects) {
    const x=r.x+g,y=r.y+g,w=r.w-2*g,h=r.h-2*g;if(w<=0||h<=0)continue;
    const isSelected = selected?.id===r.id, isHovered = hovered?.id===r.id;
    ctx.fillStyle=tileColour(r, isHovered ? .8 : isSelected ? .7 : .5);ctx.fillRect(x,y,w,h);
    if(!validValue(r)&&mode==="exposure"){ctx.save();ctx.strokeStyle="rgba(255,255,255,.22)";ctx.lineWidth=1/zoom;ctx.setLineDash([4/zoom,3/zoom]);ctx.strokeRect(x+.5/zoom,y+.5/zoom,w-1/zoom,h-1/zoom);ctx.restore();}
    if(isSelected||isHovered){ctx.strokeStyle="#fff";ctx.lineWidth=2/zoom;ctx.strokeRect(x,y,w,h);}
  }
  ctx.restore();
  for (const r of rects) {
    const sx=(r.x+g)*zoom+panX, sy=(r.y+g)*zoom+panY, sw=(r.w-2*g)*zoom, sh=(r.h-2*g)*zoom;
    if (sw < (compactLayout ? 42 : 50) || sh < (compactLayout ? 20 : 18) || sx > width || sy > height || sx+sw < 0 || sy+sh < 0) continue;
    // Text sizing and clipping follow the reference: the title is clipped at the
    // box edge rather than shortened with an ellipsis, so every box shows as much
    // of its name as fits.
    const size = Math.min(13, Math.max(9, Math.min(sw/10, sh/3))) * textScale;
    const titleFont=`500 ${size}px -apple-system, system-ui, sans-serif`, subFont=`400 ${Math.max(8,size-2)}px -apple-system, system-ui, sans-serif`;
    const inner=Math.max(0,sw-10), isOn=hovered?.id===r.id;
    ctx.save();
    ctx.beginPath();ctx.rect(sx+4,sy+2,inner,Math.max(0,sh-4));ctx.clip();
    ctx.textBaseline="top";ctx.font=titleFont;ctx.fillStyle=!validValue(r)?"rgba(255,255,255,0.4)":isOn?"#fff":"rgba(255,255,255,0.85)";
    ctx.fillText(r.title,sx+5,sy+4);
    if (sh > (compactLayout ? 30 : 34) && sw > (compactLayout ? 52 : 60)) {
      ctx.font=subFont;ctx.fillStyle="rgba(255,255,255,0.5)";ctx.fillText(displayValue(r),sx+5,sy+4+size+2);
      if (zoom >= 2 && sh > 56) {
        const detailFont=`400 ${Math.max(8,size-3)}px -apple-system, system-ui, sans-serif`, line=gradeLabel(r);
        ctx.font=detailFont;ctx.fillStyle="rgba(255,255,255,0.46)";
        ctx.fillText(line,sx+5,sy+4+size+2+Math.max(11,size-1));
      }
    }
    ctx.restore();
  }
}
function hit(clientX, clientY) {
  const b=canvas.getBoundingClientRect(), x=(clientX-b.left-panX)/zoom, y=(clientY-b.top-panY)/zoom;
  for (let i=rects.length-1;i>=0;i--){const r=rects[i];if(x>=r.x&&x<r.x+r.w&&y>=r.y&&y<r.y+r.h)return r;}
  return null;
}
function precisionText(r) {
  if (!validValue(r)) return "—";
  const cv = Number.isFinite(r.coefficient_of_variation) ? `CV ${fmt(r.coefficient_of_variation,1)}%` : "";
  const se = r.standard_error === null || r.standard_error === undefined ? "" : mode === "ofw" ? `SE ${fmt(r.standard_error*100,2)} pp` : mode === "wages" ? `SE ₱${fmt(r.standard_error,0)}` : `SE ${fmt(r.standard_error)}`;
  return [se, cv].filter(Boolean).join(" · ") || "Not supplied";
}
// Rebuild the preview only when the record changes; pointer movement only positions it.
let tooltipRecord = null, tooltipSize = null;
function sourceName(r) {
  if(r.source_id?.startsWith("ilostat_")) return "ILOSTAT · Philippine LFS";
  return {psa_lfs:"PSA · Labor Force Survey",psa_sof:"PSA · Survey on Overseas Filipinos",psa_ows:"PSA · Occupational Wages Survey"}[r.source_id] || r.source_id || "Not supplied";
}
function evidenceLabel(r) {
  if(!validValue(r)) return "No published value";
  if(mode === "exposure") return "Experimental model estimate";
  return [r.derivation_class_label||r.derivation_class, "statistic"].join(" ");
}
function recordCode(r) { return `${mode === "wages" ? "Source code" : "PSOC"} ${r.code}`; }
function scoreRail(value, label) {
  const rail=node("div",undefined,"score-rail"); rail.setAttribute("role","img");
  rail.setAttribute("aria-label",`${label}: ${fmt(value,1)} out of 5`);
  for(let i=0;i<5;i++){const segment=node("span");const fill=node("i");fill.style.width=`${Math.max(0,Math.min(1,value-i))*100}%`;segment.append(fill);rail.append(segment);}
  return rail;
}
function showTooltip(r, mx, my) {
  const tip=$("tooltip");tip.classList.toggle("compact",compactLayout);
  const changed=tooltipRecord !== r;
  if(changed){
    tooltipRecord=r;
    tip.querySelector(".tt-category").textContent=r.categoryLabel;
    tip.querySelector(".tt-title").textContent=r.title;
    tip.querySelector(".tt-percentile").textContent=recordCode(r);
    const value=node("strong",displayValue(r),"preview-value");
    const label=node("span",mode === "exposure" ? "Technical task exposure" : MODES[mode].label,"preview-label");
    tip.querySelector(".tt-exposure").replaceChildren(value,label,...(mode === "exposure" && validValue(r) ? [scoreRail(r.value,"Technical task exposure")] : []));
    const rows=mode === "exposure" ? (validValue(r) ? [["Tasks scored",`${r.tasks_included} / ${r.tasks_total_for_occupation}`],["Review","Not independently validated"]] : [["Why",r.availability === "no_psa_tasks"?"No PSA task list":"No published scoring run"]]) : [["Period",r.reference_period||"Not supplied"],["Evidence",evidenceLabel(r)]];
    tip.querySelector(".tt-stats").replaceChildren(...rows.flatMap(([label,value])=>[node("span",label,"label"),node("span",value,"value")]));
    tip.querySelector(".tt-rationale").textContent=mode === "exposure"?"Model estimate · not independently validated":"";
  }
  tip.classList.add("visible");tip.setAttribute("aria-hidden","false");
  if(compactLayout){tip.style.left="";tip.style.top="";tip.style.transform="none";tooltipSize=null;return;}
  // Cache geometry per record and move on the compositor while scanning the map.
  if(changed || !tooltipSize || tooltipSize.viewport !== `${innerWidth}:${innerHeight}`){
    const bounds=tip.getBoundingClientRect();tooltipSize={width:bounds.width,height:bounds.height,viewport:`${innerWidth}:${innerHeight}`};
  }
  const box=tooltipSize, inset=12, offset=20;
  let x=mx+offset;if(x+box.width>innerWidth-inset)x=mx-box.width-offset;
  let y=my-28;if(y+box.height>innerHeight-inset)y=innerHeight-box.height-inset;
  tip.style.left="0";tip.style.top="0";
  tip.style.transform=`translate3d(${Math.max(inset,Math.min(x,innerWidth-box.width-inset))}px,${Math.max(inset,y)}px,0)`;
}
function renderProfileVisual(r) {
  $("profileMetricLabel").textContent=mode === "exposure"?"Technical task exposure":MODES[mode].label;
  $("profileValue").textContent=displayValue(r);
  $("profileStatus").textContent=gradeLabel(r);
  $("profileVisual").replaceChildren();
  if(mode === "exposure" && validValue(r)){
    const explorer=scoreExplorer(r.value);
    const metrics=node("div",undefined,"profile-facts");
    for(const [label,value] of [["Physical presence",r.human_interaction_median===null?"—":`${fmt(r.human_interaction_median,1)} / 5`],["Task coverage",`${r.tasks_included} / ${r.tasks_total_for_occupation}`]]){const fact=node("div");fact.append(explainButton(label,label==="Physical presence"?"Median score for physical presence and in-person contact, scored independently from task exposure. It is not the inverse of the exposure score.":"Tasks scored out of the PSA task statements listed for this group. Excluded tasks do not silently receive a score."),node("strong",value));metrics.append(fact);}
    $("profileVisual").append(explorer,metrics);
  }else if(!validValue(r)){
    $("profileVisual").append(node("p",r.availability === "no_psa_tasks"?"This PSOC entry has no published PSA task list. A score cannot be supported.":"This record has no published value. See the source record for the reason.","profile-caption"));
  }else{
    const facts=node("div",undefined,"profile-facts");
    for(const [label,value] of [["Reference period",r.reference_period],["Sampling precision",precisionText(r)]]){const fact=node("div");fact.append(node("span",label),node("strong",value||"Not supplied"));facts.append(fact);}
    $("profileVisual").append(facts);
  }
  const distribution=r.score_distribution;
  $("distributionCard").hidden=mode!=="exposure"||!validValue(r)||!distribution;
  $("taskDistribution").replaceChildren();
  if(!$("distributionCard").hidden){
    const max=Math.max(...Object.values(distribution));
    for(const [score,count] of Object.entries(distribution)){
      const col=node("div",undefined,"distribution-column"),track=node("div",undefined,"distribution-track"),bar=node("div",undefined,"distribution-bar");
      bar.style.height=`${max?count/max*100:0}%`;track.append(bar);
      col.append(node("strong",String(count)),track,node("span",score));col.setAttribute("aria-label",`Score ${score}: ${count} tasks`);$("taskDistribution").append(col);
    }
  }
  $("sourceSummary").replaceChildren(...[["Source",mode === "exposure"?(validValue(r)?"PSA task statements · model-scored":"PSA · PSOC classification"):sourceName(r)],["Published at",String(r.source_granularity||"Not supplied").replaceAll("_"," ")],["Scoring model",mode === "exposure"?r.model_id:null]].filter(([,v])=>v).map(([label,value])=>{const row=node("div",undefined,"source-summary-row");row.append(node("span",label),node("strong",value));return row;}));
}
const FIELD_LABELS = {
  availability:"Availability", unit:"Unit", derivation_class:"How it was produced", source_authority:"Who produced it",
  confidence_grade:"Confidence grade", source_id:"Source", reference_period:"Reference period", standard_error:"Standard error",
  coefficient_of_variation:"Coefficient of variation", uncertainty_lower:"Interval, lower", uncertainty_upper:"Interval, upper",
  confidence_level:"Interval confidence level", source_granularity:"Published at", display_granularity:"Shown at",
  source_table:"Source table", normalised_row_id:"Source row", source_file_hash:"File fingerprint (SHA-256)", retrieved_at:"Retrieved",
  model_provider:"Model provider", model_id:"Scoring model", rubric_version:"Rubric version", prompt_version:"Prompt version",
  temperature:"Temperature", attempted_attempts:"Attempts made", successful_attempts:"Successful attempts per task",
  tasks_included:"Tasks scored", tasks_total_for_occupation:"PSA tasks listed", score_iqr_lower:"Task scores, lower quartile",
  score_iqr_upper:"Task scores, upper quartile", human_interaction_median:"Physical presence (median, 0-5)",
  run_disagreement_range:"Largest gap between attempts", stability:"Stability", human_review_status:"Expert review",
  task_source:"Task source", task_source_file_hash:"Task file fingerprint (SHA-256)", raw_response_reference:"Raw model responses"
};
function showDetail(r) {
  clearTimeout(clickTimer); hideTooltip(); hideExplanation(); selected=r;returnFocus=document.activeElement;
  $("riskPanel").querySelector(".risk-body").scrollTop=0;$("provenanceDetails").open=false;$("riskPanel").querySelector(".profile-limits").open=false;
  $("profileEyebrow").textContent=mode === "wages"?"Wage reference":"Occupation profile";renderProfileVisual(r);
  $("tabEvidence").hidden=mode!=="exposure"||!validValue(r);selectProfileTab("overview");
  $("riskTitle").textContent=r.title;
  $("riskMeta").replaceChildren(node("span",[recordCode(r),r.reference_period].filter(Boolean).join(" · ")),node("span",r.categoryLabel));
  $("riskMeaning").textContent=mode === "exposure" && !validValue(r) ? "A task-exposure score requires published task statements and at least two successful scoring attempts. This group has no published score." : r.population_scope||MODES[mode].description;
  $("detailFields").replaceChildren();
  $("taskCard").hidden = mode !== "exposure" || !validValue(r);
  if (!$("taskCard").hidden) renderTasks(r);
  const fields=mode === "exposure" ? ["availability","unit","derivation_class","source_authority","model_provider","model_id","rubric_version","prompt_version","temperature","reference_period","attempted_attempts","successful_attempts","tasks_included","tasks_total_for_occupation","score_iqr_lower","score_iqr_upper","human_interaction_median","run_disagreement_range","stability","confidence_grade","human_review_status","task_source","task_source_file_hash","raw_response_reference"] : ["availability","unit","derivation_class","source_authority","confidence_grade","source_id","reference_period","standard_error","coefficient_of_variation","uncertainty_lower","uncertainty_upper","confidence_level","source_granularity","display_granularity","source_table","normalised_row_id","source_file_hash","retrieved_at"];
  for(const key of fields){let value=r[key];if(key==="standard_error"&&value!==null&&value!==undefined&&mode==="ofw")value=`${fmt(value*100,5)} percentage points`;else if(key==="coefficient_of_variation"&&Number.isFinite(value))value=`${fmt(value,4)}%`;if(key==="derivation_class"&&r.derivation_class_label)value=r.derivation_class_label;else if(key==="source_authority"&&r.source_authority_label)value=r.source_authority_label;else if(/granularity$/.test(key)&&typeof value==="string")value=value.replaceAll("_"," ");$("detailFields").append(node("dt",FIELD_LABELS[key]||key.replaceAll("_"," ")),node("dd",value===null||value===undefined||value===""?"Not supplied":String(value)));}
  $("profileBoundary").textContent=mode === "exposure"?"Task exposure describes potential AI assistance, not employment outcomes.":"See Source for coverage, sampling precision and limitations.";
  $("detailNotes").textContent=[MODES[mode].note,r.notes,...(r.confidence_reasons||[])].filter(Boolean).join(" ");
  let url;try{url=new URL(r.source_url);}catch{}$("detailSource").hidden=!url||url.protocol!=="https:";if(!$("detailSource").hidden)$("detailSource").href=url.href;
  $("riskPanel").inert=false;$("riskPanel").setAttribute("aria-hidden","false");$("riskPanel").classList.add("visible");$("riskOverlay").classList.add("visible");$("wrapper").inert=true;document.body.classList.add("detail-open");$("riskClose").focus({preventScroll:true});requestDraw();
}
let taskEvidence = null;
async function renderTasks(r) {
  const list = $("taskList"), caption = $("taskCaption");
  list.replaceChildren(); caption.textContent = "Loading task evidence…";
  try {
    const file = payload.exposure_coverage?.task_evidence_file;
    if (!file) throw Error("no task evidence file in this release");
    taskEvidence ??= fetch(file, {cache:"no-cache"}).then(res => { if (!res.ok) throw Error(`HTTP ${res.status}`); return res.json(); });
    const evidence = await taskEvidence;
    if (selected?.id !== r.id) return;
    const tasks = evidence.tasks_by_psoc_code[r.code] || [];
    caption.textContent = `${tasks.length} PSA task statements, each scored ${r.successful_attempts}× by ${evidence.model_id} (rubric ${evidence.rubric_version}). Numbers are each attempt's score, 0–5. Expand a statement for the scores and what the scoring model judged, not findings.`;
    for (const task of tasks) {
      const li = node("li"), detail = node("details"), summary = node("summary", task.statement, "task-statement");
      detail.append(summary, node("div", `Task exposure ${task.technical_task_exposure_attempts.join(", ")} · Physical presence ${task.human_interaction_attempts.join(", ")}`, "task-scores"));
      const judged = [task.model_judged_ai_can_assist_with && `AI could assist with: ${task.model_judged_ai_can_assist_with}`, task.model_judged_remains_human_dependent && `Remains human-dependent: ${task.model_judged_remains_human_dependent}`].filter(Boolean).join(" · ");
      if (judged) detail.append(node("div", judged, "task-judged"));
      li.append(detail);list.append(li);
    }
  } catch (error) { if (selected?.id === r.id) caption.textContent = `Task evidence could not be loaded (${error.message}). The occupation score above is unaffected.`; taskEvidence = null; }
}
function closeDetail(){
  $("riskPanel").classList.remove("visible");$("riskPanel").setAttribute("aria-hidden","true");$("riskPanel").inert=true;$("riskOverlay").classList.remove("visible");$("wrapper").inert=false;
  hideExplanation();document.body.classList.remove("detail-open");selected=null;hideTooltip();if(!tableMode)requestDraw();returnFocus?.focus({preventScroll:true});returnFocus=null;
}
function renderTable(){const size=40,count=Math.max(1,Math.ceil(filtered.length/size));page=Math.max(0,Math.min(page,count-1));$("rows").replaceChildren();for(const r of filtered.slice(page*size,(page+1)*size)){const tr=node("tr"),td=node("td"),b=node("button",r.title);b.addEventListener("click",()=>showDetail(r));td.append(b);tr.append(td,node("td",r.categoryLabel),node("td",displayValue(r)),node("td",gradeLabel(r)));$("rows").append(tr);}$("tableCaption").textContent=MODES[mode]?.title||"No validated data for this layer";$("page").textContent=`Page ${page+1} of ${count}`;$("prev").disabled=page===0;$("next").disabled=page>=count-1;}

function animateZoom(scale, targetX, targetY, duration = 520) {
  if (zoomFrame) cancelAnimationFrame(zoomFrame);
  const end = Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, scale));
  if (reducedMotion()) { zoom=end;panX=targetX;panY=targetY;clampPan();draw();return; }
  const start={zoom,panX,panY}, t0=performance.now();
  const frame = now => {
    const raw=Math.min(1,(now-t0)/duration), ease=1-Math.pow(1-raw,4);
    zoom=start.zoom+(end-start.zoom)*ease;panX=start.panX+(targetX-start.panX)*ease;panY=start.panY+(targetY-start.panY)*ease;
    clampPan();draw();zoomFrame=raw<1?requestAnimationFrame(frame):null;
  };
  zoomFrame=requestAnimationFrame(frame);
}
function zoomAt(x, y, value, animated = false) {
  const next=Math.max(ZOOM_MIN,Math.min(ZOOM_MAX,value)), worldX=(x-panX)/zoom, worldY=(y-panY)/zoom;
  if (animated) return animateZoom(next, x-worldX*next, y-worldY*next);
  if (zoomFrame) { cancelAnimationFrame(zoomFrame); zoomFrame=null; }
  panX=x-worldX*next;panY=y-worldY*next;zoom=next;clampPan();hideTooltip();draw();
}
function zoomToRect(r) {
  const scale=Math.max(1.4,Math.min(ZOOM_MAX,Math.min(width/(Math.max(24,r.w)*1.5),height/(Math.max(24,r.h)*1.5))));
  hideTooltip();animateZoom(scale,width/2-(r.x+r.w/2)*scale,height/2-(r.y+r.h/2)*scale,560);
}
function resetZoom(animated = true) {
  if (animated && zoom !== 1) return animateZoom(1,0,0,460);
  if (zoomFrame) { cancelAnimationFrame(zoomFrame); zoomFrame=null; }
  zoom=1;panX=panY=0;hideTooltip();if(width)draw();
}

let hoverFrame=null,pendingHover=null;
canvas.addEventListener("mousemove",e=>{
  if(compactLayout||isPanning)return;
  pendingHover={x:e.clientX,y:e.clientY};
  if(hoverFrame!==null)return;
  hoverFrame=requestAnimationFrame(()=>{
    hoverFrame=null;const point=pendingHover;pendingHover=null;if(!point||isPanning||panelOpen())return;
    const r=hit(point.x,point.y);if(r?.id!==hovered?.id){hovered=r;requestDraw();}
    if(hovered){showTooltip(hovered,point.x,point.y);canvas.style.cursor="pointer";}else{hideTooltip();canvas.style.cursor=zoom>1?"grab":"default";}
  });
});
canvas.addEventListener("mouseleave",()=>{
  if(hoverFrame!==null){cancelAnimationFrame(hoverFrame);hoverFrame=null;}pendingHover=null;
  if(compactLayout||isPanning)return;hovered=null;hideTooltip();requestDraw();
});
canvas.addEventListener("click",e=>{
  if(suppressClick){suppressClick=false;return;}
  const r=hit(e.clientX,e.clientY);
  if(compactLayout){
    // Deployed touch behaviour: tap pins the tooltip and opens details; a
    // second tap on the same spot zooms to that box instead. Details wait for
    // the double-tap window, or their overlay would swallow the second tap.
    if(!r){hovered=null;hideTooltip();requestDraw();if(panelOpen())closeDetail();return;}
    const now=Date.now(), dblTap=lastTap&&now-lastTap.time<320&&Math.hypot(lastTap.x-e.clientX,lastTap.y-e.clientY)<28;
    lastTap={time:now,x:e.clientX,y:e.clientY};hovered=r;
    clearTimeout(clickTimer);
    if(dblTap){lastTap=null;hideTooltip();zoomToRect(r);}else{showTooltip(r,e.clientX,e.clientY);clickTimer=setTimeout(()=>showDetail(r),320);}
    requestDraw();return;
  }
  // Delay the drawer briefly so a double-click can zoom instead: once the
  // drawer's overlay covers the canvas, the second click would only close it.
  if(r){clearTimeout(clickTimer);clickTimer=setTimeout(()=>showDetail(r),220);}
});
canvas.addEventListener("dblclick",e=>{const r=hit(e.clientX,e.clientY);if(!r)return;e.preventDefault();clearTimeout(clickTimer);zoomToRect(r);});
canvas.addEventListener("wheel",e=>{
  if(!e.ctrlKey&&!e.metaKey)return;e.preventDefault();
  // Proportional, eased zoom: the target accumulates across wheel ticks and the
  // view glides toward it, so trackpad pinch and mouse wheels both feel smooth.
  const b=canvas.getBoundingClientRect(), x=e.clientX-b.left, y=e.clientY-b.top;
  wheelTarget=Math.max(ZOOM_MIN,Math.min(ZOOM_MAX,(zoomFrame&&wheelTarget?wheelTarget:zoom)*Math.exp(-Math.max(-60,Math.min(60,e.deltaY))*.0042)));
  const wx=(x-panX)/zoom, wy=(y-panY)/zoom;hideTooltip();
  animateZoom(wheelTarget,x-wx*wheelTarget,y-wy*wheelTarget,220);
},{passive:false});
canvas.addEventListener("pointerdown",e=>{
  canvas.classList.remove("keyboard-navigation");
  if(!pointers.size)suppressClick=false;
  pointers.set(e.pointerId,{x:e.clientX,y:e.clientY});canvas.setPointerCapture(e.pointerId);
  if(pointers.size===1&&zoom>1){isPanning=true;lastPan={x:e.clientX,y:e.clientY};canvas.style.cursor="grabbing";}
  if(pointers.size===2){const [a,b]=[...pointers.values()],box=canvas.getBoundingClientRect();pinch={distance:Math.hypot(b.x-a.x,b.y-a.y),zoom,x:(a.x+b.x)/2-box.left,y:(a.y+b.y)/2-box.top};isPanning=false;}
});
canvas.addEventListener("pointermove",e=>{
  if(!pointers.has(e.pointerId))return;
  pointers.set(e.pointerId,{x:e.clientX,y:e.clientY});
  if(pointers.size===2&&pinch?.distance>0){const [a,b]=[...pointers.values()];suppressClick=true;zoomAt(pinch.x,pinch.y,pinch.zoom*Math.hypot(b.x-a.x,b.y-a.y)/pinch.distance);e.preventDefault();return;}
  if(isPanning&&lastPan&&zoom>1){
    const dx=e.clientX-lastPan.x,dy=e.clientY-lastPan.y;if(Math.hypot(dx,dy)>2)suppressClick=true;
    lastPan={x:e.clientX,y:e.clientY};panX+=dx;panY+=dy;clampPan();hovered=null;hideTooltip();requestDraw();e.preventDefault();
  }
});
function releasePointer(id){
  pointers.delete(id);if(pointers.size<2)pinch=null;
  if(!pointers.size){isPanning=false;lastPan=null;canvas.style.cursor=zoom>1?"grab":"default";}
}
canvas.addEventListener("pointerup",e=>releasePointer(e.pointerId));
canvas.addEventListener("pointercancel",e=>releasePointer(e.pointerId));

// Keyboard parity with pointer hover and click: arrows move between boxes in
// layout order, Enter or Space opens the evidence record, + and - zoom.
function focusRect(i){
  keyIndex=(i+rects.length)%rects.length;hovered=rects[keyIndex];
  if(zoom>1){panX=width/2-(hovered.x+hovered.w/2)*zoom;panY=height/2-(hovered.y+hovered.h/2)*zoom;clampPan();}
  const b=canvas.getBoundingClientRect();draw();
  showTooltip(hovered,b.left+(hovered.x+hovered.w/2)*zoom+panX,b.top+(hovered.y+hovered.h/2)*zoom+panY);
  canvas.setAttribute("aria-label",`${hovered.title}, ${displayValue(hovered)}. Box ${keyIndex+1} of ${rects.length}. Enter opens source details.`);
}
canvas.addEventListener("keydown",e=>{
  canvas.classList.add("keyboard-navigation");
  if(!rects.length)return;
  const moves={ArrowRight:1,ArrowDown:1,ArrowLeft:-1,ArrowUp:-1};
  if(e.key in moves){e.preventDefault();focusRect(keyIndex<0?0:keyIndex+moves[e.key]);}
  else if(e.key==="Home"||e.key==="End"){e.preventDefault();focusRect(e.key==="Home"?0:rects.length-1);}
  else if((e.key==="Enter"||e.key===" ")&&keyIndex>=0){e.preventDefault();showDetail(rects[keyIndex]);}
  else if(e.key==="+"||e.key==="="||e.key==="-"){e.preventDefault();zoomAt(width/2,height/2,zoom*(e.key==="-"?1/1.25:1.25));}
});
canvas.addEventListener("blur",()=>{if(keyIndex>=0&&!panelOpen()){hovered=null;hideTooltip();requestDraw();}});

document.addEventListener("pointerover",e=>{const target=e.target.closest("[data-explanation]");if(target&&e.pointerType!=="touch"&&!explanationPinned)showExplanation(target);});
document.addEventListener("pointerout",e=>{if(explanationPinned||!explanationTarget)return;const to=e.relatedTarget;if(!explanationTarget.contains(to)&&!$("explainPopover").contains(to))explanationTimer=setTimeout(hideExplanation,120);});
$("explainPopover").addEventListener("pointerenter",()=>clearTimeout(explanationTimer));
$("explainPopover").addEventListener("pointerleave",()=>{if(!explanationPinned)explanationTimer=setTimeout(hideExplanation,120);});
document.addEventListener("focusin",e=>{const target=e.target.closest("[data-explanation]");if(target)showExplanation(target);else if(explanationTarget)hideExplanation();});
document.addEventListener("click",e=>{const target=e.target.closest("[data-explanation]");if(target){if(explanationTarget===target&&explanationPinned)hideExplanation();else showExplanation(target,true);}else if(!$("explainPopover").contains(e.target))hideExplanation();});
addEventListener("scroll",()=>hideExplanation(),true);addEventListener("resize",()=>hideExplanation());
$("profileTabs").addEventListener("click",e=>{const tab=e.target.closest("[data-profile-tab]");if(tab)selectProfileTab(tab.dataset.profileTab);});
$("profileTabs").addEventListener("keydown",e=>{
  if(!["ArrowRight","ArrowLeft","Home","End"].includes(e.key))return;e.preventDefault();
  const tabs=[...$("profileTabs").querySelectorAll("button")].filter(b=>!b.hidden), index=tabs.indexOf(document.activeElement);
  const next=e.key==="Home"?0:e.key==="End"?tabs.length-1:(index+(e.key==="ArrowRight"?1:-1)+tabs.length)%tabs.length;
  selectProfileTab(tabs[next].dataset.profileTab,true);
});
$("riskClose").addEventListener("click",closeDetail);$("riskOverlay").addEventListener("click",closeDetail);
document.addEventListener("keydown",e=>{
  if(e.key==="Escape"){if(hideExplanation()){e.preventDefault();return;}if(panelOpen())closeDetail();else resetZoom(true);}
  if(e.key==="Tab"&&panelOpen()){const items=[...$("riskPanel").querySelectorAll("button,a[href],summary")].filter(n=>!n.disabled&&n.getClientRects().length&&n.tabIndex!==-1),first=items[0],last=items.at(-1);if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus();}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus();}}
});
$("industryFilter").addEventListener("change",()=>{saveSetting(`trabaholens_verified_filter_${mode}`,$("industryFilter").value);if(panelOpen())closeDetail();page=0;resetZoom(false);update();});
$("search").addEventListener("input",()=>{page=0;resetZoom(false);update();});
$("view").addEventListener("click",()=>{tableMode=!tableMode;$("view").textContent=tableMode?"Treemap view":"Table view";update();});
$("download").addEventListener("click",exportCSV);$("resetZoom").addEventListener("click",()=>resetZoom(true));$("prev").addEventListener("click",()=>{page--;renderTable();});$("next").addEventListener("click",()=>{page++;renderTable();});
new ResizeObserver(()=>{if(payload&&!tableMode&&($("wrapper").clientWidth!==width||isCompactLayout()!==compactLayout)){hideTooltip();layout();}}).observe($("wrapper"));
addEventListener("orientationchange",()=>{if(payload&&!tableMode){hideTooltip();layout();}});
(async()=>{
  try{
    if(location.protocol==="file:")throw Error("Open http://127.0.0.1:8000/ using the local server; direct file previews cannot load release data");
    const response=await fetch("data.json",{cache:"no-cache"});if(!response.ok)throw Error(`Data request failed (${response.status})`);payload=await response.json();assertRelease(payload);buildRecords();
    SCORE_GUIDE.forEach(([title,text],i)=>{const button=explainButton(String(i),text);button.dataset.explainTitle=`Score ${i} · ${title}`;button.setAttribute("aria-label",`Score ${i}: ${title}`);$("legendSteps").append(button);});$("methodScale").append(scoreExplorer());$("classificationNote").textContent=payload.disclaimers.classification_verification;for(const text of payload.release.known_limitations)$("limitations").append(node("li",text));$("releaseDate").textContent=`Build ${payload.release.release_date.slice(0,10)} · source periods 2024`;
    // Unavailable layers stay selectable so every user, including keyboard and
    // touch users, can read why they are empty. They never receive values.
    document.querySelectorAll("#colorToggle button").forEach(button=>{if(UNAVAILABLE[button.dataset.mode]){button.title=UNAVAILABLE[button.dataset.mode];button.classList.add("unavailable");}button.addEventListener("click",()=>selectMode(button.dataset.mode));});
    // The exposure layer leads when a scored run is published; otherwise the
    // first survey layer does, so an empty model layer is never the front page.
    // A first visit opens on AI task exposure when a scoring run is published.
        const saved=loadSetting("trabaholens_layer_v2");
    selectMode(MODES[saved]||UNAVAILABLE[saved]?saved:records.exposure.some(validValue)?"exposure":"employment");
  }catch(error){payload=null;$("loadError").hidden=false;$("loadError").textContent=`No estimates displayed: ${error.message}`;$("canvas").hidden=true;$("statsRow").hidden=true;$("evidenceStats").hidden=true;$("overviewCharts").hidden=true;document.querySelectorAll("#colorToggle button,.evidence-tools button,.evidence-tools input,#industryFilter").forEach(n=>n.disabled=true);}
})();
