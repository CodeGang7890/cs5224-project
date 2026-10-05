// Public API of the workflow (chat configuration) feature.
export { BLOCK_META } from './blocks'
export { blockDetailFields, DEFAULT_DETAIL_FIELDS } from './details'
export { WorkflowBuilder } from './components/workflow-builder'
export {
  chatConfigurationKeys,
  useChatConfiguration,
  useSaveChatConfiguration,
} from './hooks/use-chat-configuration'
export { useDetailLabels } from './hooks/use-detail-labels'
export { DETAILS_COLLECTION_BLOCK, SEND_MESSAGE_BLOCK } from './types'
export type { BlockType, ChatBlock, ChatConfiguration, ChatConfigurationInput, DetailField, DetailFieldType } from './types'
