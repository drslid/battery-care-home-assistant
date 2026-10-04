import { readFileSync } from "node:fs";
import { gzipSync } from "node:zlib";

const bundle = new URL(
  "../../custom_components/battery_care/frontend/battery-care-panel.js",
  import.meta.url,
);
const budget = 150 * 1024;
const size = gzipSync(readFileSync(bundle)).length;

console.log(
  `battery-care-panel.js: ${(size / 1024).toFixed(1)} KiB gzipped (budget ${budget / 1024} KiB)`,
);
if (size > budget) {
  console.error("The panel bundle exceeds its size budget.");
  process.exit(1);
}
