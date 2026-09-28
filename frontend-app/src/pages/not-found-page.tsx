import { Link } from 'react-router'

import { Button } from '@/components/ui/button'

export function NotFoundPage() {
  return (
    <section className="flex flex-col items-center gap-4 py-16 text-center">
      <h1 className="text-4xl font-bold">404</h1>
      <p className="text-muted-foreground">The page you're looking for doesn't exist.</p>
      <Button asChild variant="outline">
        <Link to="/">Go home</Link>
      </Button>
    </section>
  )
}
