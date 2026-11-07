// Pure adapter/layout tests. These are not browser or visual-acceptance tests.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const js = fs.readFileSync(path.join(root,'site/dashboard.js'),'utf8');
const release = JSON.parse(fs.readFileSync(path.join(root,'site/data.json'),'utf8'));
function adapter() {
  const context=vm.createContext({document:{getElementById:()=>null},Intl,release});
  vm.runInContext(js.split('// Deployed visual shell;')[0],context);
  return expression=>vm.runInContext(expression,context);
}
test('the actual release passes the browser evidence guard',()=>{
  const run=adapter();assert.doesNotThrow(()=>run('assertRelease(release)'));
});
test('missing evidence and fabricated withheld values fail closed',()=>{
  const run=adapter();
  assert.throws(()=>run('const broken=JSON.parse(JSON.stringify(release)); broken.wage_references.find(r=>r.availability === "published").source_file_hash=""; assertRelease(broken)'),/incomplete evidence/);
  assert.throws(()=>run('const fabricated=JSON.parse(JSON.stringify(release)); fabricated.wage_references.find(r=>r.availability !== "published").value=123; assertRelease(fabricated)'),/withheld record/);
});
test('the adapter preserves source values, missingness and population separation',()=>{
  const run=adapter();run('payload=release; buildRecords()');
  assert.equal(run('records.wages.length'),release.wage_references.length);
  assert.equal(run('records.wages.filter(validValue).length'),release.wage_references.filter(r=>r.availability==='published').length);
  assert.equal(run('records.employment.length'),release.occupations.filter(o=>o.level==='psoc_major_group'&&o.metrics.employment_count).length);
  assert.equal(run('records.ofw.find(r=>r.code === "0").value'),null);
  assert.equal(run('Object.keys(records).sort().join(",")'),'employment,exposure,ofw,wages');
  const units=release.occupations.filter(o=>o.level==='psoc_unit_group');
  assert.equal(run('records.exposure.length'),units.length);
  const scored=units.filter(o=>(o.exposure||[]).some(e=>e.dimension==='A'&&e.score!==null)).length;
  assert.equal(run('records.exposure.filter(validValue).length'),scored);
  assert.equal(run('records.exposure.filter(r=>!validValue(r)).every(r=>r.value===null&&["no_psa_tasks","not_scored"].includes(r.availability))'),true);
  assert.equal(run('records.employment.reduce((s,r)=>s+r.value,0)'),release.occupations.filter(o=>o.level==='psoc_major_group').reduce((s,o)=>s+(o.metrics.employment_count?.value??0),0));
});
test('exposure scores without full provenance or two successes fail closed',()=>{
  const run=adapter();
  const withScore=`const d=JSON.parse(JSON.stringify(release)); const u=d.occupations.find(o=>o.level==="psoc_unit_group");
    u.exposure=[{dimension:"A",score:3,model_id:"m",rubric_version:"0.3.0",prompt_version:"0.3.0",scoring_date:"2026-09-28T00:00:00Z",human_review_status:"not_reviewed",raw_response_reference:"r",task_source:"t",attempted_attempts:2,successful_attempts:2}];`;
  assert.doesNotThrow(()=>run(`{${withScore} assertRelease(d)}`));
  assert.throws(()=>run(`{${withScore} u.exposure[0].successful_attempts=1; assertRelease(d)}`),/two successful/);
  assert.throws(()=>run(`{${withScore} u.exposure[0].model_id=""; assertRelease(d)}`),/incomplete provenance/);
  assert.throws(()=>run(`{${withScore} u.exposure[0].score=7; assertRelease(d)}`),/incomplete provenance/);
  assert.throws(()=>run(`{${withScore} d.occupations.find(o=>o.level==="psoc_major_group").exposure=u.exposure; assertRelease(d)}`),/unit groups/);
});
test('layout allocates areas only in proportion to explicit weights',()=>{
  const run=adapter();const rects=run('squarify([{weight:1},{weight:3},{weight:6}],0,0,500,300)');
  for(const r of rects)assert.ok(Math.abs(r.w*r.h-150000*r.weight/10)<1e-7);
  assert.equal(run('squarify([],0,0,500,300).length'),0);
});
