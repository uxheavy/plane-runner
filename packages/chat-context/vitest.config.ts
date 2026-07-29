import { playwright } from "@vitest/browser-playwright";
import { defineConfig } from "vitest/config";

export default defineConfig({
  optimizeDeps: {
    include: ["react-grab/primitives"],
  },
  test: {
    include: ["tests/**/*.browser.test.ts"],
    browser: {
      enabled: true,
      headless: true,
      provider: playwright({
        launchOptions: {
          channel: "chrome",
        },
      }),
      instances: [{ browser: "chromium" }],
    },
  },
});
