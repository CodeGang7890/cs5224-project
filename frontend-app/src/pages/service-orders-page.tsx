import { TabPage } from "@/components/common/tab-page";
import { SchedulesBrowser } from "@/features/orders";

export function ServiceOrdersPage() {
  return (
    <TabPage title="Services" section="Orders">
      <SchedulesBrowser />
    </TabPage>
  );
}
