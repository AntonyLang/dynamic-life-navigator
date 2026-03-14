import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  base: "./",
  plugins: [react()],
  resolve: {
    preserveSymlinks: true,
  },
  server: {
    port: 5174,
  },
  build: {
    rollupOptions: {
      input: {
        index: "index.html",
      },
    },
  },
  test: {
    globals: true,
    environment: "jsdom",
    css: true,
  },
});
