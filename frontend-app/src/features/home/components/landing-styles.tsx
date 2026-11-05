/**
 * The landing page's own keyframes (Tailwind and tw-animate-css have no float / marquee / moving gradient).
 * React hoists this `<style>` into `<head>` once, so nothing outside the Home page changes.
 */
export function LandingStyles() {
  return (
    <style href="home-landing-animations" precedence="default">{`
@keyframes landing-float {
  0%, 100% { transform: translate(0, 0) scale(1); }
  50% { transform: translate(24px, -32px) scale(1.08); }
}
@keyframes landing-marquee {
  from { transform: translateX(0); }
  to { transform: translateX(-50%); }
}
@keyframes landing-gradient {
  0%, 100% { background-position: 0% 50%; }
  50% { background-position: 100% 50%; }
}
`}</style>
  );
}
