# Production Source Registry Schema

## Purpose

The production source registry controls which literature, documents, datasets, models, and customer artifacts Vyu may ingest or query. No source should enter a production workflow without an approved registry record.

## Required Fields

| Field | Description |
| --- | --- |
| `source_id` | Stable source identifier used in manifests and audit records |
| `display_name` | Human-readable source name |
| `source_type` | `public_literature`, `licensed_content`, `customer_document`, `patient_data`, or `model_artifact` |
| `owner` | Source owner or steward |
| `license_or_terms` | Licence, terms URL, contract ID, or internal policy reference |
| `allowed_uses` | Approved use cases for this source |
| `forbidden_uses` | Explicitly disallowed use cases |
| `attribution_required` | Whether reports must include attribution |
| `retention_policy` | Retention period and deletion process |
| `update_cadence` | Expected refresh schedule |
| `phi_pii_status` | `none`, `possible`, `contains_phi`, or `contains_pii` |
| `access_policy` | Tenant, role, or workspace restrictions |
| `connector_config_ref` | Runtime connector configuration reference, not secrets |
| `rate_limit_policy` | Request limits and backoff expectations |
| `approval_status` | `draft`, `approved`, `blocked`, or `retired` |
| `approved_by` | Named approver or approval group |
| `approved_at` | ISO-8601 approval timestamp |
| `source_version` | Source registry version used in manifests and tool-call records |
| `policy_version` | Source governance policy version used to evaluate source access |

## Example

```json
{
  "source_id": "pubmed",
  "display_name": "PubMed",
  "source_type": "public_literature",
  "owner": "National Library of Medicine",
  "license_or_terms": "NLM/NCBI usage terms",
  "allowed_uses": ["literature_search", "citation_metadata"],
  "forbidden_uses": ["bulk_full_text_without_terms_review"],
  "attribution_required": true,
  "retention_policy": "retain normalized metadata while source remains approved",
  "update_cadence": "daily",
  "phi_pii_status": "none",
  "access_policy": "all_approved_workspaces",
  "connector_config_ref": "connectors.pubmed",
  "rate_limit_policy": "pubmed-default",
  "approval_status": "draft",
  "approved_by": "",
  "approved_at": "",
  "source_version": "v1",
  "policy_version": "source_governance_policy_v1"
}
```

## Production Rules

- Source records must be immutable after approval; changes create a new version.
- Artifact manifests must include source IDs and source versions.
- PHI/ePHI sources require privacy and security approval before use.
- Licensed content must enforce access restrictions at query and export time.

## Scoped Access Policy Labels

When a source is evaluated with tenant/workspace context, `access_policy` supports these compact labels:

- `all` or `all_approved_workspaces`
- `tenant:<tenant_id>`
- `workspace:<workspace_id>`
- `workspace:<tenant_id>/<workspace_id>`
- `tenant:<tenant_id>:workspace:<workspace_id>`

Unknown scoped policy labels fail closed. This lets local artifact-generation sources remain approved for unscoped build workflows while preventing accidental tenant/workspace use unless the source record explicitly allows it.
