import dashboardFixture from "@/tests/mocks/fixtures/dashboard.json";
import { apiFetch } from "@/lib/api/client";
import type { DashboardSummary } from "@/features/dashboard/types";

export async function getDashboardSummary(): Promise<DashboardSummary> {
  if (process.env.NEXT_PUBLIC_USE_FIXTURES !== "false") {
    return dashboardFixture as DashboardSummary;
  }

  return apiFetch<DashboardSummary>("/v1/dashboard/summary");
}
