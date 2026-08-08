import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath, URL } from "node:url";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const serviceApiUrl = env.VITE_SERVICE_API_URL?.replace(/\/+$/, "") || "";
  const apiTarget = serviceApiUrl.replace(/\/api\/?$/, "");

  return {
    plugins: [react()],
    resolve: {
      alias: {
        "@": fileURLToPath(new URL("./src", import.meta.url)),
      },
    },
    server: {
      port: 5173,
      ...(apiTarget
        ? {
            proxy: {
              "/api": {
                target: apiTarget,
                changeOrigin: true,
              },
            },
          }
        : {}),
    },
  };
});
