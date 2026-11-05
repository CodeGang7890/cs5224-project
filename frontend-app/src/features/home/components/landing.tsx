import type { LucideIcon } from "lucide-react";
import {
  ArrowRight,
  CalendarCheck,
  CircleCheck,
  CreditCard,
  FlaskConical,
  MessageCircleQuestion,
  MessagesSquare,
  ShoppingBag,
  Sparkles,
  Store,
  Unplug,
} from "lucide-react";

import { type PointerEvent, useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

import { usePrefersReducedMotion } from "../hooks/use-prefers-reduced-motion";

import { AuthButton } from "./auth-button";
import { ChatPreview } from "./chat-preview";
import { LandingStyles } from "./landing-styles";
import { Reveal } from "./reveal";
import { Testimonials } from "./testimonials";

interface Item {
  icon: LucideIcon;
  title: string;
  description: string;
}

const FEATURES: Item[] = [
  {
    icon: MessagesSquare,
    title: "Replies 24/7",
    description:
      "Your AI assistant answers every customer chat in seconds, even at 3 a.m.",
  },
  {
    icon: ShoppingBag,
    title: "Takes orders",
    description:
      "It knows your products, prices and stock, and collects the delivery details for you.",
  },
  {
    icon: CalendarCheck,
    title: "Books appointments",
    description:
      "Customers pick a service and a free time slot; your providers' calendars stay up to date.",
  },
  {
    icon: CreditCard,
    title: "Gets you paid",
    description:
      "Every confirmed order or booking gets a secure payment link, and payments are tracked for you.",
  },
  {
    icon: MessageCircleQuestion,
    title: "Learns from your FAQs",
    description:
      "Questions it can't answer are saved for you; answer once and it knows next time.",
  },
  {
    icon: FlaskConical,
    title: "Try before you go live",
    description:
      "Chat with your assistant as a pretend customer in the Chat Sandbox before customers do.",
  },
];

const STEPS: Item[] = [
  {
    icon: Store,
    title: "Create your free account",
    description:
      "Sign up with Google, Facebook or an email, and tell us your business's name.",
  },
  {
    icon: ShoppingBag,
    title: "Add what you sell",
    description:
      "Enter your products or services and a few FAQs. No training or code needed.",
  },
  {
    icon: Unplug,
    title: "Connect your chat",
    description:
      "Link the messaging account your customers already message, in one click. Your assistant starts replying right away.",
  },
];

const PERKS = ["Free to get started", "Set up in minutes", "No code needed"];

const ROTATING_WORDS = ["orders", "bookings", "payments", "happy customers"];

/** The hero headline's highlighted words, changing every few seconds (fixed with reduced motion). */
function RotatingWord() {
  const reducedMotion = usePrefersReducedMotion();
  const [index, setIndex] = useState(0);

  useEffect(() => {
    if (reducedMotion) return;
    const timer = setInterval(
      () => setIndex((current) => (current + 1) % ROTATING_WORDS.length),
      2600,
    );
    return () => clearInterval(timer);
  }, [reducedMotion]);

  return (
    <span
      key={index}
      className="animate-in fade-in slide-in-from-bottom-4 blur-in-sm inline-block bg-gradient-to-r from-emerald-600 to-sky-600 bg-clip-text text-transparent duration-500 dark:from-emerald-400 dark:to-sky-400"
    >
      {ROTATING_WORDS[index]}
    </span>
  );
}

/** A soft blurred colour blob drifting in the background. */
function Blob({ className }: { className: string }) {
  return (
    <div
      aria-hidden
      className={cn(
        "pointer-events-none absolute rounded-full blur-3xl motion-safe:animate-[landing-float_14s_ease-in-out_infinite]",
        className,
      )}
    />
  );
}

/** Lets the hero's background glow follow the pointer. */
function followPointer(event: PointerEvent<HTMLElement>) {
  const rect = event.currentTarget.getBoundingClientRect();
  event.currentTarget.style.setProperty(
    "--spot-x",
    `${event.clientX - rect.left}px`,
  );
  event.currentTarget.style.setProperty(
    "--spot-y",
    `${event.clientY - rect.top}px`,
  );
}

function TryForFreeButton() {
  return (
    <AuthButton
      mode="signup"
      size="lg"
      className="group shadow-lg shadow-emerald-600/25 transition-all hover:-translate-y-0.5 hover:shadow-xl hover:shadow-emerald-600/30"
    >
      Try it for free{" "}
      <ArrowRight className="transition-transform group-hover:translate-x-1" />
    </AuthButton>
  );
}

// Classes for the hero's staggered entrance.
const ENTER =
  "animate-in fade-in slide-in-from-bottom-6 fill-mode-both duration-700";

/** The Home page while logged out: what the app does, how easy it is, and sign-up buttons. */
export function Landing() {
  return (
    <div className="flex flex-col gap-24 pb-8">
      <LandingStyles />

      {/* Hero */}
      <section
        onPointerMove={followPointer}
        className="relative isolate overflow-hidden rounded-3xl border bg-gradient-to-br from-emerald-50 via-background to-sky-50 px-6 py-12 sm:px-12 sm:py-16 dark:from-emerald-950/40 dark:to-sky-950/30"
      >
        <Blob className="-top-24 -left-20 -z-10 size-72 bg-emerald-300/40 dark:bg-emerald-700/25" />
        <Blob className="-right-16 -bottom-24 -z-10 size-80 bg-sky-300/40 [animation-delay:-7s] dark:bg-sky-700/25" />
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 -z-10"
          style={{
            background:
              "radial-gradient(500px circle at var(--spot-x, 30%) var(--spot-y, 20%), rgba(16, 185, 129, 0.14), transparent 60%)",
          }}
        />

        <div className="grid items-center gap-12 lg:grid-cols-[1.1fr_1fr]">
          <div className="flex flex-col items-start gap-6">
            <Badge
              variant="outline"
              className={cn("bg-background gap-1.5 px-3 py-1", ENTER)}
            >
              <span className="relative flex size-2">
                <span className="absolute inline-flex size-full animate-ping rounded-full bg-emerald-500 opacity-75 motion-reduce:hidden" />
                <span className="relative inline-flex size-2 rounded-full bg-emerald-500" />
              </span>
              Your AI sales assistant for customer chats
            </Badge>
            <h1
              className={cn(
                "text-4xl font-bold tracking-tight text-balance sm:text-5xl lg:text-6xl",
                ENTER,
                "delay-100",
              )}
            >
              Turn customer chats into <RotatingWord />, automatically.
            </h1>
            <p
              className={cn(
                "text-muted-foreground max-w-xl text-lg text-pretty",
                ENTER,
                "delay-200",
              )}
            >
              Ansera answers your customers instantly, takes their orders, books
              their appointments and sends them a payment link, all inside the
              chat app they already use. You just watch the orders come in.
            </p>
            <div className={cn("flex flex-wrap gap-3", ENTER, "delay-300")}>
              <TryForFreeButton />
              <AuthButton
                size="lg"
                variant="outline"
                className="bg-background/70 backdrop-blur transition-all hover:-translate-y-0.5"
              >
                I already have an account
              </AuthButton>
            </div>
            <ul
              className={cn(
                "text-muted-foreground flex flex-wrap gap-x-5 gap-y-2 text-sm",
                ENTER,
                "delay-500",
              )}
            >
              {PERKS.map((perk) => (
                <li key={perk} className="flex items-center gap-1.5">
                  <CircleCheck className="size-4 text-emerald-600" /> {perk}
                </li>
              ))}
            </ul>
          </div>
          <ChatPreview
            className={cn(
              "justify-self-center lg:justify-self-end",
              "animate-in fade-in zoom-in-95 slide-in-from-right-8 fill-mode-both delay-300 duration-1000",
            )}
          />
        </div>
      </section>

      {/* Features */}
      <section className="flex flex-col gap-10">
        <Reveal className="mx-auto max-w-2xl text-center">
          <p className="text-sm font-semibold tracking-wide text-emerald-600 uppercase">
            Features
          </p>
          <h2 className="mt-2 text-3xl font-bold tracking-tight">
            Everything your chats need to sell
          </h2>
          <p className="text-muted-foreground mt-3 text-lg">
            One assistant for your whole shop, from the first "hi" to the paid
            order.
          </p>
        </Reveal>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map(({ icon: Icon, title, description }, index) => (
            <Reveal key={title} delay={(index % 3) * 120}>
              <Card className="group relative h-full gap-3 overflow-hidden transition-all duration-300 hover:-translate-y-1 hover:border-emerald-500/40 hover:shadow-lg">
                <div
                  aria-hidden
                  className="pointer-events-none absolute -top-16 -right-16 size-32 rounded-full bg-emerald-400/0 blur-2xl transition-colors duration-500 group-hover:bg-emerald-400/25"
                />
                <CardContent className="flex flex-col gap-3">
                  <div className="flex size-11 items-center justify-center rounded-xl bg-emerald-100 text-emerald-700 transition-transform duration-300 group-hover:scale-110 group-hover:-rotate-6 dark:bg-emerald-900/50 dark:text-emerald-300">
                    <Icon className="size-5" />
                  </div>
                  <h3 className="font-semibold">{title}</h3>
                  <p className="text-muted-foreground text-sm">{description}</p>
                </CardContent>
              </Card>
            </Reveal>
          ))}
        </div>
      </section>

      {/* How it works */}
      <section className="flex flex-col gap-12">
        <Reveal className="mx-auto max-w-2xl text-center">
          <p className="text-sm font-semibold tracking-wide text-emerald-600 uppercase">
            How it works
          </p>
          <h2 className="mt-2 text-3xl font-bold tracking-tight">
            Up and running in 3 easy steps
          </h2>
          <p className="text-muted-foreground mt-3 text-lg">
            No developers, no complicated setup. If you can fill in a form, you
            can do this.
          </p>
        </Reveal>
        <div className="relative">
          <div
            aria-hidden
            className="absolute top-0 right-[16%] left-[16%] hidden h-0.5 bg-gradient-to-r from-emerald-500/0 via-emerald-500/50 to-emerald-500/0 md:block"
          />
          <ol className="grid gap-10 md:grid-cols-3 md:gap-6">
            {STEPS.map(({ icon: Icon, title, description }, index) => (
              <Reveal
                as="li"
                key={title}
                delay={index * 200}
                className="h-full"
              >
                <div className="group bg-card relative flex h-full flex-col items-center gap-3 rounded-2xl border p-6 pt-10 text-center transition-all duration-300 hover:-translate-y-1 hover:shadow-lg">
                  <span className="absolute -top-5 left-1/2 flex size-10 -translate-x-1/2 items-center justify-center rounded-full bg-emerald-600 text-base font-bold text-white shadow-lg ring-4 shadow-emerald-600/30 ring-background transition-transform duration-300 group-hover:scale-110">
                    {index + 1}
                  </span>
                  <Icon className="size-7 text-emerald-600 transition-transform duration-300 group-hover:-translate-y-0.5" />
                  <h3 className="font-semibold">{title}</h3>
                  <p className="text-muted-foreground text-sm">{description}</p>
                </div>
              </Reveal>
            ))}
          </ol>
        </div>
      </section>

      <Testimonials />

      {/* Final call to action */}
      <Reveal>
        <section className="relative isolate flex flex-col items-center gap-5 overflow-hidden rounded-3xl bg-[linear-gradient(120deg,#047857,#059669,#0f766e,#0369a1,#047857)] bg-[length:300%_300%] px-6 py-14 text-center text-white motion-safe:animate-[landing-gradient_14s_ease_infinite]">
          <Blob className="-top-20 -left-10 -z-10 size-64 bg-white/15" />
          <Blob className="-right-10 -bottom-24 -z-10 size-72 bg-sky-300/20 [animation-delay:-5s]" />
          <Sparkles className="size-8 text-white/80 motion-safe:animate-pulse" />
          <h2 className="text-3xl font-bold tracking-tight text-balance sm:text-4xl">
            Ready to let your chats sell for you?
          </h2>
          <p className="max-w-xl text-lg text-white/85">
            Create your free account and see your assistant answer its first
            customer today.
          </p>
          <div className="flex flex-wrap justify-center gap-3">
            <AuthButton
              mode="signup"
              size="lg"
              variant="secondary"
              className="group shadow-lg transition-all hover:-translate-y-0.5 hover:shadow-xl"
            >
              Create my free account{" "}
              <ArrowRight className="transition-transform group-hover:translate-x-1" />
            </AuthButton>
            <AuthButton
              size="lg"
              variant="ghost"
              className="text-white hover:bg-white/10 hover:text-white"
            >
              Log in
            </AuthButton>
          </div>
        </section>
      </Reveal>
    </div>
  );
}
