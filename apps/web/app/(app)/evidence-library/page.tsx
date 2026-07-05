import { PlaceholderSurface } from "@/components/domain/PlaceholderSurface";

export default function EvidenceLibraryPage() {
  return (
    <PlaceholderSurface
      title="Evidence Library"
      description="Manage uploaded, curated, bookmarked, and dataset evidence documents."
      items={[
        "All Documents tab",
        "My Uploads tab",
        "Datasets tab",
        "Curated Sources tab",
        "Bookmarks tab",
        "Document table",
        "Upload panel",
        "Library Summary",
        "Filters and pagination"
      ]}
    />
  );
}
