import { TabPage } from '@/components/common/tab-page'
import { ServiceManager } from '@/features/services'

export function ServicePage() {
  return (
    <TabPage
      title="Services"
      section="Catalog"
      description="What customers can book a time for in a chat, and when each person on your team is available."
    >
      <ServiceManager />
    </TabPage>
  )
}
