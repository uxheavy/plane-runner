import { defineConfig } from "tsdown";

export default defineConfig({
  entry: ["src/index.ts", "src/html2canvas-pro.ts"],
  format: ["esm"],
  dts: true,
  exports: true,
});
