import { cn } from "@/lib/utils/cn";

export function Input({
  className,
  ...props
}: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cn(
        "h-10 w-full rounded-md border border-border bg-white px-3 text-sm text-slate-950 shadow-sm placeholder:text-slate-400",
        className
      )}
      {...props}
    />
  );
}
