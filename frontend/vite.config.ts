import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/reports": { target: "http://localhost:8000", changeOrigin: true },
      "/research": { target: "http://localhost:8000", changeOrigin: true },
    },
  },
});
