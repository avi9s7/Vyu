import tempfile
import unittest
from pathlib import Path

from src.vyu.sources import ProductionSourceRecord, SourceRegistry


class SourceRegistryTests(unittest.TestCase):
    def test_registry_blocks_unapproved_sources_for_production_use(self):
        registry = SourceRegistry(
            [
                ProductionSourceRecord(
                    source_id="pubmed",
                    display_name="PubMed",
                    source_type="public_literature",
                    owner="National Library of Medicine",
                    license_or_terms="NLM/NCBI usage terms",
                    allowed_uses=["literature_search"],
                    approval_status="draft",
                )
            ]
        )

        with self.assertRaises(PermissionError):
            registry.require_approved("pubmed")

    def test_registry_returns_approved_source_and_round_trips_json(self):
        source = ProductionSourceRecord(
            source_id="pubmed",
            display_name="PubMed",
            source_type="public_literature",
            owner="National Library of Medicine",
            license_or_terms="NLM/NCBI usage terms",
            allowed_uses=["literature_search", "citation_metadata"],
            forbidden_uses=["bulk_full_text_without_terms_review"],
            attribution_required=True,
            retention_policy="retain normalized metadata while source remains approved",
            update_cadence="daily",
            phi_pii_status="none",
            access_policy="all_approved_workspaces",
            connector_config_ref="connectors.pubmed",
            rate_limit_policy="pubmed-default",
            approval_status="approved",
            approved_by="production-review-board",
            approved_at="2026-06-13T00:00:00Z",
        )
        registry = SourceRegistry([source])

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "source_registry.json"
            registry.write(path)
            loaded = SourceRegistry.read(path)

        approved = loaded.require_approved("pubmed")

        self.assertEqual(source.to_json(), approved.to_json())
        self.assertEqual(["pubmed"], loaded.source_ids())

    def test_registry_rejects_duplicate_source_ids(self):
        source = ProductionSourceRecord(
            source_id="pubmed",
            display_name="PubMed",
            source_type="public_literature",
            owner="National Library of Medicine",
            license_or_terms="NLM/NCBI usage terms",
            allowed_uses=["literature_search"],
        )

        with self.assertRaises(ValueError):
            SourceRegistry([source, source])


if __name__ == "__main__":
    unittest.main()
