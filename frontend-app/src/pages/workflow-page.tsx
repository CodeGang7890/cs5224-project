import { APP_NAME } from '@/config/app'
import { WorkflowBuilder } from '@/features/workflow'

export function WorkflowPage() {
  return (
    <section className="flex flex-col gap-6">
      <title>{`Workflow | ${APP_NAME}`}</title>
      <div className="grid gap-1">
        <h1 className="text-2xl font-bold tracking-tight">Workflow</h1>
        <p className="text-muted-foreground text-sm">
          How your chat assistant handles each customer message. Click a step to see what it does or to change its settings.
        </p>
      </div>
      <WorkflowBuilder />
    </section>
  )
}
