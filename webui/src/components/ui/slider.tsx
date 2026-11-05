import { cn } from "@/lib/utils";

/** A range, as a slider with its value beside it (in the accent colour). */
export function Slider({ value, min, max, step = 1, onChange, ariaLabel, disabled, unit = "", className }: {
  value: number;
  min: number;
  max: number;
  step?: number;
  onChange: (value: number) => void;
  ariaLabel: string;
  disabled?: boolean;
  /** Shown after the value ("min", "tokens"). */
  unit?: string;
  className?: string;
}) {
  const high = Math.max(max, value);
  const low = Math.min(min, value);
  return <span className={cn("flex min-w-[12rem] items-center gap-3", className)}>
    <input type="range" min={low} max={high} step={step} value={value} disabled={disabled} aria-label={ariaLabel}
      onChange={(event) => onChange(Number(event.target.value))}
      className="h-1.5 w-full cursor-pointer appearance-auto accent-[hsl(var(--primary))] disabled:cursor-default disabled:opacity-60" />
    <span className="w-16 shrink-0 text-right text-[13px] font-medium tabular-nums">{value}{unit ? <span className="ml-0.5 text-xs font-normal text-muted-foreground">{unit}</span> : null}</span>
  </span>;
}
