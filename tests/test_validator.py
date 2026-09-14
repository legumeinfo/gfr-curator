import unittest
import os
from gfr_curator.validator import (
    load_schema,
    validate_document,
    validate_yaml_string,
    validate_yaml_file,
)

VALID_SAMPLE_YAML = """---
scientific_name: Glycine max
gene_symbols:
  - GmCIF1
gene_symbol_long: Cell Wall Invertase Inhibitor 1
gene_model_pub_name: Glyma.17G036300
gene_model_full_id: glyma.Wm82.gnm2.ann1.Glyma.17G036300
confidence: 5
curators:
  - AI Curation Assistant
comments:
  - "Post-translationally regulates cell wall invertase."
phenotype_synopsis: "Silencing leads to increased seed weight."
traits:
  - entity_name: seed weight
    entity: TO:0000181
references:
  - citation: Tang, Su et al., 2017
    doi: 10.1093/jxb/erw425
    pmid: 28204559
"""

class TestValidator(unittest.TestCase):
    def setUp(self):
        self.schema = load_schema()

    def test_schema_loaded(self):
        self.assertIsInstance(self.schema, dict)
        self.assertIn("properties", self.schema)
        self.assertIn("scientific_name", self.schema["properties"])

    def test_valid_yaml_document(self):
        is_valid, results = validate_yaml_string(VALID_SAMPLE_YAML, schema=self.schema)
        self.assertTrue(is_valid)
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0]["is_valid"])
        self.assertEqual(len(results[0]["errors"]), 0)

    def test_multi_document_yaml(self):
        multi_yaml = VALID_SAMPLE_YAML + "\n" + VALID_SAMPLE_YAML
        is_valid, results = validate_yaml_string(multi_yaml, schema=self.schema)
        self.assertTrue(is_valid)
        self.assertEqual(len(results), 2)
        self.assertTrue(results[0]["is_valid"])
        self.assertTrue(results[1]["is_valid"])

    def test_invalid_confidence_range(self):
        invalid_yaml = VALID_SAMPLE_YAML.replace("confidence: 5", "confidence: 1")
        is_valid, results = validate_yaml_string(invalid_yaml, schema=self.schema)
        self.assertFalse(is_valid)
        self.assertFalse(results[0]["is_valid"])
        self.assertTrue(any("confidence" in err for err in results[0]["errors"]))

    def test_missing_required_field(self):
        invalid_yaml = VALID_SAMPLE_YAML.replace("phenotype_synopsis: \"Silencing leads to increased seed weight.\"", "")
        is_valid, results = validate_yaml_string(invalid_yaml, schema=self.schema)
        self.assertFalse(is_valid)
        self.assertFalse(results[0]["is_valid"])
        self.assertTrue(any("phenotype_synopsis" in err for err in results[0]["errors"]))

    def test_invalid_scientific_name_pattern(self):
        invalid_yaml = VALID_SAMPLE_YAML.replace("scientific_name: Glycine max", "scientific_name: glycine_max")
        is_valid, results = validate_yaml_string(invalid_yaml, schema=self.schema)
        self.assertFalse(is_valid)
        self.assertTrue(any("scientific_name" in err for err in results[0]["errors"]))

    def test_invalid_citation_pattern(self):
        invalid_yaml = VALID_SAMPLE_YAML.replace("citation: Tang, Su et al., 2017", "citation: InvalidCitation")
        is_valid, results = validate_yaml_string(invalid_yaml, schema=self.schema)
        self.assertFalse(is_valid)
        self.assertTrue(any("citation" in err for err in results[0]["errors"]))

    def test_validate_sample_file(self):
        sample_path = os.path.join(os.path.dirname(__file__), "..", "glyma.Tang_Su_2017.yml")
        if not os.path.exists(sample_path):
            sample_path = os.path.join(os.path.dirname(__file__), "..", "glyma.Tang_2017.yml")
        if os.path.exists(sample_path):
            is_valid, results = validate_yaml_file(sample_path, verbose=False)
            self.assertTrue(is_valid)
            self.assertEqual(len(results), 2)

    def test_validate_nonexistent_file(self):
        is_valid, results = validate_yaml_file("nonexistent_test_file.yml", verbose=False)
        self.assertFalse(is_valid)
        self.assertIn("File not found", results[0]["errors"][0])

if __name__ == "__main__":
    unittest.main()
