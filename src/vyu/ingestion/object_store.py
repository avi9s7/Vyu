from __future__ import annotations

import hashlib
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol
from uuid import UUID

from src.vyu.ingestion.validation import sanitize_filename


VERIFY_TERMINAL_CODES = frozenset(
    {
        "object_verified",
        "object_missing",
        "size_mismatch",
        "checksum_mismatch",
        "scope_metadata_mismatch",
        "encryption_missing",
        "content_type_mismatch",
    }
)


class ObjectNotFoundError(Exception):
    """Raised when a quarantine object is missing from storage."""


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


@dataclass(frozen=True)
class QuarantineObjectHead:
    bucket: str
    key: str
    content_length: int
    content_type: str | None
    server_side_encryption: str | None
    ssekms_key_id: str | None
    metadata: dict[str, str]
    checksum_sha256: str | None = None


@dataclass
class StoredQuarantineObject:
    ref: QuarantineObjectRef
    body: bytes
    content_type: str | None = None
    server_side_encryption: str | None = "aws:kms"
    ssekms_key_id: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)


class QuarantineObjectStore(Protocol):
    def create_presigned_upload(self, ref: QuarantineObjectRef) -> PresignedPost: ...

    def head_object(self, ref: QuarantineObjectRef) -> QuarantineObjectHead | None: ...

    def iter_object_chunks(
        self,
        ref: QuarantineObjectRef,
        *,
        chunk_size: int = 1024 * 1024,
    ) -> Iterator[bytes]: ...


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


def default_scope_metadata(ref: QuarantineObjectRef) -> dict[str, str]:
    return {
        "tenant-id": str(ref.tenant_id),
        "workspace-id": str(ref.workspace_id),
        "document-id": str(ref.document_id),
        "version-id": str(ref.version_id),
        "sha256": ref.sha256,
    }


def metadata_value(metadata: dict[str, str], name: str) -> str | None:
    hyphenated = name.replace("_", "-")
    return metadata.get(name) or metadata.get(hyphenated)


def stream_sha256_hex(chunks: Iterator[bytes]) -> str:
    digest = hashlib.sha256()
    for chunk in chunks:
        digest.update(chunk)
    return digest.hexdigest()


@dataclass
class RecordingQuarantineObjectStore:
    bucket: str
    region: str
    kms_key_id: str
    expiry_seconds: int
    upload_url: str = "https://s3.local/quarantine"
    posts: list[PresignedPost] = field(default_factory=list)
    stored: dict[str, StoredQuarantineObject] = field(default_factory=dict)

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

    def seed_object(
        self,
        ref: QuarantineObjectRef,
        body: bytes,
        *,
        metadata_overrides: dict[str, str] | None = None,
        content_type: str | None = None,
        server_side_encryption: str | None = "aws:kms",
        ssekms_key_id: str | None = None,
        include_checksum_metadata: bool = True,
    ) -> None:
        metadata = default_scope_metadata(ref)
        if not include_checksum_metadata:
            metadata.pop("sha256", None)
        if metadata_overrides:
            metadata.update(metadata_overrides)
        self.stored[ref.key] = StoredQuarantineObject(
            ref=ref,
            body=body,
            content_type=content_type or ref.media_type,
            server_side_encryption=server_side_encryption,
            ssekms_key_id=ssekms_key_id or self.kms_key_id,
            metadata=metadata,
        )

    def head_object(self, ref: QuarantineObjectRef) -> QuarantineObjectHead | None:
        stored = self.stored.get(ref.key)
        if stored is None:
            return None
        checksum = metadata_value(stored.metadata, "sha256")
        return QuarantineObjectHead(
            bucket=ref.bucket,
            key=ref.key,
            content_length=len(stored.body),
            content_type=stored.content_type,
            server_side_encryption=stored.server_side_encryption,
            ssekms_key_id=stored.ssekms_key_id,
            metadata=dict(stored.metadata),
            checksum_sha256=checksum,
        )

    def iter_object_chunks(
        self,
        ref: QuarantineObjectRef,
        *,
        chunk_size: int = 1024 * 1024,
    ) -> Iterator[bytes]:
        stored = self.stored.get(ref.key)
        if stored is None:
            raise ObjectNotFoundError(ref.key)
        for offset in range(0, len(stored.body), chunk_size):
            yield stored.body[offset : offset + chunk_size]


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

    def head_object(self, ref: QuarantineObjectRef) -> QuarantineObjectHead | None:
        import botocore.exceptions
        import boto3

        client = boto3.client("s3", region_name=self.region)
        try:
            response = client.head_object(Bucket=ref.bucket, Key=ref.key)
        except botocore.exceptions.ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code")
            if error_code in {"404", "NoSuchKey", "NotFound"}:
                return None
            raise
        metadata = {str(key): str(value) for key, value in response.get("Metadata", {}).items()}
        checksum = metadata_value(metadata, "sha256")
        return QuarantineObjectHead(
            bucket=ref.bucket,
            key=ref.key,
            content_length=int(response.get("ContentLength", 0)),
            content_type=response.get("ContentType"),
            server_side_encryption=response.get("ServerSideEncryption"),
            ssekms_key_id=response.get("SSEKMSKeyId"),
            metadata=metadata,
            checksum_sha256=checksum,
        )

    def iter_object_chunks(
        self,
        ref: QuarantineObjectRef,
        *,
        chunk_size: int = 1024 * 1024,
    ) -> Iterator[bytes]:
        import boto3

        client = boto3.client("s3", region_name=self.region)
        response = client.get_object(Bucket=ref.bucket, Key=ref.key)
        body = response["Body"]
        while True:
            chunk = body.read(chunk_size)
            if not chunk:
                break
            yield chunk
