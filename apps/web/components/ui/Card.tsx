import { cn } from "@/lib/utils/cn";

type CardProps = {
  title?: string;
  action?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
};

export function Card({ title, action, children, className }: CardProps) {
  return (
    <section
      className={cn(
        "rounded-card border border-border bg-surface shadow-sm",
        className
      )}
    >
      {(title || action) && (
        <header className="flex items-center justify-between gap-4 border-b border-border px-6 py-4">
          {title ? <h2 className="text-base font-semibold">{title}</h2> : <span />}
          {action}
        </header>
      )}
      <div className="p-6">{children}</div>
    </section>
  );
}
