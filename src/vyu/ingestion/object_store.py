from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol
from uuid import UUID

from src.vyu.ingestion.validation import sanitize_filename


@dataclass(frozen=True)
class QuarantineObjectRef:
    bucket: str
    key: str
    tenant_id: UUID
    workspace_id: UUID
    document_id: UUID
    version_id: UUID
    filename: str
    media_type: str
    size_bytes: int
    sha256: str


@dataclass(frozen=True)
class PresignedPost:
    url: str
    fields: dict[str, str]
    conditions: list[object]
    expires_at: datetime
    object_ref: QuarantineObjectRef


class QuarantineObjectStore(Protocol):
    def create_presigned_upload(self, ref: QuarantineObjectRef) -> PresignedPost: ...


def build_quarantine_key(
    *,
    env: str,
    tenant_id: UUID,
    workspace_id: UUID,
    document_id: UUID,
    version_id: UUID,
    filename: str,
) -> str:
    safe_name = sanitize_filename(filename)
    return (
        f"{env}/{tenant_id}/{workspace_id}/quarantine/"
        f"{document_id}/{version_id}/{safe_name}"
    )


@dataclass
class RecordingQuarantineObjectStore:
    bucket: str
    region: str
    kms_key_id: str
    expiry_seconds: int
    upload_url: str = "https://s3.local/quarantine"
    posts: list[PresignedPost] = field(default_factory=list)

    def create_presigned_upload(self, ref: QuarantineObjectRef) -> PresignedPost:
        conditions: list[object] = [
            {"bucket": self.bucket},
            ["eq", "$key", ref.key],
            ["content-length-range", ref.size_bytes, ref.size_bytes],
            {"Content-Type": ref.media_type},
            {"x-amz-server-side-encryption": "aws:kms"},
            {"x-amz-server-side-encryption-aws-kms-key-id": self.kms_key_id},
            {"x-amz-meta-tenant-id": str(ref.tenant_id)},
            {"x-amz-meta-workspace-id": str(ref.workspace_id)},
            {"x-amz-meta-document-id": str(ref.document_id)},
            {"x-amz-meta-version-id": str(ref.version_id)},
            {"x-amz-meta-sha256": ref.sha256},
            {"acl": "private"},
        ]
        fields = {
            "key": ref.key,
            "Content-Type": ref.media_type,
            "x-amz-server-side-encryption": "aws:kms",
            "x-amz-server-side-encryption-aws-kms-key-id": self.kms_key_id,
            "x-amz-meta-tenant-id": str(ref.tenant_id),
            "x-amz-meta-workspace-id": str(ref.workspace_id),
            "x-amz-meta-document-id": str(ref.document_id),
            "x-amz-meta-version-id": str(ref.version_id),
            "x-amz-meta-sha256": ref.sha256,
            "acl": "private",
        }
        from datetime import UTC, timedelta

        post = PresignedPost(
            url=self.upload_url,
            fields=fields,
            conditions=conditions,
            expires_at=datetime.now(tz=UTC) + timedelta(seconds=self.expiry_seconds),
            object_ref=ref,
        )
        self.posts.append(post)
        return post


@dataclass
class BotoQuarantineObjectStore:
    bucket: str
    region: str
    kms_key_id: str
    expiry_seconds: int

    def create_presigned_upload(self, ref: QuarantineObjectRef) -> PresignedPost:
        import boto3

        client = boto3.client("s3", region_name=self.region)
        fields = {
            "Content-Type": ref.media_type,
            "x-amz-server-side-encryption": "aws:kms",
            "x-amz-server-side-encryption-aws-kms-key-id": self.kms_key_id,
            "x-amz-meta-tenant-id": str(ref.tenant_id),
            "x-amz-meta-workspace-id": str(ref.workspace_id),
            "x-amz-meta-document-id": str(ref.document_id),
            "x-amz-meta-version-id": str(ref.version_id),
            "x-amz-meta-sha256": ref.sha256,
            "acl": "private",
        }
        conditions: list[object] = [
            {"bucket": self.bucket},
            ["eq", "$key", ref.key],
            ["content-length-range", ref.size_bytes, ref.size_bytes],
            {"Content-Type": ref.media_type},
            {"x-amz-server-side-encryption": "aws:kms"},
            {"x-amz-server-side-encryption-aws-kms-key-id": self.kms_key_id},
            {"x-amz-meta-tenant-id": str(ref.tenant_id)},
            {"x-amz-meta-workspace-id": str(ref.workspace_id)},
            {"x-amz-meta-document-id": str(ref.document_id)},
            {"x-amz-meta-version-id": str(ref.version_id)},
            {"x-amz-meta-sha256": ref.sha256},
            {"acl": "private"},
        ]
        response = client.generate_presigned_post(
            Bucket=self.bucket,
            Key=ref.key,
            Fields=fields,
            Conditions=conditions,
            ExpiresIn=self.expiry_seconds,
        )
        from datetime import UTC, timedelta

        return PresignedPost(
            url=response["url"],
            fields=response["fields"],
            conditions=conditions,
            expires_at=datetime.now(tz=UTC) + timedelta(seconds=self.expiry_seconds),
            object_ref=ref,
        )
