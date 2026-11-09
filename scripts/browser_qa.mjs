// Headless Chrome browser QA for the dashboard. Fresh profile per run.
//
// Drives real mouse, touch and keyboard input through the DevTools protocol,
// compares canvas geometry with the deployed site, and writes screenshots for
// human side-by-side review. Screenshots are evidence for a person to judge;
// passing checks here does not by itself establish visual acceptance.
//
//   PYTHONPATH=src uv run python scripts/serve.py &   # http://127.0.0.1:8000
//   node scripts/browser_qa.mjs                       # or: make browser-qa
//
// Env: CHROME (binary), QA_OUT (screenshot dir), LOCAL_URL, LIVE_URL,
// SHOTS=1 (screenshots and geometry only).
import { spawn } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
const OUT = process.env.QA_OUT || path.resolve(path.dirname(new URL(import.meta.url).pathname), "../.browser-qa");
fs.mkdirSync(OUT, { recursive: true });
const CHROME = process.env.CHROME || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const profile = fs.mkdtempSync(OUT + "/profile-");
const chrome = spawn(CHROME, ["--headless=new", "--remote-debugging-port=9333", `--user-data-dir=${profile}`, "--no-first-run", "--hide-scrollbars", "about:blank"], { stdio: "ignore" });
const sleep = ms => new Promise(r => setTimeout(r, ms));
let ws, id = 0; const pending = new Map(), listeners = [];
async function connect() {
  for (let i = 0; i < 50; i++) { try { const list = await (await fetch("http://127.0.0.1:9333/json")).json(); const page = list.find(t => t.type === "page"); if (page) { ws = new WebSocket(page.webSocketDebuggerUrl); await new Promise(r => ws.onopen = r); break; } } catch {} await sleep(200); }
  ws.onmessage = m => { const d = JSON.parse(m.data); if (d.id && pending.has(d.id)) { pending.get(d.id)(d); pending.delete(d.id); } else listeners.forEach(f => f(d)); };
}
const send = (method, params = {}) => new Promise((res, rej) => { const i = ++id; pending.set(i, d => d.error ? rej(Error(method + ": " + d.error.message)) : res(d.result)); ws.send(JSON.stringify({ id: i, method, params })); });
const ev = async expr => { const r = await send("Runtime.evaluate", { expression: expr, returnByValue: true, awaitPromise: true }); if (r.exceptionDetails) throw Error(expr + " -> " + JSON.stringify(r.exceptionDetails.exception?.description || r.exceptionDetails.text)); return r.result.value; };
const results = []; const check = (name, ok, detail = "") => { results.push({ name, ok: !!ok, detail }); console.log(`${ok ? "PASS" : "FAIL"} ${name}${detail ? " — " + detail : ""}`); };
async function viewport(w, h, mobile) {
  await send("Emulation.setDeviceMetricsOverride", { width: w, height: h, deviceScaleFactor: mobile ? 3 : 1, mobile });
  await send("Emulation.setTouchEmulationEnabled", { enabled: mobile, maxTouchPoints: mobile ? 5 : 1 });
  await send("Emulation.setEmitTouchEventsForMouse", { enabled: false });
}
async function load(url) { await send("Page.navigate", { url }); for (let i = 0; i < 60; i++) { await sleep(200); if (await ev("document.readyState") === "complete") break; } await sleep(900); }
async function shot(name, full = true) { if (!full) { const r = await send("Page.captureScreenshot", { format: "png" }); fs.writeFileSync(`${OUT}/${name}.png`, Buffer.from(r.data, "base64")); return; } const m = await send("Page.getLayoutMetrics"); const h = Math.min(full ? m.cssContentSize.height : m.cssVisualViewport.clientHeight, 6000); const r = await send("Page.captureScreenshot", { format: "png", captureBeyondViewport: full, clip: { x: 0, y: 0, width: m.cssVisualViewport.clientWidth, height: h, scale: 1 } }); fs.writeFileSync(`${OUT}/${name}.png`, Buffer.from(r.data, "base64")); }
const mouse = (type, x, y, extra = {}) => send("Input.dispatchMouseEvent", { type, x, y, button: "left", buttons: type === "mouseReleased" ? 0 : 1, clickCount: 1, ...extra });
async function click(x, y, count = 1) { await mouse("mouseMoved", x, y, { buttons: 0 }); await mouse("mousePressed", x, y, { clickCount: count }); await mouse("mouseReleased", x, y, { clickCount: count }); }
const key = async (k, code, extra = {}) => { await send("Input.dispatchKeyEvent", { type: "keyDown", key: k, code: code || k, windowsVirtualKeyCode: extra.vk || 0, ...extra }); await send("Input.dispatchKeyEvent", { type: "keyUp", key: k, code: code || k, windowsVirtualKeyCode: extra.vk || 0 }); };
const touch = (type, points) => send("Input.dispatchTouchEvent", { type, touchPoints: points.map((p, i) => ({ x: p[0], y: p[1], id: i })) });
async function tap(x, y) { await touch("touchStart", [[x, y]]); await sleep(30); await touch("touchEnd", []); }
// Centre of the largest rect in viewport coordinates, scrolled into view.
async function target(index = 0) {
  return ev(`(()=>{const c=document.getElementById("canvas");c.scrollIntoView({block:"start"});const b=c.getBoundingClientRect();const r=[...rects].sort((a,b)=>b.w*b.h-a.w*a.h)[${index}];return r?{x:b.left+(r.x+r.w/2)*zoom+panX,y:b.top+(r.y+r.h/2)*zoom+panY,id:r.id,title:r.title}:null})()`);
}

const LOCAL = process.env.LOCAL_URL || "http://127.0.0.1:8000/", LIVE = process.env.LIVE_URL || "https://trabaho-lens.vercel.app/";
await connect();
await send("Page.enable"); await send("Runtime.enable");
const errors = []; listeners.push(d => { if (d.method === "Runtime.exceptionThrown") errors.push(d.params.exceptionDetails.exception?.description || d.params.exceptionDetails.text); if (d.method === "Runtime.consoleAPICalled" && d.params.type === "error") errors.push(d.params.args.map(a => a.value || a.description).join(" ")); });

// ── Side-by-side screenshots ─────────────────────────────────────────────
for (const [label, w, h, mobile] of [["desktop", 1440, 900, false], ["tablet", 820, 1180, true], ["mobile", 390, 844, true]]) {
  await viewport(w, h, mobile);
  await load(LIVE); await shot(`live-${label}`, false); await shot(`live-${label}-full`);
  const live = await ev(`({header:document.getElementById("header").getBoundingClientRect().height,canvas:[canvas.clientWidth,canvas.clientHeight],overflow:document.documentElement.scrollWidth>innerWidth,buttons:document.querySelectorAll("#colorToggle button").length})`);
  await load(LOCAL); await shot(`local-${label}`, false); await shot(`local-${label}-full`);
  const local = await ev(`({header:document.getElementById("header").getBoundingClientRect().height,canvas:[canvas.clientWidth,canvas.clientHeight],overflow:document.documentElement.scrollWidth>innerWidth,buttons:document.querySelectorAll("#colorToggle button").length})`);
  check(`${label}: canvas dimensions match deployment`, JSON.stringify(live.canvas) === JSON.stringify(local.canvas), `live ${live.canvas} local ${local.canvas}`);
  check(`${label}: no horizontal page overflow`, !local.overflow, `live overflow=${live.overflow}`);
  console.log(`  ${label} header height live ${live.header.toFixed(0)} local ${local.header.toFixed(0)}`);
}

if (process.env.SHOTS) { ws.close(); chrome.kill(); setTimeout(()=>process.exit(0),500); await sleep(1e9); }
// ── Desktop interactions ─────────────────────────────────────────────────
await viewport(1440, 900, false); await load(LOCAL);
{ const m0 = await ev(`mode`); check("fresh profile starts on AI task exposure when a run is published", m0 === "exposure", `mode=${m0} saved=${await ev(`(()=>{try{return localStorage.getItem("trabaholens_layer_v2")}catch(e){return "err"}})()`)}`); }
await ev(`document.querySelector('#colorToggle button[data-mode="employment"]').click()`); await sleep(300);
check("employment layer selectable", await ev(`mode`) === "employment");
check("employment boxes equal published major groups", await ev(`rects.length`) === await ev(`records.employment.filter(validValue).length`), `${await ev("rects.length")} boxes`);
check("employment box areas proportional to estimates", await ev(`(()=>{const t=rects.reduce((s,r)=>s+r.value,0),a=rects.reduce((s,r)=>s+r.w*r.h,0);return rects.every(r=>Math.abs(r.w*r.h/a-r.value/t)<0.02)})()`));
let t = await target();
await mouse("mouseMoved", t.x, t.y, { buttons: 0 }); await sleep(150);
check("hover shows tooltip", await ev(`document.getElementById("tooltip").classList.contains("visible")`), await ev(`document.querySelector("#tooltip .tt-title").textContent`));
check("hover preview stays concise with period and evidence", await ev(`document.querySelectorAll("#tooltip .tt-stats .label").length===2&&tooltip.textContent.includes(hovered.reference_period)`));
check("hovered box highlighted", await ev(`hovered?.id`) === t.id);
await shot("local-desktop-hover", false);
await mouse("mousePressed", t.x, t.y); await mouse("mouseReleased", t.x, t.y); await sleep(500);
check("click opens details drawer", await ev(`document.getElementById("riskPanel").classList.contains("visible")`));
check("drawer focuses close button", await ev(`document.activeElement.id`) === "riskClose");
check("drawer lists provenance hash", await ev(`document.getElementById("detailFields").textContent.includes(selected.source_file_hash)`));
check("background is inert while drawer open", await ev(`document.getElementById("wrapper").inert`));
await shot("local-desktop-drawer", false);
await key("Tab", "Tab", { vk: 9 }); await key("Tab", "Tab", { vk: 9 });
check("Tab stays trapped in drawer", await ev(`document.getElementById("riskPanel").contains(document.activeElement)`), await ev(`document.activeElement.id||document.activeElement.textContent`));
await key("Escape", "Escape", { vk: 27 }); await sleep(200);
check("Escape closes drawer", !(await ev(`document.getElementById("riskPanel").classList.contains("visible")`)));
check("selection cleared on close", await ev(`selected`) === null);
await click(t.x, t.y); await sleep(400);
await ev(`document.getElementById("riskOverlay").click()`); await sleep(200);
check("overlay click closes drawer", !(await ev(`document.getElementById("riskPanel").classList.contains("visible")`)));
// double-click zoom
await mouse("mouseMoved", t.x, t.y, { buttons: 0 });
await mouse("mousePressed", t.x, t.y, { clickCount: 1 }); await mouse("mouseReleased", t.x, t.y, { clickCount: 1 });
await mouse("mousePressed", t.x, t.y, { clickCount: 2 }); await mouse("mouseReleased", t.x, t.y, { clickCount: 2 }); await sleep(800);
check("double-click zooms to box", await ev(`zoom`) > 1.3, `zoom ${(await ev("zoom")).toFixed(2)}`);
check("double-click does not open drawer", !(await ev(`document.getElementById("riskPanel").classList.contains("visible")`)));
await shot("local-desktop-zoomed", false);
// drag pan
const before = await ev(`[panX,panY]`);
await mouse("mouseMoved", t.x, t.y, { buttons: 0 }); await mouse("mousePressed", t.x, t.y);
for (let i = 1; i <= 5; i++) await mouse("mouseMoved", t.x - i * 30, t.y - i * 20);
await mouse("mouseReleased", t.x - 150, t.y - 100); await sleep(400);
const after = await ev(`[panX,panY]`);
check("mouse drag pans when zoomed", before[0] !== after[0] || before[1] !== after[1], `${before.map(n=>n.toFixed(0))} -> ${after.map(n=>n.toFixed(0))}`);
check("drag does not open drawer", !(await ev(`document.getElementById("riskPanel").classList.contains("visible")`)));
await key("Escape", "Escape", { vk: 27 }); await sleep(700);
check("Escape resets zoom", await ev(`zoom`) === 1);
await send("Input.dispatchMouseEvent", { type: "mouseWheel", x: t.x, y: t.y, deltaX: 0, deltaY: -100, modifiers: 2 }); await sleep(100);
check("Ctrl+wheel zooms in", await ev(`zoom`) > 1, `zoom ${(await ev("zoom")).toFixed(2)}`);
await sleep(400); const z = await ev(`zoom`); await send("Input.dispatchMouseEvent", { type: "mouseWheel", x: t.x, y: t.y, deltaX: 0, deltaY: 100, modifiers: 0 }); await sleep(400);
check("plain wheel does not zoom", await ev(`zoom`) === z);
await ev(`resetZoom(false)`);
// keyboard
await ev(`document.getElementById("canvas").focus()`);
await key("ArrowRight", "ArrowRight", { vk: 39 }); await key("ArrowRight", "ArrowRight", { vk: 39 });
check("arrow keys move highlight", await ev(`keyIndex`) === 1 && await ev(`hovered?.id`) === await ev(`rects[1].id`));
check("canvas label announces focused box", (await ev(`canvas.getAttribute("aria-label")`)).includes("Box 2 of"));
await key("Enter", "Enter", { vk: 13, text: "\r" }); await sleep(200);
check("Enter opens drawer for focused box", await ev(`selected?.id`) === await ev(`rects[1].id`));
await key("Escape", "Escape", { vk: 27 }); await sleep(200);
check("focus returns to canvas after close", await ev(`document.activeElement.id`) === "canvas");
// layers
for (const m of ["employment", "detail", "earnings", "exposure", "wages", "education", "vulnerable", "outlook", "ofw", "informal"]) {
  await ev(`document.querySelector('#colorToggle button[data-mode="${m}"]').click()`); await sleep(250);
  const s = await ev(`({mode,boxes:rects.length,desc:layerDesc.textContent,count:resultCount.textContent,enabled:!document.querySelector('#colorToggle button[data-mode="${m}"]').disabled,pressed:document.querySelector('#colorToggle button[data-mode="${m}"]').getAttribute("aria-pressed"),legend:[legendLow.textContent,legendHigh.textContent]})`);
  const unavailable = ["outlook", "informal"].includes(m);
  check(`layer ${m}: selectable and explained`, s.mode === m && s.enabled && s.pressed === "true" && (unavailable ? s.boxes === 0 && s.desc.includes("unavailable") : s.boxes > 0), `${s.boxes} boxes · ${s.count} · legend ${s.legend.join("–")}`);
  await shot(`local-desktop-layer-${m}`, false);
}
// OFW missing cell and filter
await ev(`document.querySelector('#colorToggle button[data-mode="ofw"]').click()`); await sleep(200);
check("OFW armed-forces cell not plotted and counted missing", await ev(`!rects.some(r=>r.code==="0") && resultCount.textContent.includes("1 withheld")`), await ev("resultCount.textContent"));
await ev(`document.querySelector('#colorToggle button[data-mode="wages"]').click()`); await sleep(200);
const opt = await ev(`industryFilter.options[2].value`);
await ev(`industryFilter.value=${JSON.stringify(opt)};industryFilter.dispatchEvent(new Event("change"))`); await sleep(200);
check("industry filter restricts wage records", await ev(`filtered.every(r=>r.category===${JSON.stringify(opt)}) && rects.length>0`), `${opt}: ${await ev("resultCount.textContent")}`);
await ev(`industryFilter.value="all";industryFilter.dispatchEvent(new Event("change"));search.value="accountant";search.dispatchEvent(new Event("input"))`); await sleep(200);
check("search filters records", await ev(`filtered.length>0 && filtered.length<records.wages.length && filtered.every(r=>(r.title+" "+r.code+" "+r.categoryLabel).toLowerCase().includes("accountant"))`), await ev("resultCount.textContent"));
// CSV capture
await ev(`industryFilter.value="all";search.value="";industryFilter.dispatchEvent(new Event("change"))`); await sleep(200);
const csv = await ev(`new Promise(res=>{const o=URL.createObjectURL;URL.createObjectURL=b=>{b.text().then(res);URL.createObjectURL=o;return o.call(URL,b)};download.click()})`);
fs.writeFileSync(`${OUT}/wages-export.csv`, csv);
const lines = csv.replace(/^﻿/, "").trim().split("\r\n");
check("CSV has one row per filtered record incl. withheld", lines.length - 1 === await ev(`filtered.length`), `${lines.length - 1} rows`);
const parse = l => l.slice(1, -1).split('","'); const head = parse(lines[0].replace(/^\uFEFF/, "")); const vi = head.indexOf("value"), ai = head.indexOf("availability");
const rows = lines.slice(1).map(parse), held = rows.filter(r => r[ai] !== "published");
check("CSV withheld rows keep empty values", held.length === 9 && held.every(r => r[vi] === ""), `${held.length} withheld: ${[...new Set(held.map(r=>r[ai]))]}`);
check("CSV published values match payload", rows.filter(r=>r[ai]==="published").every(r=>r[vi]!=="" && Number.isFinite(Number(r[vi]))));
check("CSV header carries provenance", ["source_file_hash", "population_scope", "standard_error", "availability"].every(f => lines[0].includes(f)));
// Table view
await ev(`view.click()`); await sleep(200);
check("table view paginates records", await ev(`rows.children.length`) === 40, await ev(`page.textContent`));
await ev(`view.click()`);
// persistence after reload
await load(LOCAL);
check("layer persists across reload", await ev(`mode`) === "wages");
check("no page errors on desktop", errors.length === 0, errors.join(" | "));

// ── Profile redesign: evidence, disclosure and responsive boundaries ──────
await ev(`selectMode("exposure")`); await sleep(250);
const previewTarget = await target();
await mouse("mouseMoved", previewTarget.x, previewTarget.y, {buttons:0}); await sleep(150);
check("exposure preview shows the source score", await ev(`document.querySelector(".preview-value").textContent === displayValue(hovered)`));
check("preview rail announces the ordinal scale", await ev(`document.querySelector("#tooltip .score-rail").getAttribute("aria-label").includes("out of 5")`));
check("preview retains independent-validation disclosure", await ev(`tooltip.textContent.includes("Not independently validated")`));
for (const [edge,x,y] of [["top-left",2,2],["bottom-right",1438,898]]) {
  await ev(`showTooltip(records.exposure.find(validValue),${x},${y})`);
  check(`preview stays within ${edge} viewport edges`,await ev(`(()=>{const b=tooltip.getBoundingClientRect();return b.x>=0&&b.y>=0&&b.right<=innerWidth&&b.bottom<=innerHeight})()`));
}
await ev(`showDetail(records.exposure.find(validValue))`); await sleep(350);
for(let i=0;i<30;i++){if(await ev(`taskList.children.length>0`))break;await sleep(100);}
check("profile displays the exact selected score",await ev(`profileValue.textContent === displayValue(selected)`));
await ev(`tabEvidence.click()`);
check("task distribution counts match the selected source distribution",await ev(`JSON.stringify([...taskDistribution.querySelectorAll("strong")].map(n=>Number(n.textContent))) === JSON.stringify(Object.values(selected.score_distribution))`));
check("task chart has accessible per-category counts",await ev(`taskDistribution.children.length>0&&[...taskDistribution.children].every(n=>n.getAttribute("aria-label").includes("tasks"))`));
check("task statements match published evidence coverage",await ev(`taskList.children.length === selected.tasks_included`));
check("task reasoning starts collapsed",await ev(`taskList.querySelectorAll("details").length===taskList.children.length&&![...taskList.querySelectorAll("details")].some(n=>n.open)`));
await ev(`taskList.querySelector("summary").click()`);
check("task reasoning can be expanded",await ev(`taskList.querySelector("details").open&&taskList.querySelector(".task-scores").textContent.includes("Task exposure")`));
await ev(`tabSource.click()`);
check("full provenance starts collapsed but preserves the hash",await ev(`!provenanceDetails.open&&detailFields.textContent.includes(selected.task_source_file_hash)`));
await ev(`provenanceDetails.querySelector("summary").click()`);
check("full provenance can be expanded",await ev(`provenanceDetails.open&&detailFields.getBoundingClientRect().height>0`));
await ev(`tabOverview.click()`); await shot("profile-exposure-desktop",false);
await ev(`tabEvidence.click();taskList.querySelector("details").open=false;provenanceDetails.open=false;document.querySelector(".risk-body").scrollTop=0`);await shot("profile-evidence-desktop",false);
check("drawer hides hover preview and locks page scrolling",await ev(`!tooltip.classList.contains("visible")&&getComputedStyle(document.body).overflow==="hidden"`));
await ev(`closeDetail();showDetail(records.exposure.find(r=>!validValue(r)))`);await sleep(250);
check("unscored profile has no invented score or chart",await ev(`distributionCard.hidden&&taskCard.hidden&&!document.querySelector("#profileVisual .score-rail")&&profileValue.textContent===displayValue(selected)`));
await shot("profile-unscored-desktop",false);
await ev(`closeDetail();selectMode("wages");showDetail(records.wages.find(r=>!validValue(r)))`);await sleep(250);
check("withheld wage profile preserves missingness",await ev(`distributionCard.hidden&&taskCard.hidden&&profileValue.textContent===displayValue(selected)&&selected.value===null`));
check("wage record code is not labelled PSOC",await ev(`riskMeta.textContent.includes("Source code")&&!riskMeta.textContent.includes("PSOC")`));
await ev(`closeDetail()`);
check("closing drawer unlocks page scrolling",await ev(`!document.body.classList.contains("detail-open")&&!wrapper.inert`));
for(const layer of ["employment","detail","earnings","education","vulnerable","ofw","wages","exposure"]){
  await ev(`selectMode("${layer}");showDetail(records[mode].find(validValue))`);await sleep(80);
  check(`${layer}: profile preserves source value and has no horizontal overflow`,await ev(`profileValue.textContent===displayValue(selected)&&riskPanel.scrollWidth<=riskPanel.clientWidth&&detailFields.textContent.includes(selected.reference_period)`));
  await ev(`closeDetail()`);
}
await ev(`showDetail(records.exposure.find(validValue))`);await sleep(100);
await ev(`tabSource.click();riskClose.focus()`);await key("Tab","Tab",{vk:9,modifiers:8});
check("Shift+Tab wraps to final provenance control",await ev(`document.activeElement===provenanceDetails.querySelector("summary")`));
await key("Tab","Tab",{vk:9});
check("Tab wraps back to close after final control",await ev(`document.activeElement===riskClose`));
await ev(`closeDetail()`);

for(const [label,w,h,mobile] of [["small-phone",320,740,true],["phone",390,844,true],["tablet",820,1180,true]]){
  await viewport(w,h,mobile);await ev(`selectMode("exposure");showDetail(records.exposure.find(validValue))`);await sleep(300);
  check(`${label}: profile fits viewport without horizontal overflow`,await ev(`(()=>{const b=riskPanel.getBoundingClientRect();return b.left>=-1&&b.right<=innerWidth+1&&b.top>=-1&&b.bottom<=innerHeight+1&&riskPanel.scrollWidth<=riskPanel.clientWidth})()`));
  check(`${label}: body scrolls within fixed profile header and footer`,await ev(`(()=>{const b=document.querySelector(".risk-body");return getComputedStyle(b).overflowY==="auto"&&riskClose.getBoundingClientRect().top>=0})()`));
  await shot(`profile-exposure-${label}`,false);await ev(`closeDetail()`);
}
await send("Emulation.setEmulatedMedia",{features:[{name:"prefers-reduced-motion",value:"reduce"}]});
check("reduced-motion preference disables drawer movement",await ev(`getComputedStyle(riskPanel).transitionDuration === "0s"`));
await send("Emulation.setEmulatedMedia",{features:[]});
check("no page errors in redesigned profiles",errors.length===0,errors.join(" | "));

// ── Local review refinements: concise UI and discoverable meaning ────────
await viewport(1440,900,false);await ev(`selectMode("exposure")`);await sleep(250);
check("main legend offers meanings for all score categories",await ev(`!legendSteps.hidden&&legendSteps.children.length===6`));
const legendPoint=await ev(`(()=>{legendSteps.scrollIntoView({block:"center"});const b=legendSteps.children[3].getBoundingClientRect();return {x:b.x+b.width/2,y:b.y+b.height/2}})()`);
await mouse("mouseMoved",legendPoint.x,legendPoint.y,{buttons:0});await sleep(100);
check("hovering 3 on the main legend explains the category",await ev(`!explainPopover.hidden&&explainPopover.textContent.includes("Substantial assistance")`));
await ev(`hideExplanation()`);
check("supporting evidence starts behind a disclosure",await ev(`!evidenceStats.open&&statsRow.children.length===4`));
check("all summary figures have plain-language explanations",await ev(`document.querySelectorAll("#statsRow [data-explanation],#evidenceStats [data-explanation]").length===8&&[...document.querySelectorAll("#statsRow [data-explanation],#evidenceStats [data-explanation]")].every(b=>b.dataset.explanation.length>60)`));
await ev(`document.querySelector("#statTotalHeading button").focus()`);await sleep(80);
check("keyboard focus opens summary explanation",await ev(`!explainPopover.hidden&&explainPopover.textContent.includes("unit groups")`));
await key("Escape","Escape",{vk:27});
check("Escape dismisses explanatory help",await ev(`explainPopover.hidden`));
await ev(`evidenceStats.querySelector("summary").click();document.querySelector("#block7 button").click()`);
check("model help explains limits of agreement",await ev(`!explainPopover.hidden&&explainPopover.textContent.includes("Agreement between models")`));
await shot("summary-help-desktop",false);await ev(`hideExplanation();evidenceStats.open=false`);
const borderTarget=await target();await click(borderTarget.x,borderTarget.y);await sleep(500);await key("Escape","Escape",{vk:27});
check("mouse use has no large canvas focus border",await ev(`getComputedStyle(canvas).outlineStyle==="none"&&!canvas.classList.contains("keyboard-navigation")`));
await mouse("mouseMoved",borderTarget.x,borderTarget.y,{buttons:0});await sleep(120);
check("hover card is compact",await ev(`(()=>{const b=tooltip.getBoundingClientRect();return b.width<=270&&b.height<=285})()`));
await shot("compact-hover-desktop",false);
await ev(`showDetail(records.exposure.find(validValue))`);await sleep(280);
check("profile opens with overview only",await ev(`!profileOverview.hidden&&profileEvidence.hidden&&profileSource.hidden&&tabOverview.getAttribute("aria-selected")==="true"`));
check("close control is labelled and has no circular border",await ev(`riskClose.textContent.includes("Close")&&getComputedStyle(riskClose).borderTopWidth==="0px"`));
const originalScore=await ev(`selected.value`);
await ev(`document.querySelectorAll("#profileVisual .scale-options button")[3].dispatchEvent(new PointerEvent("pointerenter",{pointerType:"mouse"}))`);
check("hovering score 3 explains substantial assistance",await ev(`document.querySelector("#profileVisual .scale-description").textContent.includes("Substantial assistance")`));
await ev(`document.querySelectorAll("#profileVisual .scale-options button")[2].focus()`);
check("focusing score 2 explains its category",await ev(`document.querySelector("#profileVisual .scale-description").textContent.includes("meaningful slice")`));
await ev(`document.querySelectorAll("#profileVisual .scale-options button")[4].click()`);
check("clicking a scale point pins its explanation without changing the score",await ev(`document.querySelectorAll("#profileVisual .scale-options button")[4].getAttribute("aria-pressed")==="true"&&selected.value===${originalScore}&&profileValue.textContent===displayValue(selected)`));
await ev(`tabOverview.focus()`);await key("ArrowRight","ArrowRight",{vk:39});
check("profile tabs support arrow-key navigation",await ev(`!profileEvidence.hidden&&profileOverview.hidden&&document.activeElement===tabEvidence`));
await ev(`tabSource.click();document.querySelector(".profile-limits summary").click()`);
check("record limitations remain available in source tab",await ev(`!profileSource.hidden&&document.querySelector(".profile-limits").open&&detailNotes.getBoundingClientRect().height>0`));
await ev(`closeDetail();methodGuide.open=true`);await sleep(150);
check("method guide has a readable structure and interactive scale",await ev(`methodGuide.querySelectorAll(".method-content h2").length===3&&methodScale.querySelectorAll("button").length===6`));
await ev(`methodScale.querySelectorAll("button")[5].click()`);
check("method guide scale explains accountability at score 5",await ev(`methodScale.textContent.includes("accountability")`));
await ev(`document.querySelector(".method-notes summary").click()`);
check("classification and all published limitations remain accessible",await ev(`classificationNote.getBoundingClientRect().height>0&&limitations.children.length===payload.release.known_limitations.length`));
await ev(`methodGuide.scrollIntoView({block:"start"})`);await shot("method-guide-desktop",false);
await ev(`methodGuide.open=false`);
for(const [label,w,h] of [["small-phone",320,740],["phone",390,844],["tablet",820,1180]]){
  await viewport(w,h,true);await ev(`methodGuide.open=true`);await sleep(100);
  check(`${label}: expanded method guide has no page overflow`,await ev(`document.documentElement.scrollWidth<=innerWidth`));
  await ev(`methodGuide.open=false;showDetail(records.exposure.find(validValue))`);await sleep(250);
  await ev(`document.querySelectorAll("#profileVisual .scale-options button")[3].click()`);
  check(`${label}: tapping scale reveals explanation`,await ev(`document.querySelector("#profileVisual .scale-description").textContent.includes("Substantial assistance")`));
  await shot(`refined-profile-${label}`,false);await ev(`closeDetail()`);
}
check("no errors in local-review refinements",errors.length===0,errors.join(" | "));

// ── Layer consistency, source-backed charts and readable profile ─────────
await viewport(1440,900,false);await ev(`selectMode("exposure");evidenceStats.open=false`);await sleep(250);
const layerGeometry=[];
for(const layer of ["exposure","employment","detail","earnings","wages","education","vulnerable","ofw","outlook","informal"]){
  await ev(`selectMode("${layer}")`);await sleep(80);
  const geometry=await ev(`({buttons:[...colorToggle.children].map(b=>{const r=b.getBoundingClientRect();return [r.width,r.height]}),mapTop:canvas.getBoundingClientRect().top,charts:overviewCharts.getBoundingClientRect().height})`);layerGeometry.push(geometry);
  check(`${layer}: chart counts match the published source records`,await ev(`!overviewData.available ? document.querySelectorAll(".chart-empty").length===3 : [...distributionPlot.querySelectorAll("[data-count]")].reduce((s,b)=>s+Number(b.dataset.count),0)===filtered.filter(validValue).length`));
}
check("layer buttons keep identical dimensions across every mode",layerGeometry.every(g=>JSON.stringify(g.buttons)===JSON.stringify(layerGeometry[0].buttons)));
check("summary charts retain the same height across layers",layerGeometry.every(g=>Math.abs(g.charts-layerGeometry[0].charts)<1));
check("map starts at a consistent position across layers",layerGeometry.every(g=>Math.abs(g.mapTop-layerGeometry[0].mapTop)<1),JSON.stringify(layerGeometry.map(g=>g.mapTop)));
await ev(`selectMode("exposure")`);await sleep(100);
check("exposure tiers partition scored unit groups without employment weighting",await ev(`overviewData.tiers.reduce((s,t)=>s+t.count,0)===filtered.filter(validValue).length&&distributionCaption.textContent.includes("not workers")`));
check("task coverage uses the published task totals",await ev(`overviewData.tasks.listed===filtered.filter(validValue).reduce((s,r)=>s+r.tasks_total_for_occupation,0)&&overviewData.tasks.included===filtered.filter(validValue).reduce((s,r)=>s+r.tasks_included,0)`));
await ev(`search.value="no-source-record-matches-this-query";search.dispatchEvent(new Event("input"))`);await sleep(80);
check("an empty search leaves charts explicitly unavailable",await ev(`!overviewData.available&&document.querySelectorAll(".chart-column").length===0&&document.querySelectorAll(".chart-empty").length===3`));
await ev(`search.value="";search.dispatchEvent(new Event("input"));search.focus()`);
check("search has a subtle focus cue instead of thick outline",await ev(`getComputedStyle(search).outlineStyle==="none"&&parseFloat(getComputedStyle(search).borderTopWidth)<=1`));
await ev(`header.scrollIntoView({block:"start"})`);await shot("overview-exposure-desktop",false);
for(const layer of ["employment","wages","education"]){await ev(`selectMode("${layer}")`);await sleep(120);await shot(`overview-${layer}-desktop`,false);}
await ev(`selectMode("exposure");showDetail(records.exposure.find(validValue))`);await sleep(250);
check("sidebar reading text is at least 14px",await ev(`parseFloat(getComputedStyle(riskMeaning).fontSize)>=14`));
check("close icon has a 44px target and an accessible label",await ev(`riskClose.getBoundingClientRect().width>=44&&riskClose.getBoundingClientRect().height>=44&&riskClose.getAttribute("aria-label").includes("Close")`));
await shot("readable-sidebar-desktop",false);await ev(`tabEvidence.click()`);await sleep(100);
check("task statements use readable body type",await ev(`parseFloat(getComputedStyle(taskList.querySelector("summary")).fontSize)>=14`));
await shot("readable-tasks-desktop",false);await ev(`closeDetail()`);
for(const [label,w,h] of [["small-phone",320,740],["phone",390,844],["tablet",820,1180]]){
  await viewport(w,h,true);await ev(`selectMode("exposure")`);await sleep(180);
  check(`${label}: charts and layers cause no page overflow`,await ev(`document.documentElement.scrollWidth<=innerWidth`));
  check(`${label}: all charts remain reachable`,await ev(`overviewCharts.querySelectorAll(".overview-chart").length===3&&[...overviewCharts.querySelectorAll(".overview-chart")].every(n=>n.getBoundingClientRect().height>0)`));
  const dimensions=await ev(`[...colorToggle.children].map(b=>[b.getBoundingClientRect().width,b.getBoundingClientRect().height])`);
  await ev(`selectMode("employment")`);await sleep(100);
  check(`${label}: layer button sizes remain consistent`,JSON.stringify(dimensions)===JSON.stringify(await ev(`[...colorToggle.children].map(b=>[b.getBoundingClientRect().width,b.getBoundingClientRect().height])`)));
  await shot(`overview-${label}`,false);
}
check("no errors in layer/chart improvements",errors.length===0,errors.join(" | "));

// ── Mobile touch ─────────────────────────────────────────────────────────
await viewport(390, 844, true); await load(LOCAL);
await ev(`document.querySelector('#colorToggle button[data-mode="employment"]').click()`); await sleep(300);
check("mobile uses compact layout", await ev(`compactLayout`));
t = await target();
await tap(t.x, t.y); await sleep(80);
check("tap pins compact tooltip", await ev(`tooltip.classList.contains("visible") && tooltip.classList.contains("compact")`));
await sleep(450);
check("tap opens bottom-sheet drawer", await ev(`riskPanel.classList.contains("visible")`));
await shot("local-mobile-drawer", false);
await ev(`riskClose.click()`); await sleep(300);
t = await target();
await tap(t.x, t.y); await sleep(120); await tap(t.x, t.y); await sleep(900);
check("double-tap zooms to box", await ev(`zoom`) > 1.3, `zoom ${(await ev("zoom")).toFixed(2)}`);
check("double-tap does not leave drawer open", !(await ev(`riskPanel.classList.contains("visible")`)));
await ev(`resetZoom(false)`);
t = await target();
await touch("touchStart", [[t.x - 40, t.y], [t.x + 40, t.y]]);
for (let i = 1; i <= 6; i++) { await touch("touchMove", [[t.x - 40 - i * 15, t.y], [t.x + 40 + i * 15, t.y]]); await sleep(16); }
await touch("touchEnd", []); await sleep(300);
check("two-finger pinch zooms", await ev(`zoom`) > 1.5, `zoom ${(await ev("zoom")).toFixed(2)}`);
check("pinch does not open drawer", !(await ev(`riskPanel.classList.contains("visible")`)));
const p0 = await ev(`[panX,panY]`);
await touch("touchStart", [[t.x, t.y]]); for (let i = 1; i <= 5; i++) { await touch("touchMove", [[t.x + i * 20, t.y + i * 10]]); await sleep(16); } await touch("touchEnd", []); await sleep(400);
const p1 = await ev(`[panX,panY]`);
check("one-finger drag pans when zoomed", p0[0] !== p1[0] || p0[1] !== p1[1]);
check("pan does not open drawer", !(await ev(`riskPanel.classList.contains("visible")`)));
await ev(`resetZoom(false)`);
await tap(t.x, t.y); await sleep(500);
check("next tap after gestures still works", await ev(`riskPanel.classList.contains("visible")`));
check("no page errors on mobile", errors.length === 0, errors.join(" | "));

// ── Load failure ─────────────────────────────────────────────────────────
await viewport(1440, 900, false);
await send("Fetch.enable", { patterns: [{ urlPattern: "*data.json*" }] });
listeners.push(d => { if (d.method === "Fetch.requestPaused") send("Fetch.fulfillRequest", { requestId: d.params.requestId, responseCode: 503, body: "" }); });
await load(LOCAL);
check("data-load failure shows explicit error", await ev(`!loadError.hidden && loadError.textContent.includes("503")`), await ev(`loadError.textContent`));
check("failure hides canvas and stats, disables controls", await ev(`canvas.hidden && statsRow.hidden && [...document.querySelectorAll("#colorToggle button")].every(b=>b.disabled)`));
await shot("local-desktop-load-failure", false);
await send("Fetch.disable");

fs.writeFileSync(`${OUT}/results.json`, JSON.stringify(results, null, 1));
console.log(`\n${results.filter(r => r.ok).length}/${results.length} passed`);
ws.close(); chrome.kill(); setTimeout(()=>{try{fs.rmSync(profile,{recursive:true,force:true})}catch{}},500);
setTimeout(()=>process.exit(results.every(r=>r.ok)?0:1),800);
