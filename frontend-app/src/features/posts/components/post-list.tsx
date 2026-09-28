import { Link } from 'react-router'

import { Button } from '@/components/ui/button'
import { Card, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'

import { usePosts } from '../hooks/use-posts'

export function PostList() {
  const { data: posts, isPending, isError, error, refetch } = usePosts()

  if (isPending) {
    return (
      <div className="grid gap-4">
        {Array.from({ length: 3 }, (_, i) => (
          <Skeleton key={i} className="h-24 w-full" />
        ))}
      </div>
    )
  }

  if (isError) {
    return (
      <div className="flex flex-col items-start gap-3 rounded-lg border border-destructive/50 p-4">
        <p className="text-destructive text-sm">Failed to load posts: {error.message}</p>
        <Button variant="outline" size="sm" onClick={() => refetch()}>
          Try again
        </Button>
      </div>
    )
  }

  return (
    <div className="grid gap-4">
      {posts.map((post) => (
        <Link key={post.id} to={`/posts/${post.id}`}>
          <Card className="hover:bg-accent/50 transition-colors">
            <CardHeader>
              <CardTitle className="capitalize">{post.title}</CardTitle>
              <CardDescription className="line-clamp-2">{post.body}</CardDescription>
            </CardHeader>
          </Card>
        </Link>
      ))}
    </div>
  )
}
