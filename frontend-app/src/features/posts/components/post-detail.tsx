import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'

import { usePost } from '../hooks/use-posts'

export function PostDetail({ postId }: { postId: number }) {
  const { data: post, isPending, isError, error } = usePost(postId)

  if (isPending) return <Skeleton className="h-48 w-full" />

  if (isError) {
    return <p className="text-destructive text-sm">Failed to load post: {error.message}</p>
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-xl capitalize">{post.title}</CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-muted-foreground leading-relaxed">{post.body}</p>
      </CardContent>
    </Card>
  )
}
