import { AlertTriangle, ClipboardCheck, FileText, FolderKanban } from "lucide-react";
import { Card } from "@/components/ui/Card";
import type { DashboardSummary } from "@/features/dashboard/types";

const kpiItems = [
  {
    key: "activeResearchProjects",
    label: "Active Research Projects",
    icon: FolderKanban
  },
  {
    key: "evidenceReportsCreated",
    label: "Evidence Reports Created",
    icon: FileText
  },
  {
    key: "pendingReviews",
    label: "Pending Reviews",
    icon: ClipboardCheck
  },
  {
    key: "governanceAlerts",
    label: "Governance Alerts",
    icon: AlertTriangle
  }
] as const;

export function DashboardKpiGrid({ kpis }: { kpis: DashboardSummary["kpis"] }) {
  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      {kpiItems.map((item) => {
        const Icon = item.icon;
        return (
          <Card key={item.key}>
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="text-sm font-medium text-slate-500">{item.label}</p>
                <p className="mt-3 text-3xl font-bold">{kpis[item.key]}</p>
              </div>
              <div className="flex h-10 w-10 items-center justify-center rounded-md bg-slate-100 text-slate-700">
                <Icon aria-hidden="true" size={20} />
              </div>
            </div>
          </Card>
        );
      })}
    </div>
  );
}
