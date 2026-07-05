import { cn } from "@/lib/utils/cn";

type Variant = "primary" | "secondary" | "ghost" | "danger";

const variantClassName: Record<Variant, string> = {
  primary: "bg-primary text-white hover:bg-[var(--color-primary-dark)]",
  secondary: "border border-border bg-white text-slate-900 hover:bg-slate-50",
  ghost: "text-slate-700 hover:bg-slate-100",
  danger: "bg-red-600 text-white hover:bg-red-700"
};

export function Button({
  children,
  className,
  variant = "secondary",
  type = "button",
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant;
}) {
  return (
    <button
      type={type}
      className={cn(
        "inline-flex h-10 items-center justify-center gap-2 rounded-md px-4 text-sm font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-60",
        variantClassName[variant],
        className
      )}
      {...props}
    >
      {children}
    </button>
  );
}
