import { APP_NAME } from '@/config/app'

/** Simple page body with a heading, used for pages whose content isn't built yet. */
export function PagePlaceholder({ title }: { title: string }) {
  return (
    <section className="flex flex-col gap-2">
      {/* React 19 hoists <title> into <head>, keeping the browser tab in sync with the route. */}
      <title>{`${title} | ${APP_NAME}`}</title>
      <h1 className="text-2xl font-bold tracking-tight">{title}</h1>
      <p className="text-muted-foreground">{title} content coming soon.</p>
    </section>
  )
}
