// Single place to read environment variables. Import `env` instead of using
// `import.meta.env` directly so defaults and validation live in one file.
export const env = {
  /** configuration-service API root (auth, configuration, products, FAQs live under it). */
  configurationServiceUrl: import.meta.env.VITE_CONFIGURATION_SERVICE_URL || 'http://localhost:8000/api',
  /** messaging-service API root (the chat flow: the Chat Sandbox's messages). */
  messagingServiceUrl: import.meta.env.VITE_MESSAGING_SERVICE_URL || 'http://localhost:8004/api',
  isDev: import.meta.env.DEV,
} as const
