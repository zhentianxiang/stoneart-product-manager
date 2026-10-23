import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import stoneart_products


class ProductNameZHTests(unittest.TestCase):
    def test_name_zh_is_a_writable_product_field(self):
        self.assertIn("name_zh", stoneart_products.PRODUCT_FIELDS)

    def test_missing_name_zh_produces_a_warning(self):
        _, warnings = stoneart_products.validate_product(
            {
                "title": "White Marble Angel Headstone",
                "slug": "white-marble-angel-headstone",
                "body_markdown": "A carved marble angel headstone.",
                "status": "draft",
                "name_zh": "",
            },
            category_ids=[],
            has_image=False,
        )
        self.assertTrue(any("name_zh" in warning for warning in warnings))

    def test_existing_name_zh_is_preserved(self):
        payload = {
            "title": "White Marble Angel Headstone",
            "name_zh": "白色大理石天使墓碑",
        }
        with patch.object(
            stoneart_products,
            "translate_title_zh",
            side_effect=AssertionError("translation must not run"),
        ):
            result = stoneart_products.ensure_product_name_zh({}, payload)
        self.assertEqual(result, "白色大理石天使墓碑")

    def test_missing_name_zh_is_generated(self):
        payload = {"title": "White Marble Angel Headstone"}
        with patch.object(
            stoneart_products,
            "translate_title_zh",
            return_value="白色大理石天使墓碑",
        ):
            result = stoneart_products.ensure_product_name_zh({}, payload)
        self.assertEqual(result, "白色大理石天使墓碑")
        self.assertEqual(payload["name_zh"], "白色大理石天使墓碑")


if __name__ == "__main__":
    unittest.main()
