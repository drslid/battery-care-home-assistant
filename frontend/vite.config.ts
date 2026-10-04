import { defineConfig } from "vitest/config";

export default defineConfig({
  build: {
    target: "es2021",
    outDir: "../custom_components/battery_care/frontend",
    emptyOutDir: true,
    reportCompressedSize: false,
    license: { fileName: "battery-care-panel.licenses.txt" },
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
