import { Link } from 'react-router'

import { Button } from '@/components/ui/button'

export function HomePage() {
  return (
    <section className="flex flex-col items-start gap-4">
      <h1 className="text-3xl font-bold tracking-tight">Welcome</h1>
      <p className="text-muted-foreground max-w-prose">
        React + TypeScript + Vite single-page app with React Router, TanStack Query, Axios, Zustand,
        Tailwind CSS and shadcn/ui.
      </p>
      <Button asChild>
        <Link to="/posts">View example posts</Link>
      </Button>
    </section>
  )
}
