import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "node",
    include: ["tests/electron/**/*.test.ts"],
    coverage: {
      provider: "v8",
      include: ["src/electron/**/*.ts"],
      exclude: ["src/electron/main/main.ts", "src/electron/main/preload.ts"],
    },
  },
});
