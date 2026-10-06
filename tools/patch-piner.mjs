// The piner engine (a clean-room Pine v6 runtime used only for these checks) ties `timenow` to the last bar.
// This patch lets a check set globalThis.__TIMENOW so the "data age" and "stale" banner can be tested. Idempotent.
import fs from 'fs';
import { createRequire } from 'module';
const require = createRequire(import.meta.url);
const dist = require.resolve('@heyphat/piner').replace(/index\.c?js$/, '');
const from = '  get timenow() {\n    const lbt';
const to = '  get timenow() {\n    if (globalThis.__TIMENOW != null) return globalThis.__TIMENOW;\n    const lbt';
for (const f of ['index.js', 'index.cjs']) {
  const p = dist + f;
  let s = fs.readFileSync(p, 'utf8');
  if (s.includes(to)) continue;
  if (!s.includes(from)) throw new Error(`piner patch target not found in ${f}`);
  fs.writeFileSync(p, s.replace(from, to));
}
console.log('piner patched');
