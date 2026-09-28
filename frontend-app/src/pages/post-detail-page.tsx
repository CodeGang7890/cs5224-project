import { ArrowLeft } from 'lucide-react'
import { Link, useParams } from 'react-router'

import { Button } from '@/components/ui/button'
import { PostDetail } from '@/features/posts'

export function PostDetailPage() {
  const { postId } = useParams()

  return (
    <section className="flex flex-col items-start gap-6">
      <Button variant="ghost" size="sm" asChild>
        <Link to="/posts">
          <ArrowLeft /> Back to posts
        </Link>
      </Button>
      <div className="w-full">
        <PostDetail postId={Number(postId)} />
      </div>
    </section>
  )
}
