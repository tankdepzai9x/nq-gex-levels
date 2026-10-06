// Static Pine v6 checks (unknown functions/parameters, scope rules). Usage: node lint.cjs ../pine/nq_gex_levels.pine
const fs = require('fs');
const { validatePineScript } = require('pinescript-v6-validator');
const src = fs.readFileSync(process.argv[2], 'utf8');
const lines = src.split('\n');
// S1 (repainting) is a style warning that does not apply to a script that only draws pasted levels.
const res = validatePineScript(src).filter(e => !/^\[S1\]/.test(e.message));
for (const e of res) console.log(`${e.line}:${e.column} [${e.severity === 0 ? 'ERR' : 'WARN'}] ${e.message}\n    ${(lines[e.line - 1] || '').trim()}`);
console.log(res.length ? `${res.length} finding(s)` : 'lint: clean');
process.exit(res.some(e => e.severity === 0) ? 1 : 0);
