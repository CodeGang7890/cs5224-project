import { APP_NAME } from "@/config/app";
import { BusinessHome, Landing } from "@/features/home";
import { selectIsAuthenticated, useAuthStore } from "@/stores/auth-store";

export function HomePage() {
  const isAuthenticated = useAuthStore(selectIsAuthenticated);
  return (
    <section className="flex flex-col gap-6">
      <title>{`Home | ${APP_NAME}`}</title>
      {isAuthenticated ? <BusinessHome /> : <Landing />}
    </section>
  );
}
