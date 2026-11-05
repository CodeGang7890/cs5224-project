import type { LucideIcon } from "lucide-react";
import {
  CalendarCheck,
  CheckCheck,
  MessageCircleQuestion,
  ShoppingBag,
  Sparkles,
} from "lucide-react";
import { useEffect, useState } from "react";

import { cn } from "@/lib/utils";

import { usePrefersReducedMotion } from "../hooks/use-prefers-reduced-motion";

interface PreviewMessage {
  from: "customer" | "assistant";
  text: string;
  time: string;
}

interface Scenario {
  label: string;
  icon: LucideIcon;
  business: string;
  avatarClass: string;
  messages: PreviewMessage[];
}

// Made-up conversations showing what the assistant does: takes orders, books appointments, answers questions.
const SCENARIOS: Scenario[] = [
  {
    label: "Orders",
    icon: ShoppingBag,
    business: "Kopi Corner",
    avatarClass: "bg-amber-500",
    messages: [
      {
        from: "customer",
        text: "Hi! Do you still have the House Blend coffee beans?",
        time: "9:41",
      },
      {
        from: "assistant",
        text: "Yes, we do! House Blend 250 g is $18. How many bags would you like?",
        time: "9:41",
      },
      {
        from: "customer",
        text: "2 please, delivered to Clementi",
        time: "9:42",
      },
      {
        from: "assistant",
        text: "Done! 2 × House Blend = $36. Here's your secure payment link: pay.xendit.co/…",
        time: "9:42",
      },
    ],
  },
  {
    label: "Bookings",
    icon: CalendarCheck,
    business: "Glow Hair Studio",
    avatarClass: "bg-pink-500",
    messages: [
      {
        from: "customer",
        text: "Can I book a haircut this Saturday?",
        time: "18:05",
      },
      {
        from: "assistant",
        text: "Of course! A haircut (45 min) is $35. On Saturday I have 10:00, 11:30 or 14:00. Which suits you?",
        time: "18:05",
      },
      { from: "customer", text: "11:30 please!", time: "18:06" },
      {
        from: "assistant",
        text: "You're booked for Saturday 11:30 with Mei ✂️ Pay here to confirm: pay.xendit.co/…",
        time: "18:06",
      },
    ],
  },
  {
    label: "Questions",
    icon: MessageCircleQuestion,
    business: "Kopi Corner",
    avatarClass: "bg-amber-500",
    messages: [
      { from: "customer", text: "Do you deliver on Sundays?", time: "23:12" },
      {
        from: "assistant",
        text: "We do! Sunday deliveries run 10 am to 4 pm, and they're free over $30.",
        time: "23:12",
      },
      {
        from: "customer",
        text: "Nice. Is the oat milk latte vegan?",
        time: "23:13",
      },
      {
        from: "assistant",
        text: "Yes, it's 100% plant-based 🌱 Would you like to order one?",
        time: "23:13",
      },
    ],
  },
];

const CUSTOMER_DELAY_MS = 900;
const TYPING_MS = 1400;
const REPLAY_AFTER_MS = 4500;

/**
 * A chat mock-up for the landing page's hero (static: nothing is sent). The conversation plays message by
 * message, with a typing indicator before each reply, then moves on to the next example; the tabs pick one.
 */
export function ChatPreview({ className }: { className?: string }) {
  const reducedMotion = usePrefersReducedMotion();
  const [scenarioIndex, setScenarioIndex] = useState(0);
  const [shown, setShown] = useState(0);
  const [typing, setTyping] = useState(false);
  // Moves through the examples by itself until the visitor picks one.
  const [autoAdvance, setAutoAdvance] = useState(true);

  const scenario = SCENARIOS[scenarioIndex];
  const total = scenario.messages.length;

  useEffect(() => {
    if (reducedMotion) return;
    let timer: ReturnType<typeof setTimeout>;
    if (shown >= total) {
      timer = setTimeout(() => {
        if (autoAdvance) {
          setScenarioIndex((index) => (index + 1) % SCENARIOS.length);
        }
        setShown(0);
      }, REPLAY_AFTER_MS);
    } else if (scenario.messages[shown].from === "assistant") {
      timer = setTimeout(() => setTyping(true), 300);
      const reply = setTimeout(() => {
        setTyping(false);
        setShown(shown + 1);
      }, 300 + TYPING_MS);
      return () => {
        clearTimeout(timer);
        clearTimeout(reply);
      };
    } else {
      timer = setTimeout(() => setShown(shown + 1), CUSTOMER_DELAY_MS);
    }
    return () => clearTimeout(timer);
  }, [reducedMotion, shown, total, scenario, autoAdvance]);

  const pick = (index: number) => {
    setAutoAdvance(false);
    setScenarioIndex(index);
    setShown(0);
    setTyping(false);
  };

  const visible = reducedMotion
    ? scenario.messages
    : scenario.messages.slice(0, shown);

  return (
    <div className={cn("flex w-full max-w-sm flex-col gap-3", className)}>
      <div
        role="tablist"
        aria-label="Example conversations"
        className="bg-background/80 flex gap-1 self-center rounded-full border p-1 shadow-sm backdrop-blur"
      >
        {SCENARIOS.map(({ label, icon: Icon }, index) => (
          <button
            key={label}
            type="button"
            role="tab"
            aria-selected={index === scenarioIndex}
            onClick={() => pick(index)}
            className={cn(
              "flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium transition-colors",
              index === scenarioIndex
                ? "bg-emerald-600 text-white shadow"
                : "text-muted-foreground hover:text-foreground hover:bg-muted",
            )}
          >
            <Icon className="size-3.5" /> {label}
          </button>
        ))}
      </div>

      <div
        aria-hidden
        className="bg-card overflow-hidden rounded-3xl border shadow-2xl shadow-emerald-900/10 transition-transform duration-500 hover:-rotate-1 hover:scale-[1.02] motion-reduce:transform-none"
      >
        <div className="flex items-center gap-3 bg-emerald-700 px-4 py-3 text-white">
          <div
            className={cn(
              "flex size-9 items-center justify-center rounded-full font-semibold transition-colors",
              scenario.avatarClass,
            )}
          >
            {scenario.business[0]}
          </div>
          <div className="leading-tight">
            <p className="text-sm font-semibold">{scenario.business}</p>
            <p className="text-xs text-white/80">
              {typing ? "typing…" : "online · replies instantly"}
            </p>
          </div>
        </div>

        <div
          key={scenarioIndex}
          className="flex h-[22rem] flex-col justify-end gap-2 overflow-hidden bg-emerald-50/60 p-4 dark:bg-emerald-950/30"
        >
          {visible.map((message, index) => (
            <div
              key={index}
              className={cn(
                "animate-in fade-in slide-in-from-bottom-3 zoom-in-95 max-w-[85%] rounded-2xl px-3 py-2 text-sm shadow-sm duration-300",
                message.from === "customer"
                  ? "origin-bottom-right self-end rounded-br-sm bg-emerald-200 text-emerald-950 dark:bg-emerald-800 dark:text-emerald-50"
                  : "bg-background origin-bottom-left self-start rounded-bl-sm",
              )}
            >
              {message.from === "assistant" && (
                <p className="mb-0.5 flex items-center gap-1 text-xs font-medium text-emerald-700 dark:text-emerald-400">
                  <Sparkles className="size-3" /> AI assistant
                </p>
              )}
              <p>{message.text}</p>
              <p className="text-muted-foreground mt-0.5 flex items-center justify-end gap-1 text-[10px]">
                {message.time}
                {message.from === "customer" && (
                  <CheckCheck className="size-3 text-sky-500" />
                )}
              </p>
            </div>
          ))}
          {typing && (
            <div className="bg-background animate-in fade-in zoom-in-90 flex gap-1 self-start rounded-2xl rounded-bl-sm px-4 py-3 shadow-sm">
              {[0, 150, 300].map((delay) => (
                <span
                  key={delay}
                  className="size-2 animate-bounce rounded-full bg-emerald-600/70"
                  style={{ animationDelay: `${delay}ms` }}
                />
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="flex justify-center gap-1.5" aria-hidden>
        {SCENARIOS.map(({ label }, index) => (
          <span
            key={label}
            className={cn(
              "h-1.5 rounded-full transition-all duration-500",
              index === scenarioIndex
                ? "w-6 bg-emerald-600"
                : "bg-muted-foreground/30 w-1.5",
            )}
          />
        ))}
      </div>
    </div>
  );
}
