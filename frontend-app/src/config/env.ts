// Single place to read environment variables. Import `env` instead of using
// `import.meta.env` directly so defaults and validation live in one file.
export const env = {
  configurationServiceUrl:
    import.meta.env.VITE_CONFIGURATION_SERVICE_URL || 'http://localhost:8000/api/configuration',
  isDev: import.meta.env.DEV,
} as const
