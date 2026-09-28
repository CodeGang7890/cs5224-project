import { APP_NAME } from '@/config/app'
import { FaqManager } from '@/features/faqs'

export function FaqPage() {
  return (
    <section className="flex flex-col gap-6">
      <title>{`FAQ | ${APP_NAME}`}</title>
      <div className="grid gap-1">
        <h1 className="text-2xl font-bold tracking-tight">FAQs</h1>
        <p className="text-muted-foreground text-sm">Manage the frequently asked questions for your business.</p>
      </div>
      <FaqManager />
    </section>
  )
}
