import { type ReactNode, useEffect, useRef, useState } from "react";

import { cn } from "@/lib/utils";

/**
 * Fades and slides its content up the first time it scrolls into view. `delay` (ms) staggers items in a
 * row. With reduced motion, the content just shows.
 */
export function Reveal({
  as: Tag = "div",
  children,
  delay = 0,
  className,
}: {
  /** The element to render (`li` inside a list). */
  as?: "div" | "li";
  children: ReactNode;
  delay?: number;
  className?: string;
}) {
  const ref = useRef<HTMLDivElement & HTMLLIElement>(null);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setVisible(true);
          observer.disconnect();
        }
      },
      { threshold: 0.15, rootMargin: "0px 0px -40px 0px" },
    );
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  return (
    <Tag
      ref={ref}
      style={{ transitionDelay: `${delay}ms` }}
      className={cn(
        "transition-[opacity,translate] duration-700 ease-out motion-reduce:translate-y-0 motion-reduce:opacity-100 motion-reduce:transition-none",
        visible ? "translate-y-0 opacity-100" : "translate-y-8 opacity-0",
        className,
      )}
    >
      {children}
    </Tag>
  );
}
