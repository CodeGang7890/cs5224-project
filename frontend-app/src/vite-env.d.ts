/// <reference types="vite/client" />

// Type declarations for the VITE_* variables in .env files.
// Every variable added to .env.example must also be declared here.
interface ImportMetaEnv {
  readonly VITE_CONFIGURATION_SERVICE_URL: string;
  readonly VITE_META_APP_ID?: string;
  readonly VITE_META_CONFIG_ID?: string;
  readonly VITE_META_GRAPH_API_VERSION?: string;
  readonly VITE_FIREBASE_API_KEY?: string;
  readonly VITE_FIREBASE_AUTH_DOMAIN?: string;
  readonly VITE_FIREBASE_PROJECT_ID?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
