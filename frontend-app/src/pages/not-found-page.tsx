import { Link } from 'react-router'

import { Button } from '@/components/ui/button'
import { APP_NAME } from '@/config/app'

export function NotFoundPage() {
  return (
    <section className="flex flex-col items-center gap-4 py-16 text-center">
      <title>{`Page not found | ${APP_NAME}`}</title>
      <h1 className="text-4xl font-bold">404</h1>
      <p className="text-muted-foreground">The page you're looking for doesn't exist.</p>
      <Button asChild variant="outline">
        <Link to="/">Go home</Link>
      </Button>
    </section>
  )
}
