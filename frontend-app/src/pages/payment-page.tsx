import { TabPage } from "@/components/common/tab-page";
import { PaymentBrowser } from "@/features/orders";
import { PaymentExpiryCard } from "@/features/business";

export function PaymentPage() {
  return (
    <TabPage
      title="Payment"
      section="Orders"
      description="Your orders and bookings, with their payment status and Xendit payment links."
    >
      <PaymentExpiryCard />
      <PaymentBrowser />
    </TabPage>
  );
}
