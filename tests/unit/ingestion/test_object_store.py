from __future__ import annotations

from uuid import uuid4

from src.vyu.ingestion.object_store import (
    QuarantineObjectRef,
    RecordingQuarantineObjectStore,
    stream_sha256_hex,
)


def test_presigned_post_conditions_bind_exact_scope_and_encryption() -> None:
    store = RecordingQuarantineObjectStore(
        bucket="vyu-test-quarantine",
        region="ap-south-1",
        kms_key_id="arn:aws:kms:ap-south-1:123456789012:key/00000000-0000-0000-0000-000000000000",
        expiry_seconds=600,
    )
    tenant_id = uuid4()
    workspace_id = uuid4()
    document_id = uuid4()
    version_id = uuid4()
    ref = QuarantineObjectRef(
        bucket=store.bucket,
        key=f"test/{tenant_id}/{workspace_id}/quarantine/{document_id}/{version_id}/report.pdf",
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        document_id=document_id,
        version_id=version_id,
        filename="report.pdf",
        media_type="application/pdf",
        size_bytes=2048,
        sha256="d" * 64,
    )
    post = store.create_presigned_upload(ref)
    assert post.fields["key"] == ref.key
    assert {"x-amz-server-side-encryption": "aws:kms"} in post.conditions
    assert {"acl": "private"} in post.conditions
    assert ["content-length-range", 2048, 2048] in post.conditions
    assert {"x-amz-meta-tenant-id": str(tenant_id)} in post.conditions
    wrong_tenant_condition = {"x-amz-meta-tenant-id": str(uuid4())}
    assert wrong_tenant_condition not in post.conditions


def test_presigned_post_rejects_wrong_key_in_conditions() -> None:
    store = RecordingQuarantineObjectStore(
        bucket="vyu-test-quarantine",
        region="ap-south-1",
        kms_key_id="arn:aws:kms:ap-south-1:123456789012:key/00000000-0000-0000-0000-000000000000",
        expiry_seconds=600,
    )
    ref = QuarantineObjectRef(
        bucket=store.bucket,
        key="test/key/report.pdf",
        tenant_id=uuid4(),
        workspace_id=uuid4(),
        document_id=uuid4(),
        version_id=uuid4(),
        filename="report.pdf",
        media_type="application/pdf",
        size_bytes=1024,
        sha256="e" * 64,
    )
    post = store.create_presigned_upload(ref)
    assert ["eq", "$key", ref.key] in post.conditions
    assert ["eq", "$key", "some/other/key.pdf"] not in post.conditions


def test_stream_sha256_hex_reads_in_chunks() -> None:
    payload = b"chunk-one" * 1024 + b"chunk-two" * 1024

    def chunks():
        yield payload[:1024]
        yield payload[1024:2048]
        yield payload[2048:]

    import hashlib

    assert stream_sha256_hex(chunks()) == hashlib.sha256(payload).hexdigest()
