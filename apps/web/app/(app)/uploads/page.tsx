import { PlaceholderSurface } from "@/components/domain/PlaceholderSurface";

export default function UploadsPage() {
  return (
    <PlaceholderSurface
      title="Uploads"
      description="Pre-signed upload workflow surface for approved evidence documents."
      items={[
        "File selection",
        "Upload metadata",
        "Pre-signed S3 URL request",
        "Direct browser-to-S3 upload",
        "Ingestion record creation",
        "Processing status"
      ]}
    />
  );
}
