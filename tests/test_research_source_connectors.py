import unittest

from src.vyu.connectors import (
    ClinicalTrialsConnector,
    GuidelineSourceConnector,
    InternalDocumentConnector,
    SearchRequest,
    SemanticScholarConnector,
)
from src.vyu.contracts import DocumentRecord, PassageRecord, StudyDesign


def document(source_type: str, document_id: str) -> DocumentRecord:
    return DocumentRecord(
        document_id=document_id,
        title="VX-101 migraine evidence source",
        year=2026,
        study_design=StudyDesign.UNKNOWN,
        source_type=source_type,
        publication_status="governed_placeholder",
        abstract="VX-101 migraine evidence metadata for governed connector boundary tests.",
    )


class ResearchSourceConnectorShellTests(unittest.TestCase):
    def test_static_connector_shells_return_normalized_connector_results(self):
        connector_classes = [
            SemanticScholarConnector,
            ClinicalTrialsConnector,
            GuidelineSourceConnector,
            InternalDocumentConnector,
        ]

        for connector_class in connector_classes:
            with self.subTest(connector_class=connector_class.__name__):
                doc = document(source_type=connector_class().source, document_id=f"{connector_class().source}-1")
                passage = PassageRecord(
                    passage_id=f"{doc.document_id}-P1",
                    document_id=doc.document_id,
                    section="summary",
                    text=doc.abstract,
                )
                connector = connector_class(documents=[doc], passages=[passage])

                result = connector.search(SearchRequest(query="VX-101", limit=5))

                self.assertEqual(connector.source, result.source)
                self.assertEqual([doc.document_id], [item.document_id for item in result.documents])
                self.assertEqual([passage.passage_id], [item.passage_id for item in result.passages])


if __name__ == "__main__":
    unittest.main()
