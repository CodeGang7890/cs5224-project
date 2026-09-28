// Single place to read environment variables. Import `env` instead of using
// `import.meta.env` directly so defaults and validation live in one file.
export const env = {
  apiBaseUrl: import.meta.env.VITE_API_BASE_URL || 'https://jsonplaceholder.typicode.com',
  isDev: import.meta.env.DEV,
} as const
