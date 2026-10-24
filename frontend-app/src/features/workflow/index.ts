// Public API of the workflow (chat configuration) feature.
export { DEFAULT_DETAIL_FIELDS, detailFieldsOrDefault } from "./details";
export { CHAT_STEP_LABELS } from "./steps";
export { WorkflowBuilder } from "./components/workflow-builder";
export {
  chatConfigurationKeys,
  useChatConfiguration,
  useSaveChatConfiguration,
} from "./hooks/use-chat-configuration";
export { useDetailLabels, type DetailsKind } from "./hooks/use-detail-labels";
export { CHAT_STEPS } from "./types";
export type {
  ChatConfiguration,
  ChatConfigurationInput,
  ChatStep,
  DetailField,
  DetailFieldType,
} from "./types";
