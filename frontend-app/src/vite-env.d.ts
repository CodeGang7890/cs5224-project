/// <reference types="vite/client" />

// Type declarations for the VITE_* variables in .env files.
// Every variable added to .env.example must also be declared here.
interface ImportMetaEnv {
  readonly VITE_API_BASE_URL: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
