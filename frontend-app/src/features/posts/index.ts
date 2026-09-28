// Public API of the posts feature. Import from '@/features/posts', not from its internal files.
export { PostDetail } from './components/post-detail'
export { PostList } from './components/post-list'
export { postKeys, usePost, usePosts } from './hooks/use-posts'
export type { Post } from './types'
