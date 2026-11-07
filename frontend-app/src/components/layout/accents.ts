/** Each section's colour (full class names, so Tailwind generates them). */
export type Accent = "emerald" | "violet" | "amber" | "sky";

export const ACCENTS: Record<
  Accent,
  { banner: string; tile: string; tab: string; tabHover: string }
> = {
  emerald: {
    banner: "from-emerald-50 dark:from-emerald-950/40",
    tile: "from-emerald-500 to-teal-500 shadow-emerald-500/25",
    tab: "border-emerald-600 text-emerald-700 dark:border-emerald-400 dark:text-emerald-300",
    tabHover: "hover:text-emerald-700 dark:hover:text-emerald-300",
  },
  violet: {
    banner: "from-violet-50 dark:from-violet-950/40",
    tile: "from-violet-500 to-fuchsia-500 shadow-violet-500/25",
    tab: "border-violet-600 text-violet-700 dark:border-violet-400 dark:text-violet-300",
    tabHover: "hover:text-violet-700 dark:hover:text-violet-300",
  },
  amber: {
    banner: "from-amber-50 dark:from-amber-950/30",
    tile: "from-amber-500 to-orange-500 shadow-amber-500/25",
    tab: "border-amber-600 text-amber-700 dark:border-amber-400 dark:text-amber-300",
    tabHover: "hover:text-amber-700 dark:hover:text-amber-300",
  },
  sky: {
    banner: "from-sky-50 dark:from-sky-950/40",
    tile: "from-sky-500 to-indigo-500 shadow-sky-500/25",
    tab: "border-sky-600 text-sky-700 dark:border-sky-400 dark:text-sky-300",
    tabHover: "hover:text-sky-700 dark:hover:text-sky-300",
  },
};
