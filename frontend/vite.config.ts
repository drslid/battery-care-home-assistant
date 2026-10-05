import { readFile, writeFile } from "node:fs/promises";
import { join } from "node:path";
import type { Plugin } from "vite";
import { defineConfig } from "vitest/config";

const LICENSES = "battery-care-panel.licenses.txt";

/**
 * Some bundled licenses are copied with Windows line endings: rewrite them as
 * LF, so that the committed file is the exact output of every build.
 */
function lfLicenses(): Plugin {
  return {
    name: "battery-care:lf-licenses",
    async writeBundle(options) {
      const file = join(options.dir ?? ".", LICENSES);
      const text = await readFile(file, "utf8");
      await writeFile(file, text.replace(/\r\n?/g, "\n"));
    },
  };
}

export default defineConfig({
  plugins: [lfLicenses()],
  build: {
    target: "es2021",
    outDir: "../custom_components/battery_care/frontend",
    emptyOutDir: true,
    reportCompressedSize: false,
    license: { fileName: LICENSES },
    lib: {
      entry: "src/battery-care-panel.ts",
      formats: ["es"],
      fileName: () => "battery-care-panel.js",
    },
    rolldownOptions: {
      output: {
        postBanner:
          "/*! Battery Care panel. Licenses of bundled dependencies: battery-care-panel.licenses.txt */",
      },
    },
  },
  test: {
    environment: "happy-dom",
    include: ["tests/**/*.test.ts"],
  },
});
