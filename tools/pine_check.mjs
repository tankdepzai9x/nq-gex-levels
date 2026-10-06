// Runs pine/nq_gex_levels.pine in the piner engine against tests/fixtures/golden_levels.txt and checks what it draws.
// Usage: node pine_check.mjs
import fs from 'fs';
import { compile, Engine, ArrayFeed } from '@heyphat/piner';

const SRC = fs.readFileSync(new URL('../pine/nq_gex_levels.pine', import.meta.url), 'utf8');
const GOLDEN = fs.readFileSync(new URL('../tests/fixtures/golden_levels.txt', import.meta.url), 'utf8');
const ANCHOR_MS = Number(/^anchor (\d+)/m.exec(GOLDEN)[1]);       // 2026-10-05 20:00 UTC (16:00 ET)
const compiled = compile(SRC);

// 5-minute bars from 2026-10-05 13:30Z to 2026-10-06 13:30Z. The bar that closes at the anchor closes at 31350,
// price then stays flat, and the very last bar closes 60 points higher.
function makeBars() {
  const bars = [];
  let px = 31300;
  const start = Date.parse('2026-10-05T13:30:00Z');
  const end = Date.parse('2026-10-06T13:30:00Z');
  for (let t = start; t < end; t += 300000) {
    const closeT = t + 300000;
    const last = closeT >= end;
    const c = closeT === ANCHOR_MS ? 31350 : closeT > ANCHOR_MS ? (last ? 31410 : 31350) : px + Math.sin(t / 3e6) * 4;
    bars.push({ time: t, open: px, high: Math.max(px, c) + 2, low: Math.min(px, c) - 2, close: c, volume: 100 });
    px = c;
  }
  return bars;
}

async function run({ paste = GOLDEN, nowIso = '2026-10-06T13:15:00Z', inputs = {} } = {}) {
  globalThis.__TIMENOW = Date.parse(nowIso);
  const eng = new Engine(compiled, new ArrayFeed(makeBars()), { inputs: { 'Paste levels': paste, 'Expiry set': 'NEAR', ...inputs } });
  await eng.run({ symbol: 'CME_MINI:NQ1!', timeframe: '5', mintick: 0.25 });
  const kind = (d) => d.kind ?? d.type;
  const of = (k) => eng.drawings.filter((d) => kind(d) === k);
  const plots = {};
  for (const [, p] of eng.outputs.plots) plots[p.title] = p.data[p.data.length - 1];
  const table = of('table')[0]?.props.cells ?? {};
  return {
    plots,
    lines: of('line').map((d) => d.props),
    labels: of('label').map((d) => d.props),
    boxes: of('box').map((d) => d.props),
    row0: table['0,0']?.text ?? '',
    row1: table['0,1']?.text ?? '',
  };
}

let failures = 0;
function check(name, cond, detail = '') {
  if (cond) console.log('ok   ' + name);
  else { failures++; console.log('FAIL ' + name + (detail ? '  ' + detail : '')); }
}
const names = (r) => r.labels.map((l) => l.text);
const off = (v) => v == null || Number.isNaN(v);   // a switched-off plot has no value on the last bar

// 1. defaults: call wall, put wall, zero gamma, bars, regime line
let r = await run();
check('call wall = chart price at the as-of time + 175', r.plots['Call wall'] === 31525, JSON.stringify(r.plots));
check('put wall = anchor - 225', r.plots['Put wall'] === 31125);
check('zero gamma = anchor - 120', r.plots['Zero gamma'] === 31230);
check('1D range is off by default', off(r.plots['1D Max']) && off(r.plots['1D Min']));
check('tags: Call Wall, Put Wall, Zero Gamma', ['Call Wall', 'Put Wall', 'Zero Gamma'].every((n) => names(r).includes(n)), names(r).join(','));
check('no G1..G5 or 1D labels by default', !names(r).some((n) => /^G\d|1D/.test(n)));
check('two lines (call wall, put wall); zero gamma is a band', r.lines.length === 2, `lines=${r.lines.length}`);
check('one band + 25 bars', r.boxes.length === 26, `boxes=${r.boxes.length}`);
const boxAt = (y) => r.boxes.find((b) => b.top === y + 7.5);
check('positive GEX bar is green', boxAt(31350)?.bgcolor?.startsWith('#089981'), JSON.stringify(boxAt(31350)));
check('negative GEX bar is red', boxAt(31125)?.bgcolor?.startsWith('#F23645'), JSON.stringify(boxAt(31125)));
check('bar length follows size (biggest bar = width 30)', r.boxes.some((b) => b.top === 31357.5 && b.right - b.left === 30));
check('bar labels are K/M/B text', r.labels.some((l) => /^-?[\d.]+[KMB]$/.test(l.text)));
check('regime line', r.row0 === 'Positive gamma  |  NEAR  |  data 08:45 ET (30 min old)', r.row0);
check('no warning when fresh and flat', r.row1 === '' || r.row1 === undefined, r.row1);

// 2. everything on: top strikes merge with the call wall, 1D range appears
r = await run({ inputs: { 'Top strikes (G1 to G5)': true, '1D range (max / min)': true } });
check('G label merged into the Call Wall tag', names(r).some((n) => n.startsWith('Call Wall | G')), names(r).join(','));
check('1D Max / 1D Min drawn', names(r).includes('1D Max') && names(r).includes('1D Min'));
check('1D Max = anchor + 365', r.plots['1D Max'] === 31715);

// 3. Text labels have no fill
r = await run({ inputs: { Labels: 'Text' } });
check('Text style = transparent label background', r.labels.find((l) => l.text === 'Call Wall')?.color?.__na === true);

// 4. each level can be switched off
r = await run({ inputs: { 'Call wall': false, 'Show': false } });
check('call wall off', off(r.plots['Call wall']) && !names(r).includes('Call Wall'));
check('bars off (no bar boxes)', r.boxes.length === 1, `boxes=${r.boxes.length}`);

// 5. warnings
r = await run({ nowIso: '2026-10-06T23:30:00Z' });
check('stale after the due time', r.row1.startsWith('STALE') && r.row1.includes('19:00 ET'), r.row1);
r = await run({ inputs: { 'Warn when NQ has moved (%) since the data': 0.1 } });
check('moved warning', r.row1.startsWith('NQ moved 0.19%'), r.row1);

// 6. problems are explained, not drawn
r = await run({ paste: '' });
check('empty paste message', r.row0.startsWith('Paste the levels'), r.row0);
check('nothing drawn when empty', r.lines.length === 0 && r.labels.length === 0 && r.boxes.length === 0);
r = await run({ paste: GOLDEN, inputs: { 'Expiry set': 'NOPE' } });
check('unknown expiry set message', r.row0.includes('NOPE'), r.row0);
r = await run({ paste: 'GEX1\nhello' });
check('unreadable text message', r.row0.startsWith('Could not read'), r.row0);
r = await run({ paste: GOLDEN + GOLDEN });
check('two pasted blocks message', r.row0.startsWith('The box holds more than one block'), r.row0);
r = await run({ paste: GOLDEN.replace(/\n/g, '\r\n') });
check('Windows line endings still read', r.row0.startsWith('Positive gamma'), r.row0);
r = await run({ paste: GOLDEN.replace(/(prof [^\n]*) 300:30000/, '$1 3') });
check('a pasted line cut off mid-token does not crash', r.row0.startsWith('Positive gamma'), r.row0);
check('a cut-off token drops only that bar', r.boxes.length === 25, `boxes=${r.boxes.length}`);
r = await run({ paste: GOLDEN.replace(/^anchor \d+/m, 'anchor 1') });
check('anchor before the first bar message', r.row0.startsWith('This chart has no bar'), r.row0);

console.log(failures ? `${failures} check(s) failed` : 'all pine checks passed');
process.exit(failures ? 1 : 0);
