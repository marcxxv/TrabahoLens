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
check("tooltip rows use deployed label/value layout", await ev(`document.querySelectorAll("#tooltip .tt-stats .label").length`) === 6);
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
