import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import stoneart_products


class ProductWeightTests(unittest.TestCase):
    def test_weight_is_a_writable_product_field(self):
        self.assertIn("weight", stoneart_products.PRODUCT_FIELDS)

    def test_weight_is_in_product_summary(self):
        summary = stoneart_products.product_summary(
            {"id": 1, "title": "Marble Angel", "weight": "Approx. 500 kg"}
        )
        self.assertEqual(summary["weight"], "Approx. 500 kg")

    def test_merge_defaults_preserves_weight(self):
        payload, _ = stoneart_products.merge_defaults(
            {
                "title": "Marble Angel Statue",
                "slug": "marble-angel-statue",
                "body_markdown": "A carved marble angel statue.",
                "weight": "Approx. 500 kg",
            },
            {},
        )
        self.assertEqual(payload["weight"], "Approx. 500 kg")

    def test_missing_weight_produces_a_warning(self):
        _, warnings = stoneart_products.validate_product(
            {
                "title": "Marble Angel Statue",
                "slug": "marble-angel-statue",
                "body_markdown": "A carved marble angel statue.",
                "status": "draft",
                "weight": "",
            },
            category_ids=[],
            has_image=False,
        )
        self.assertTrue(any("Weight is empty" in warning for warning in warnings))


if __name__ == "__main__":
    unittest.main()
