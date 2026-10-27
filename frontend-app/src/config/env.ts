// Single place to read environment variables. Import `env` instead of using
// `import.meta.env` directly so defaults and validation live in one file.
export const env = {
  /** configuration-service API root (auth, configuration, products, FAQs live under it). */
  configurationServiceUrl:
    import.meta.env.VITE_CONFIGURATION_SERVICE_URL ||
    "http://localhost:8000/api",
  /** messaging-service API root (the chat flow: the Chat Sandbox's messages). */
  messagingServiceUrl:
    import.meta.env.VITE_MESSAGING_SERVICE_URL || "http://localhost:8004/api",
  /**
   * Our Meta app, for WhatsApp Embedded Signup ("Connect with Facebook"). Without the app ID and the
   * Facebook Login for Business configuration ID, the button shows but does nothing.
   */
  meta: {
    appId: import.meta.env.VITE_META_APP_ID || "",
    configId: import.meta.env.VITE_META_CONFIG_ID || "",
    graphApiVersion: import.meta.env.VITE_META_GRAPH_API_VERSION || "v26.0",
  },
  /**
   * Google Cloud Identity Platform (Firebase Authentication), for logging in with Google / Facebook
   * (`@/lib/firebase`): the Firebase web app's config. Empty: those buttons show but do nothing.
   */
  firebase: {
    apiKey: import.meta.env.VITE_FIREBASE_API_KEY || "",
    authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN || "",
    projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID || "",
  },
  isDev: import.meta.env.DEV,
} as const;
