// Single place to read environment variables. Import `env` instead of using
// `import.meta.env` directly so defaults and validation live in one file.
export const env = {
  /** configuration-service API root (auth, configuration, products, FAQs live under it). */
  configurationServiceUrl: import.meta.env.VITE_CONFIGURATION_SERVICE_URL || 'http://localhost:8000/api',
  isDev: import.meta.env.DEV,
} as const
