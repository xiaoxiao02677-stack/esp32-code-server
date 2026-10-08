// Temporary QA script: rough tag-balance check for Vue <template> sections.
// Usage: node tag-balance-check.js <file.vue>
const fs = require("fs");
const path = process.argv[2];
if (!path) {
  console.error("usage: node tag-balance-check.js <file.vue>");
  process.exit(2);
}
const src = fs.readFileSync(path, "utf8");
const lines = src.split(/\r?\n/);

// Locate top-level <template> block: first line starting with <template> .. last line </template>
const startIdx = lines.findIndex((l) => /^<template>\s*$/.test(l.trim()) || l.trim() === "<template>");
const endIdx = lines.map((l) => l.trim()).lastIndexOf("</template>");
if (startIdx === -1 || endIdx === -1 || endIdx <= startIdx) {
  console.error("FATAL: could not locate outer <template> block");
  process.exit(2);
}
const tmpl = lines.slice(startIdx, endIdx + 1).join("\n");

const VOID = new Set(["img", "br", "hr", "input", "meta", "link", "source", "area", "base", "col", "embed", "param", "track", "wbr"]);

// Tokenize: walk chars, respect comments and quoted attr values
const stack = [];
const errors = [];
let lineNo = 1;
let i = 0;
const n = tmpl.length;
function lineOf(pos) {
  let c = 1;
  for (let k = 0; k < pos; k++) if (tmpl[k] === "\n") c++;
  return c;
}
while (i < n) {
  const ch = tmpl[i];
  if (ch === "\n") { lineNo++; i++; continue; }
  // comments
  if (ch === "<" && tmpl.startsWith("<!--", i)) {
    const close = tmpl.indexOf("-->", i + 4);
    if (close === -1) { errors.push(`line ${lineOf(i)}: unclosed comment`); break; }
    for (let k = i; k < close + 3; k++) if (tmpl[k] === "\n") lineNo++;
    i = close + 3;
    continue;
  }
  // closing tag
  if (ch === "<" && tmpl[i + 1] === "/") {
    const gt = tmpl.indexOf(">", i);
    if (gt === -1) { errors.push(`line ${lineOf(i)}: malformed closing tag (no '>')`); break; }
    const name = tmpl.slice(i + 2, gt).trim().split(/\s+/)[0];
    const top = stack.pop();
    if (!top) {
      errors.push(`line ${lineNo}: closing </${name}> with empty stack`);
    } else if (top.name !== name) {
      errors.push(`line ${lineNo}: closing </${name}> does not match open <${top.name}> (opened at content line ${top.line})`);
      // try to resync: pop until match
      let idx = -1;
      for (let s = stack.length - 1; s >= 0; s--) if (stack[s].name === name) { idx = s; break; }
      if (idx !== -1) { stack.length = idx; } else { stack.push(top); }
    }
    i = gt + 1;
    continue;
  }
  // opening tag
  if (ch === "<" && /[a-zA-Z]/.test(tmpl[i + 1] || "")) {
    const tagStart = i;
    let j = i + 1;
    let selfClose = false;
    let quote = null;
    while (j < n) {
      const cj = tmpl[j];
      if (quote) {
        if (cj === quote) quote = null;
      } else if (cj === '"' || cj === "'") {
        quote = cj;
      } else if (cj === ">") {
        break;
      }
      j++;
    }
    if (j >= n) { errors.push(`line ${lineNo}: malformed opening tag (no '>')`); break; }
    const raw = tmpl.slice(tagStart, j); // without '>'
    selfClose = raw.trimEnd().endsWith("/");
    const name = raw.slice(1).trim().split(/[\s/>]/)[0];
    if (!selfClose && !VOID.has(name.toLowerCase())) {
      stack.push({ name, line: lineNo });
    }
    for (let k = tagStart; k <= j; k++) if (tmpl[k] === "\n") lineNo++;
    i = j + 1;
    continue;
  }
  i++;
}

if (stack.length) {
  for (const t of stack) errors.push(`line ${t.line}: unclosed <${t.name}>`);
}

if (errors.length) {
  console.log(`FAIL ${path}`);
  for (const e of errors) console.log("  " + e);
  process.exit(1);
} else {
  console.log(`PASS ${path} (template lines ${startIdx + 1}-${endIdx + 1}, tags balanced)`);
  process.exit(0);
}
