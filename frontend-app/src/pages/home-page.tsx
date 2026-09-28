import { APP_NAME } from '@/config/app'
import { RandomNumberCard } from '@/features/random-number'

export function HomePage() {
  return (
    <section className="flex flex-col gap-6">
      <title>{`Home | ${APP_NAME}`}</title>
      <h1 className="text-2xl font-bold tracking-tight">Home</h1>
      <RandomNumberCard />
    </section>
  )
}
