import { PlaceholderSurface } from "@/components/domain/PlaceholderSurface";

export default function ReportGenerationPage() {
  return (
    <PlaceholderSurface
      title="Report Generation"
      description="Convert governed evidence results into an exportable professional report."
      items={[
        "Report content checklist",
        "Report title",
        "Audience",
        "Tone",
        "Detail level",
        "Appendices toggle",
        "Export format options",
        "Live report preview",
        "Generate report button"
      ]}
    />
  );
}
