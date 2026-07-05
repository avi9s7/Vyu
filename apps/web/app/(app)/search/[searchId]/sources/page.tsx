import { PlaceholderSurface } from "@/components/domain/PlaceholderSurface";

export default function SourcesPage({ params }: { params: { searchId: string } }) {
  return (
    <PlaceholderSurface
      title="Sources / Evidence Details"
      description={`Evidence inspection surface for search ${params.searchId}.`}
      items={[
        "Source list",
        "Type and quality filters",
        "Selected source detail panel",
        "Overview / Methodology / Key Findings tabs",
        "Extracts and Full Text tabs",
        "Source Quality Assessment",
        "Cited-in-answer toggle"
      ]}
    />
  );
}
