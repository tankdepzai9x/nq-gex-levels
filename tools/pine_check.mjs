// Runs pine/nq_gex_levels.pine in the piner engine against tests/fixtures/golden_levels.txt and checks what it draws.
// Usage: node pine_check.mjs
import fs from 'fs';
import { compile, Engine, ArrayFeed } from '@heyphat/piner';

const SRC = fs.readFileSync(new URL('../pine/nq_gex_levels.pine', import.meta.url), 'utf8');
const GOLDEN = fs.readFileSync(new URL('../tests/fixtures/golden_levels.txt', import.meta.url), 'utf8');
const ANCHOR_MS = Number(/^anchor (\d+)/m.exec(GOLDEN)[1]);       // 2026-10-05 20:00 UTC (16:00 ET)
const compiled = compile(SRC);

// Bars of stepMin minutes (5 unless a check says otherwise) from 2026-10-05 13:30Z to 2026-10-06 13:30Z. The bar that closes at the
// anchor closes at 31350. Every later bar closes at 31355 (so a script that anchors on any other bar draws a different level),
// except the very last bar, which closes at 31410 (60 above the anchor bar). With 45-minute bars no bar closes at the anchor.
// gapMin (default: none) lines the bars up so that the last bar closing at or before the anchor closes gapMin minutes before it
// (and is the 31350 bar). A 45-minute chart aligned to the 18:00 ET session start has gapMin 15.
function makeBars(stepMin = 5, gapMin = null) {
  const step = stepMin * 60000;
  const asOfClose = gapMin === null ? ANCHOR_MS : ANCHOR_MS - gapMin * 60000;
  const bars = [];
  let px = 31300;
  const from = Date.parse('2026-10-05T13:30:00Z');
  const start = gapMin === null ? from : asOfClose - Math.floor((asOfClose - from) / step) * step;
  const end = Date.parse('2026-10-06T13:30:00Z');
  for (let t = start; t < end; t += step) {
    const closeT = t + step;
    const last = closeT >= end;
    const c = closeT === asOfClose ? 31350 : closeT > asOfClose ? (last ? 31410 : 31355) : px + Math.sin(t / 3e6) * 4;
    bars.push({ time: t, open: px, high: Math.max(px, c) + 2, low: Math.min(px, c) - 2, close: c, volume: 100 });
    px = c;
  }
  return bars;
}

// set: the Expiry set to select (NEAR unless a check says otherwise; null leaves the input out, so the script's own default applies).
// step: the bar length in minutes (also the chart's timeframe).
// gap: see makeBars (null = the bars as they come, from 13:30Z).
async function run({ paste = GOLDEN, nowIso = '2026-10-06T13:15:00Z', inputs = {}, set = 'NEAR', step = 5, gap = null } = {}) {
  globalThis.__TIMENOW = Date.parse(nowIso);
  const given = { 'Paste levels': paste, ...(set === null ? {} : { 'Expiry set': set }), ...inputs };
  const eng = new Engine(compiled, new ArrayFeed(makeBars(step, gap)), { inputs: given });
  await eng.run({ symbol: 'CME_MINI:NQ1!', timeframe: String(step), mintick: 0.25 });
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
// The golden file holds the same numbers in both sets, so on its own it cannot show WHICH set is drawn. This copy gives WIDE its own.
const TWO_SETS = GOLDEN.slice(0, GOLDEN.indexOf('set WIDE')) +
  ['set WIDE', 'reg N', 'flip -80', 'cw 300', 'pw -150', 'top 25:-', 'em 500', 'prof -50:-10000 0:20000 50:30000', ''].join('\n');
// The golden file with every line that starts with "key " removed: a block that leaves that level out.
const without = (key) => GOLDEN.split('\n').filter((ln) => !ln.startsWith(key + ' ')).join('\n');

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
check('empty paste message says Ctrl+A', r.row0.includes('Ctrl+A'), r.row0);
check('nothing drawn when empty', r.lines.length === 0 && r.labels.length === 0 && r.boxes.length === 0);
r = await run({ paste: GOLDEN, inputs: { 'Expiry set': 'NOPE' } });
check('unknown expiry set message', r.row0.startsWith('Expiry set NOPE was not found'), r.row0);   // not includes(): the regime line prints the set name too
r = await run({ paste: 'GEX1\nhello' });
check('unreadable text message', r.row0.startsWith('Could not read'), r.row0);
check('unreadable text message says Ctrl+A', r.row0.includes('Ctrl+A'), r.row0);
r = await run({ paste: GOLDEN + GOLDEN });
check('two pasted blocks message', r.row0.startsWith('The box holds more than one block'), r.row0);
r = await run({ paste: GOLDEN.replace(/\n/g, '\r\n') });
check('Windows line endings still read', r.row0.startsWith('Positive gamma'), r.row0);
r = await run({ paste: GOLDEN.replace(/(prof [^\n]*) 300:30000/, '$1 3') });
check('a pasted line cut off mid-token does not crash', r.row0.startsWith('Positive gamma'), r.row0);
check('a cut-off token drops only that bar', r.boxes.length === 25, `boxes=${r.boxes.length}`);
r = await run({ paste: GOLDEN.replace(/^anchor \d+/m, 'anchor 1') });
check('anchor before the first bar message', r.row0.startsWith('This chart has no bar'), r.row0);

// 7. the Expiry set picks its own block (the two sets differ in this paste); the script's own default is WIDE
r = await run({ paste: TWO_SETS, set: 'NEAR' });
check('NEAR reads the NEAR block', r.plots['Call wall'] === 31525 && r.plots['Put wall'] === 31125 && r.plots['Zero gamma'] === 31230 && r.row0.startsWith('Positive gamma  |  NEAR'), `${r.row0} ${JSON.stringify(r.plots)}`);
check('NEAR draws the NEAR bars (band + 25)', r.boxes.length === 26, `boxes=${r.boxes.length}`);
r = await run({ paste: TWO_SETS, set: 'WIDE' });
check('WIDE reads the WIDE block', r.plots['Call wall'] === 31650 && r.plots['Put wall'] === 31200 && r.plots['Zero gamma'] === 31270 && r.row0.startsWith('Negative gamma  |  WIDE'), `${r.row0} ${JSON.stringify(r.plots)}`);
check('WIDE draws the WIDE bars (band + 3)', r.boxes.length === 4, `boxes=${r.boxes.length}`);
r = await run({ paste: TWO_SETS, set: null });
check('with no Expiry set chosen the script uses WIDE', r.plots['Call wall'] === 31650 && r.row0.startsWith('Negative gamma  |  WIDE'), `${r.row0} ${JSON.stringify(r.plots)}`);

// 8. a block that leaves a key out: that level is absent, everything else still draws, nothing crashes
r = await run({ paste: without('flip') });
check('no flip line: no zero gamma, nothing else lost', off(r.plots['Zero gamma']) && !names(r).includes('Zero Gamma') && r.boxes.length === 25 && r.lines.length === 2 && r.plots['Call wall'] === 31525 && r.plots['Put wall'] === 31125 && r.row0.startsWith('Positive gamma'), `boxes=${r.boxes.length} lines=${r.lines.length} ${r.row0}`);
r = await run({ paste: without('cw') });
check('no cw line: no call wall, nothing else lost', off(r.plots['Call wall']) && !names(r).includes('Call Wall') && r.lines.length === 1 && r.boxes.length === 26 && r.plots['Put wall'] === 31125 && r.plots['Zero gamma'] === 31230 && r.row0.startsWith('Positive gamma'), `boxes=${r.boxes.length} lines=${r.lines.length} ${r.row0}`);
r = await run({ paste: without('pw') });
check('no pw line: no put wall, nothing else lost', off(r.plots['Put wall']) && !names(r).includes('Put Wall') && r.lines.length === 1 && r.boxes.length === 26 && r.plots['Call wall'] === 31525 && r.plots['Zero gamma'] === 31230 && r.row0.startsWith('Positive gamma'), `boxes=${r.boxes.length} lines=${r.lines.length} ${r.row0}`);
r = await run({ paste: without('top'), inputs: { 'Top strikes (G1 to G5)': true } });
check('no top line: no G labels, nothing else lost', !names(r).some((n) => /G\d/.test(n)) && names(r).includes('Call Wall') && r.boxes.length === 26 && r.row0.startsWith('Positive gamma'), `${names(r).join(',')} boxes=${r.boxes.length} ${r.row0}`);
r = await run({ paste: without('prof') });
check('no prof line: no bars and no bar labels, the levels still draw', r.boxes.length === 1 && !r.labels.some((l) => /^-?[\d.]+[KMB]$/.test(l.text)) && names(r).includes('Call Wall') && r.plots['Call wall'] === 31525 && r.row0.startsWith('Positive gamma'), `boxes=${r.boxes.length} ${r.row0}`);

// 9. a half-pasted number drops only that bar, not the whole bar column
r = await run({ paste: GOLDEN.replace(/(prof [^\n]*) 300:30000/, '$1 300:') });
check('a prof value cut off after the colon (300:) drops only that bar', r.row0.startsWith('Positive gamma') && r.boxes.length === 25, `boxes=${r.boxes.length} ${r.row0}`);
check('the bar labels are still drawn after 300:', r.labels.some((l) => /^-?[\d.]+[KMB]$/.test(l.text)));
r = await run({ paste: GOLDEN.replace(/(prof [^\n]*) 300:30000/, '$1 300:abc') });
check('a prof value that is not a number (300:abc) drops only that bar', r.row0.startsWith('Positive gamma') && r.boxes.length === 25, `boxes=${r.boxes.length} ${r.row0}`);
check('the bar labels are still drawn after 300:abc', r.labels.some((l) => /^-?[\d.]+[KMB]$/.test(l.text)));

// 10. the chart's bars must end at the as-of time (within 5 minutes) or nothing is drawn and the banner says why
r = await run({ step: 1 });
check('1-minute bars: call wall = anchor + 175', r.plots['Call wall'] === 31525 && r.row0.startsWith('Positive gamma'), `${JSON.stringify(r.plots)} ${r.row0}`);
r = await run({ step: 15 });
check('15-minute bars: call wall = anchor + 175', r.plots['Call wall'] === 31525 && r.row0.startsWith('Positive gamma'), `${JSON.stringify(r.plots)} ${r.row0}`);
r = await run({ step: 45 });
check('45-minute bars (none ends at the as-of time): the banner explains', r.row0.startsWith("This chart's bars do not end") && r.row0.includes('(16:00 ET)'), r.row0);
check('45-minute bars: nothing is drawn', r.lines.length === 0 && r.labels.length === 0 && r.boxes.length === 0, `lines=${r.lines.length} labels=${r.labels.length} boxes=${r.boxes.length}`);
check('45-minute bars: no price-scale tags', off(r.plots['Call wall']) && off(r.plots['Put wall']) && off(r.plots['Zero gamma']), JSON.stringify(r.plots));
// 45-minute bars aligned to the 18:00 ET session start: the last bar before 16:00 ET closes at 15:45 ET, exactly 15 minutes early
r = await run({ step: 45, gap: 15 });
check('45-minute bars from the 18:00 ET start (15 minutes early): the banner explains', r.row0.startsWith("This chart's bars do not end") && r.row0.includes('(16:00 ET)'), r.row0);
check('45-minute bars from the 18:00 ET start: nothing is drawn', r.lines.length === 0 && r.labels.length === 0 && r.boxes.length === 0, `lines=${r.lines.length} labels=${r.labels.length} boxes=${r.boxes.length}`);
check('45-minute bars from the 18:00 ET start: no price-scale tags', off(r.plots['Call wall']) && off(r.plots['Put wall']) && off(r.plots['Zero gamma']), JSON.stringify(r.plots));
// the tolerance edge (10-minute bars): a last bar that closes exactly 5 minutes early still draws, 6 minutes early does not
r = await run({ step: 10, gap: 5 });
check('a gap of exactly 5 minutes still draws (call wall = anchor bar + 175)', r.plots['Call wall'] === 31525 && r.row0.startsWith('Positive gamma'), `${JSON.stringify(r.plots)} ${r.row0}`);
r = await run({ step: 10, gap: 6 });
check('a gap of 6 minutes shows the "bars do not end" banner', r.row0.startsWith("This chart's bars do not end") && r.row0.includes('(16:00 ET)'), r.row0);
check('a gap of 6 minutes draws nothing', r.lines.length === 0 && r.labels.length === 0 && r.boxes.length === 0 && off(r.plots['Call wall']), `lines=${r.lines.length} labels=${r.labels.length} boxes=${r.boxes.length} ${JSON.stringify(r.plots)}`);

// 11. the Tag position setting moves only the level tags (Call Wall, Put Wall, Zero Gamma), measured in bars right of the last candle
const TAG_IN = 'Tag position (bars right of price)';
const LAST_BAR = makeBars().length - 1;
const isTag = (l) => ['Call Wall', 'Put Wall', 'Zero Gamma'].includes(l.text);
const tags = (x) => x.labels.filter(isTag);
const tagsOnly = (x) => JSON.stringify(tags(x).map(({ x: _x, ...rest }) => rest));    // everything about the tags except where they sit
const everythingElse = (x) => JSON.stringify([x.lines, x.boxes, x.labels.filter((l) => !isTag(l)), x.row0, x.row1, x.plots]);
const inputLines = SRC.split('\n').filter((ln) => ln.includes(' = input.') && !ln.startsWith('//'));
const lastInput = inputLines[inputLines.length - 1];
check('Tag position is the LAST input of the script, default 2, in the Style group', lastInput.includes(`input.int(2, "${TAG_IN}"`) && lastInput.includes('group = G_STY'), lastInput);
const atDefault = await run();
check('default: the three tags sit 2 bars right of the last bar', tags(atDefault).length === 3 && tags(atDefault).every((l) => l.x === LAST_BAR + 2), JSON.stringify(tags(atDefault).map((l) => l.x)));
r = await run({ inputs: { [TAG_IN]: 100 } });
check('Tag position 100: the three tags sit 100 bars right of the last bar', tags(r).length === 3 && tags(r).every((l) => l.x === LAST_BAR + 100), JSON.stringify(tags(r).map((l) => l.x)));
check('Tag position 100: tag text, colours, styles and heights are unchanged', tags(r).length === 3 && tagsOnly(r) === tagsOnly(atDefault));
check('Tag position 100: lines, band, bars, bar labels, regime line and price-scale tags are unchanged', everythingElse(r) === everythingElse(atDefault));
r = await run({ inputs: { [TAG_IN]: 0 } });
check('Tag position 0: the three tags sit on the last bar', tags(r).length === 3 && tags(r).every((l) => l.x === LAST_BAR), JSON.stringify(tags(r).map((l) => l.x)));
r = await run({ inputs: { [TAG_IN]: 100, Labels: 'Text' } });
check('Tag position 100 with Text labels: the three tags sit 100 bars right of the last bar', tags(r).length === 3 && tags(r).every((l) => l.x === LAST_BAR + 100), JSON.stringify(tags(r).map((l) => l.x)));

// 12. text on the filled tags is readable: white on dark fills (red, green), dark on the light grey; bar labels are light grey
r = await run();
const tagTextOf = (name) => r.labels.find((l) => l.text === name)?.textcolor;
check('Put Wall tag (green fill) has white text', tagTextOf('Put Wall') === '#FFFFFFFF', tagTextOf('Put Wall'));
check('Call Wall tag (red fill) has white text', tagTextOf('Call Wall') === '#FFFFFFFF', tagTextOf('Call Wall'));
check('Zero Gamma tag (light grey fill) keeps dark text', tagTextOf('Zero Gamma') === '#131722FF', tagTextOf('Zero Gamma'));
const barLabels = r.labels.filter((l) => /^-?[\d.]+[KMB]$/.test(l.text));
check('every bar label is light grey, whatever the bar colour', barLabels.length > 0 && barLabels.every((l) => l.textcolor === '#D1D4DCFF'), JSON.stringify(barLabels.map((l) => l.textcolor)));
r = await run({ inputs: { Labels: 'Text' } });
check('Text labels keep the level colour as the text colour', tagTextOf('Put Wall') === '#089981FF', tagTextOf('Put Wall'));

console.log(failures ? `${failures} check(s) failed` : 'all pine checks passed');
process.exit(failures ? 1 : 0);
