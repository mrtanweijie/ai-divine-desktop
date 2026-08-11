/// <reference types="vite/client" />

declare module "*.less";

interface ImportMetaEnv {
  readonly BASE_URL: string;
  readonly MODE: string;
  readonly DEV: boolean;
  readonly PROD: boolean;
  readonly SSR: boolean;
  readonly VITE_SERVICE_API_URL: string;
  readonly VITE_API_DEBUG?: string;
  readonly VITE_DISABLE_CONTEXT_MENU?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
