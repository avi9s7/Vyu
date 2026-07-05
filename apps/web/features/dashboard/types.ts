export type ActivityItem = {
  id: string;
  label: string;
  actor: string;
  createdAt: string;
  status: "completed" | "pending" | "needs_review";
};

export type EvidenceRecommendation = {
  id: string;
  title: string;
  sourceType: "Guideline" | "RCT" | "SystematicReview" | "InternalDocument";
  quality: "low" | "moderate" | "high";
  updatedAt: string;
};

export type ReviewQueueItem = {
  id: string;
  title: string;
  priority: "low" | "medium" | "high";
  dueDate: string;
};

export type DashboardSummary = {
  kpis: {
    activeResearchProjects: number;
    evidenceReportsCreated: number;
    pendingReviews: number;
    governanceAlerts: number;
  };
  recentActivity: ActivityItem[];
  recommendedEvidence: EvidenceRecommendation[];
  reviewQueuePreview: ReviewQueueItem[];
};
