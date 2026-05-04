import { defineConfig } from "vite";
import react from "@vitejs/plugin-react-swc";
import path from "path";

// PLAN.md §1, §13.1: prod runs on :8080 with HMR via paperswithcode.co; staging on
// :8081 with HMR via wss://staging.paperswithcode.co. Switch via `vite --mode staging`.
export default defineConfig(({ mode }) => {
  const isStaging = mode === "staging";

  return {
    server: {
      host: "::",
      port: isStaging ? 8081 : 8080,
      strictPort: true,
      allowedHosts: isStaging
        ? ["staging.paperswithcode.co"]
        : ["paperswithcode.co", "www.paperswithcode.co"],
      hmr: isStaging
        ? {
            host: "staging.paperswithcode.co",
            protocol: "wss",
            clientPort: 443,
          }
        : {
            host: "paperswithcode.co",
            clientPort: 443,
          },
      proxy: {
        "/api": {
          target: "http://127.0.0.1:8000",
          changeOrigin: true,
          secure: false,
        },
      },
    },
    plugins: [react()],
    resolve: {
      alias: {
        "@": path.resolve(__dirname, "./src"),
      },
    },
  };
});
