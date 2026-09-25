import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev: Vite on :5173 proxies /api (incl. SSE) to FastAPI on :8000.
// Prod: `npm run build` → web/dist, served by FastAPI at /.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": { target: "http://127.0.0.1:8000", changeOrigin: true } },
  },
});
