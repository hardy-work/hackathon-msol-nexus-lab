import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// During `npm run dev`, proxy API + SSE to the FastAPI backend on :8080 so the
// frontend and backend behave as one origin. In production the backend serves
// the built files directly, so no proxy is needed.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": {
        target: "http://localhost:8080",
        changeOrigin: true,
      },
    },
  },
});
