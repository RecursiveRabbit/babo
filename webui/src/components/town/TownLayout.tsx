import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

/** One area of the Town page: a clear panel with its title and what it's for at the top, then its content.
 *  Every Town tab is made of these, so each part reads as a labelled whole. */
export function TownSection({ title, badges, description, actions, children, className, tone = "plain" }: {
  title: string;
  /** Small labels beside the title (a round's file name, "off"). */
  badges?: ReactNode;
  description?: ReactNode;
  /** Buttons for the whole area, beside its title. */
  actions?: ReactNode;
  children?: ReactNode;
  className?: string;
  /** "attention": something here needs the owner. */
  tone?: "plain" | "attention";
}) {
  return <section aria-label={title}
    className={cn("town-section mt-3 overflow-hidden rounded-panel border bg-settings-surface animate-in fade-in-0 slide-in-from-bottom-1 duration-300 motion-reduce:animate-none",
      tone === "attention" ? "border-primary/50 ring-1 ring-primary/20" : "border-border/70", className)}>
    <header className="flex flex-wrap items-start gap-x-3 gap-y-2 border-b border-border/60 px-4 py-3">
      <div className="min-w-0 flex-1">
        <h2 className="flex flex-wrap items-center gap-2 text-[14px] font-semibold leading-5 text-foreground">{title}{badges}</h2>
        {description && <p className="mt-0.5 text-xs leading-5 text-muted-foreground">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </header>
    {children}
  </section>;
}

export interface TownNavItem<T extends string> { value: T; label: string; badge?: number }
export interface TownNavGroup<T extends string> { label: string; items: TownNavItem<T>[] }

/** The Town page's areas, grouped and labelled: a column beside the page on wide screens, a row of chips on narrow ones. */
export function TownNav<T extends string>({ groups, value, onChange, ariaLabel }: {
  groups: TownNavGroup<T>[];
  value: T;
  onChange: (value: T) => void;
  ariaLabel: string;
}) {
  return <nav aria-label={ariaLabel} className="town-nav min-w-0">
    <div role="tablist" aria-label={ariaLabel} aria-orientation="vertical"
      className="flex gap-4 overflow-x-auto pb-1 lg:flex-col lg:gap-5 lg:overflow-visible lg:pb-0">
      {groups.map((group) => <div key={group.label} role="presentation" className="flex shrink-0 flex-col gap-1">
        <span className="px-2 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">{group.label}</span>
        <div role="presentation" className="flex gap-1 lg:flex-col">
          {group.items.map((item) => {
            const selected = item.value === value;
            return <button key={item.value} type="button" role="tab" aria-selected={selected} tabIndex={selected ? 0 : -1}
              aria-label={item.badge ? `${item.label} (${item.badge})` : undefined}
              onClick={() => onChange(item.value)}
              className={cn("flex items-center justify-between gap-2 whitespace-nowrap rounded-md px-2.5 py-1.5 text-left text-[13px] transition-colors",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                selected ? "bg-primary text-primary-foreground font-medium shadow-sm" : "text-foreground hover:bg-muted/70")}>
              <span>{item.label}</span>
              {item.badge ? <span className={cn("rounded-full px-1.5 text-[11px] font-semibold tabular-nums",
                selected ? "bg-primary-foreground/20" : "bg-primary/15 text-primary")}>{item.badge}</span> : null}
            </button>;
          })}
        </div>
      </div>)}
    </div>
  </nav>;
}

/** What needs the owner, at the top of the Town page: each a button that goes there. Nothing shows when nothing does. */
export function AttentionStrip({ items, label }: { label: string; items: { key: string; text: string; onClick: () => void }[] }) {
  if (!items.length) return null;
  return <div role="region" aria-label={label}
    className="flex flex-wrap items-center gap-2 rounded-panel border border-primary/40 bg-primary/5 px-3 py-2 animate-in fade-in-0 duration-300 motion-reduce:animate-none">
    <span className="text-xs font-semibold uppercase tracking-wider text-primary">{label}</span>
    {items.map((item) => <button key={item.key} type="button" onClick={item.onClick}
      className="rounded-full border border-primary/40 bg-background px-3 py-1 text-[13px] font-medium text-foreground transition-colors hover:bg-primary hover:text-primary-foreground">
      {item.text}
    </button>)}
  </div>;
}

/** What a Town tab is for, in a few lines: a quiet panel at its top (and the terminal command that does the same). */
export function TownIntro({ children }: { children: ReactNode }) {
  return <p className="rounded-panel border border-dashed border-border/80 bg-muted/30 px-4 py-2.5 text-[13px] leading-6 text-muted-foreground">
    {children}
  </p>;
}
