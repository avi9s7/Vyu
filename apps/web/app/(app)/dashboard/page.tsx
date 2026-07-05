import { FilePlus, Search } from "lucide-react";
import Link from "next/link";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { getDashboardSummary } from "@/features/dashboard/api";
import { DashboardKpiGrid } from "@/features/dashboard/components/DashboardKpiGrid";
import {
  RecentActivityList,
  RecommendedEvidenceTable,
  ReviewQueuePreview
} from "@/features/dashboard/components/DashboardLists";

export default async function DashboardPage() {
  const summary = await getDashboardSummary();

  return (
    <>
      <PageHeader
        title="Home Dashboard"
        description="Compact operational overview for governed evidence search, review, and export readiness."
        action={
          <Link href="/search/new" prefetch={false}>
            <Button variant="primary">
              <Search aria-hidden="true" size={16} />
              New Search
            </Button>
          </Link>
        }
      />
      <div className="page-grid">
        <DashboardKpiGrid kpis={summary.kpis} />
        <div className="grid gap-6 xl:grid-cols-[1fr_360px]">
          <div className="page-grid">
            <RecentActivityList items={summary.recentActivity} />
            <RecommendedEvidenceTable items={summary.recommendedEvidence} />
          </div>
          <div className="page-grid content-start">
            <Card title="Quick Actions">
              <div className="grid gap-3">
                <Link href="/search/new" prefetch={false}>
                  <Button className="w-full justify-start" variant="secondary">
                    <Search aria-hidden="true" size={16} />
                    Start governed evidence search
                  </Button>
                </Link>
                <Link href="/reports/generate" prefetch={false}>
                  <Button className="w-full justify-start" variant="secondary">
                    <FilePlus aria-hidden="true" size={16} />
                    Generate report
                  </Button>
                </Link>
              </div>
            </Card>
            <ReviewQueuePreview items={summary.reviewQueuePreview} />
          </div>
        </div>
      </div>
    </>
  );
}
