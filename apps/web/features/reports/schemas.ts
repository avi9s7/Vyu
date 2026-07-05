import { z } from "zod";

export const ReportGenerationSchema = z.object({
  searchId: z.string(),
  title: z.string().min(5),
  audience: z.enum(["clinical_research_team", "policy_team", "executive", "reviewer"]),
  tone: z.enum(["professional", "technical", "executive"]),
  detailLevel: z.enum(["brief", "standard", "comprehensive"]),
  include: z.object({
    querySummary: z.boolean(),
    executiveSummary: z.boolean(),
    keyFindings: z.boolean(),
    detailedAnalysis: z.boolean(),
    sourcesEvidence: z.boolean(),
    governanceTransparency: z.boolean(),
    appendices: z.boolean()
  }),
  format: z.enum(["pdf", "docx", "pptx", "xlsx", "html"])
});

export type ReportGenerationInput = z.infer<typeof ReportGenerationSchema>;
