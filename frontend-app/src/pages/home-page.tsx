import { APP_NAME } from "@/config/app";
import { CreateBusinessCard, useNeedsBusiness } from "@/features/business";
import { RandomNumberCard } from "@/features/random-number";
import { WhatsAppSettingsCard } from "@/features/whatsapp";

export function HomePage() {
  // A new account sets up its business first; WhatsApp is connected after that.
  const needsBusiness = useNeedsBusiness();
  return (
    <section className="flex flex-col gap-6">
      <title>{`Home | ${APP_NAME}`}</title>
      <h1 className="text-2xl font-bold tracking-tight">Home</h1>
      {needsBusiness ? <CreateBusinessCard /> : <WhatsAppSettingsCard />}
      <RandomNumberCard />
    </section>
  );
}
