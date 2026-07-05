import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";

export function PlaceholderSurface({
  title,
  description,
  items
}: {
  title: string;
  description: string;
  items: string[];
}) {
  return (
    <>
      <PageHeader title={title} description={description} />
      <Card title="Production surface contract">
        <div className="grid gap-3 md:grid-cols-2">
          {items.map((item) => (
            <div
              key={item}
              className="flex items-center justify-between gap-4 rounded-md border border-border px-4 py-3"
            >
              <span className="text-sm font-medium">{item}</span>
              <Badge tone="info">planned</Badge>
            </div>
          ))}
        </div>
      </Card>
    </>
  );
}
