import { Quote, Star } from "lucide-react";

import { cn } from "@/lib/utils";

import { Reveal } from "./reveal";

interface Testimonial {
  quote: string;
  name: string;
  business: string;
  avatarClass: string;
}

// Sample reviews for the landing page (made-up people and businesses).
const TESTIMONIALS: Testimonial[] = [
  {
    quote:
      "I used to reply to orders until midnight. Now the assistant takes them while I sleep, and I wake up to paid orders.",
    name: "Sarah Lim",
    business: "Kopi Corner · café",
    avatarClass: "bg-amber-500",
  },
  {
    quote:
      "Customers book their own slots and pay upfront. No-shows dropped a lot, and I stopped juggling appointments in my notes app.",
    name: "Mei Tan",
    business: "Glow Hair Studio · salon",
    avatarClass: "bg-pink-500",
  },
  {
    quote:
      "Setting it up took one afternoon. I added my products, tried it in the sandbox, and it just worked.",
    name: "Daniel Wong",
    business: "Rally Sports · equipment",
    avatarClass: "bg-sky-500",
  },
  {
    quote:
      "It answers the same delivery questions I used to type 30 times a day, politely and in seconds.",
    name: "Priya Nair",
    business: "Bloom Florist · flowers",
    avatarClass: "bg-rose-500",
  },
  {
    quote:
      "The questions it can't answer show up in one list. I answer once, and it knows for next time. Brilliant.",
    name: "Hafiz Rahman",
    business: "Lumen Photography · studio",
    avatarClass: "bg-violet-500",
  },
  {
    quote:
      "Feels like hiring a sales assistant who never takes a day off, for a fraction of the cost.",
    name: "Grace Chua",
    business: "Little Bakes · home bakery",
    avatarClass: "bg-emerald-500",
  },
];

function initials(name: string) {
  return name
    .split(" ")
    .map((part) => part[0])
    .join("");
}

function TestimonialCard({ testimonial }: { testimonial: Testimonial }) {
  return (
    <figure className="bg-card relative flex w-80 shrink-0 flex-col gap-4 rounded-2xl border p-6 shadow-sm transition-all duration-300 hover:-translate-y-1 hover:shadow-lg">
      <Quote className="absolute top-5 right-5 size-8 text-emerald-600/15" />
      <div className="flex gap-0.5" aria-label="5 out of 5 stars">
        {Array.from({ length: 5 }, (_, index) => (
          <Star key={index} className="size-4 fill-amber-400 text-amber-400" />
        ))}
      </div>
      <blockquote className="flex-1 text-sm leading-relaxed">
        "{testimonial.quote}"
      </blockquote>
      <figcaption className="flex items-center gap-3">
        <span
          className={cn(
            "flex size-10 items-center justify-center rounded-full text-sm font-semibold text-white",
            testimonial.avatarClass,
          )}
        >
          {initials(testimonial.name)}
        </span>
        <span className="leading-tight">
          <span className="block text-sm font-semibold">
            {testimonial.name}
          </span>
          <span className="text-muted-foreground text-xs">
            {testimonial.business}
          </span>
        </span>
      </figcaption>
    </figure>
  );
}

/**
 * "Loved by small businesses": the reviews scroll by on their own (paused while hovered); with reduced
 * motion they're a row you can scroll.
 */
export function Testimonials() {
  return (
    <section className="flex flex-col gap-8">
      <Reveal className="mx-auto max-w-2xl text-center">
        <p className="text-sm font-semibold tracking-wide text-emerald-600 uppercase">
          Testimonials
        </p>
        <h2 className="mt-2 text-3xl font-bold tracking-tight">
          Loved by small businesses
        </h2>
        <p className="text-muted-foreground mt-3 text-lg">
          Shop owners who let their assistant handle the chats, and got their
          evenings back.
        </p>
      </Reveal>
      <Reveal delay={150}>
        <div className="group relative overflow-hidden [mask-image:linear-gradient(to_right,transparent,black_8%,black_92%,transparent)] motion-reduce:overflow-x-auto">
          <div className="flex w-max gap-4 py-2 animate-[landing-marquee_45s_linear_infinite] group-hover:[animation-play-state:paused] motion-reduce:animate-none">
            {[...TESTIMONIALS, ...TESTIMONIALS].map((testimonial, index) => (
              <div
                key={index}
                aria-hidden={index >= TESTIMONIALS.length}
                className={cn(
                  index >= TESTIMONIALS.length && "motion-reduce:hidden",
                )}
              >
                <TestimonialCard testimonial={testimonial} />
              </div>
            ))}
          </div>
        </div>
      </Reveal>
    </section>
  );
}
