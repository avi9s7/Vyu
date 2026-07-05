import { PlaceholderSurface } from "@/components/domain/PlaceholderSurface";

export default function SearchResultsPage({
  params
}: {
  params: { searchId: string };
}) {
  return (
    <PlaceholderSurface
      title="Search Results"
      description={`Governed answer, citations, and evidence state for search ${params.searchId}.`}
      items={[
        "Research question summary",
        "Search scope",
        "Governed answer card",
        "Confidence indicator",
        "Top Evidence list",
        "Governance Box",
        "Create report action"
      ]}
    />
  );
}
