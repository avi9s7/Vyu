import { z } from "zod";

export const NewSearchSchema = z.object({
  question: z.string().min(10).max(2000),
  sources: z
    .array(
      z.enum([
        "pubmed",
        "semantic_scholar",
        "clinicaltrials",
        "guidelines",
        "internal_library"
      ])
    )
    .min(1),
  dateRange: z.object({
    from: z.string(),
    to: z.string()
  }),
  evidenceTypes: z.array(z.string()),
  specialtyTopics: z.array(z.string()).optional(),
  population: z.string().optional(),
  intervention: z.string().optional(),
  comparator: z.string().optional(),
  onlyApprovedSources: z.boolean()
});

export type NewSearchInput = z.infer<typeof NewSearchSchema>;
