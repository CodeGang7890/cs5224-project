import { APP_NAME } from '@/config/app'
import { ServiceManager } from '@/features/services'

export function ServicePage() {
  return (
    <section className="flex flex-col gap-6">
      <title>{`Service | ${APP_NAME}`}</title>
      <div className="grid gap-1">
        <h1 className="text-2xl font-bold tracking-tight">Services</h1>
        <p className="text-muted-foreground text-sm">
          What customers can book a time for in a chat, and when each person on your team is available.
        </p>
      </div>
      <ServiceManager />
    </section>
  )
}
