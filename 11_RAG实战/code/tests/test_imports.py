import os
import subprocess
import sys
import unittest
from pathlib import Path


CODE_DIR = Path(__file__).resolve().parents[1]
MODULES = [
    "s02_data_pipeline",
    "s03_embedding",
    "s04_vector_db",
    "s05_hybrid_retrieval",
    "s06_query_rewrite",
    "s07_graphrag",
    "s08_agentic_rag",
    "s09_evaluation",
    "s11_colbert_sparse",
    "s12_citation_grounded_gen",
    "s13_serving_security",
    "s14_multimodal_rag",
]


class ImportTests(unittest.TestCase):
    def test_all_section_modules_import_without_credentials_or_network(self):
        env = os.environ.copy()
        for key in (
            "OPENAI_API_KEY",
            "OPENAI_ADMIN_KEY",
            "ARK_API_KEY",
            "MIMO_API_KEY",
        ):
            env.pop(key, None)
        command = [sys.executable, "-c", ";".join(f"import {module}" for module in MODULES)]
        result = subprocess.run(
            command,
            cwd=CODE_DIR,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
