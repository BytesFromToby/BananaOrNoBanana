// Committed guard: fail if a secret ever lands in the arena tree. The maintainer key is
// set via `wrangler secret put`, never committed; keys live only in .dev.vars (gitignored).
import { describe, it, expect } from "vitest";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const arenaRoot = join(dirname(fileURLToPath(import.meta.url)), "..");
const SKIP_DIRS = new Set(["node_modules", ".wrangler", ".git"]);
const SKIP_FILES = new Set(["no_secrets.test.js"]);

// Patterns that would indicate a real leaked secret.
const SECRET_PATTERNS = [
  /sk-[a-zA-Z0-9]{20,}/,            // OpenAI-style keys
  /sk-ant-[a-zA-Z0-9-]{20,}/,      // Anthropic keys
  /\bAKIA[0-9A-Z]{16}\b/,          // AWS access key id
];

function walk(dir) {
  const out = [];
  for (const name of readdirSync(dir)) {
    if (SKIP_DIRS.has(name)) continue;
    const full = join(dir, name);
    if (statSync(full).isDirectory()) out.push(...walk(full));
    else if (!SKIP_FILES.has(name)) out.push(full);
  }
  return out;
}

describe("no committed secrets", () => {
  it("no source file contains a secret-shaped string or a set MAINTAINER_KEY value", () => {
    const offenders = [];
    for (const file of walk(arenaRoot)) {
      let text;
      try { text = readFileSync(file, "utf-8"); } catch { continue; }
      // Real provider-key shapes must never appear anywhere — including tests.
      for (const re of SECRET_PATTERNS) {
        if (re.test(text)) offenders.push(`${file}: ${re}`);
      }
      // MAINTAINER_KEY must never be assigned a value in NON-test committed files
      // (src/config/docs). Test files legitimately pass a fake key to exercise auth.
      const isTest = file.replace(/\\/g, "/").includes("/test/");
      if (!isTest) {
        const m = text.match(/MAINTAINER_KEY\s*[:=]\s*["'][^"']+["']/);
        if (m) offenders.push(`${file}: assigns MAINTAINER_KEY (${m[0]})`);
      }
    }
    expect(offenders).toEqual([]);
  });
});
