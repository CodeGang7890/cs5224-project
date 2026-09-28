import { PostList } from '@/features/posts'

export function PostsPage() {
  return (
    <section className="flex flex-col gap-6">
      <h1 className="text-2xl font-bold tracking-tight">Posts</h1>
      <PostList />
    </section>
  )
}
