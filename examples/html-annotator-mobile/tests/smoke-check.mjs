import { readFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = dirname(dirname(fileURLToPath(import.meta.url)));

const requiredFiles = [
  "index.html",
  "manifest.webmanifest",
  "src/app.js",
  "src/styles.css",
  "samples/article.html",
  "PRD.md",
  "ARCHITECTURE.md",
  "CODEMAP.md",
  "CONVENTIONS.md",
  "prompts/DISCUSSION_AI.md",
  "prompts/EXECUTION_AI.md",
  ".tasks/build/001-mobile-html-annotator.md",
  "reports/DEV_REPORT.md"
];

for (const file of requiredFiles) {
  await readFile(join(root, file), "utf8");
}

const html = await readFile(join(root, "index.html"), "utf8");
const app = await readFile(join(root, "src/app.js"), "utf8");
const report = await readFile(join(root, "reports/DEV_REPORT.md"), "utf8");

const assertions = [
  [html.includes('id="document-content"'), "document content mount exists"],
  [html.includes('id="capture-button"'), "capture button exists"],
  [html.includes('id="export-output"'), "export output exists"],
  [app.includes("function getCurrentSelection"), "selection capture code exists"],
  [app.includes("setPendingRange"), "pending annotation staging exists"],
  [app.includes("Block staged"), "tap-to-stage block fallback exists"],
  [app.includes("function exportAnnotations"), "JSON export code exists"],
  [app.includes("localStorage"), "state persistence exists"],
  [report.includes("node tests/smoke-check.mjs"), "Dev Report records smoke test"]
];

for (const [passed, message] of assertions) {
  if (!passed) {
    throw new Error(`Smoke check failed: ${message}`);
  }
}

console.log("Mobile HTML Annotator smoke check passed.");
