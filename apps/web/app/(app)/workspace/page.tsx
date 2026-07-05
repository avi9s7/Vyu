import { PlaceholderSurface } from "@/components/domain/PlaceholderSurface";

export default function WorkspacePage() {
  return (
    <PlaceholderSurface
      title="My Workspace"
      description="Workspace navigation for saved searches, evidence projects, reports, and bookmarks."
      items={[
        "Saved research projects",
        "Recent searches",
        "Draft reports",
        "Bookmarked evidence",
        "Assigned reviews",
        "Workspace audit summary"
      ]}
    />
  );
}
