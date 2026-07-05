import tempfile
import unittest
from pathlib import Path

from scripts.generate_phase1_corpus import generate_phase1_corpus
from src.vyu.ingestion.dummy_corpus import load_dummy_corpus
from src.vyu.retrieval import (
    DenseKeywordRetriever,
    MetadataFilter,
    RetrievalQuery,
    reciprocal_rank_fusion,
)


class Phase3FusionFilterTests(unittest.TestCase):
    def test_filter_excludes_retracted_documents_and_rrf_combines_ranks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            generate_phase1_corpus(root)
            corpus = load_dummy_corpus(root)
            retriever = DenseKeywordRetriever.from_corpus(corpus)

            filtered_hits = retriever.search(
                RetrievalQuery(
                    text="retracted VX-101 trial",
                    top_k=10,
                    metadata_filter=MetadataFilter(include_retracted=False),
                )
            )
            unfiltered_hits = retriever.search(RetrievalQuery(text="VX-101 trial", top_k=5))
            fused = reciprocal_rank_fusion([filtered_hits, unfiltered_hits], top_k=5)

        self.assertTrue(all(not hit.document.is_retracted for hit in filtered_hits))
        self.assertGreaterEqual(len(fused), 1)
        self.assertEqual("rrf", fused[0].score.source)


if __name__ == "__main__":
    unittest.main()
