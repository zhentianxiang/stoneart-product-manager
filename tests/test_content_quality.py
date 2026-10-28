import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import stoneart_products


BODY = (
    "A marble fountain for estate gardens.\n\n"
    "## Product Overview\n\n"
    "The fountain has a hand-carved bowl.\n\n"
    "## Material and Craftsmanship\n\n"
    "White marble with a honed finish.\n\n"
    "## Placement\n\n"
    "Designed for a formal garden."
)


class ProductContentQualityTests(unittest.TestCase):
    def test_missing_faq_is_added(self):
        payload = {"body_markdown": BODY}

        warnings = stoneart_products.ensure_product_body_quality(payload, {})

        self.assertIn("## Frequently Asked Questions", payload["body_markdown"])
        self.assertEqual(payload["body_markdown"].count("### "), 3)
        self.assertTrue(any("Added a factual FAQ" in warning for warning in warnings))

    def test_existing_faq_is_not_duplicated(self):
        body = BODY + (
            "\n\n## Frequently Asked Questions\n\n"
            "### Can it be customized?\n\nYes.\n\n"
            "### How is it quoted?\n\nBy project.\n\n"
            "### What details are needed?\n\nSize and finish."
        )
        payload = {"body_markdown": body}

        stoneart_products.ensure_product_body_quality(payload, {})

        self.assertEqual(
            payload["body_markdown"].lower().count("## frequently asked questions"),
            1,
        )

    def test_detail_image_is_inserted_in_relevant_section(self):
        payload = {"body_markdown": BODY}

        stoneart_products.ensure_product_body_quality(
            payload, {}, image_count=3
        )

        body = payload["body_markdown"]
        self.assertEqual(body.count("{{product_image:2}}"), 1)
        self.assertGreater(
            body.index("{{product_image:2}}"),
            body.index("## Product Overview"),
        )
        self.assertLess(
            body.index("{{product_image:2}}"),
            body.index("## Material and Craftsmanship"),
        )

    def test_existing_body_image_is_not_duplicated(self):
        body = BODY.replace(
            "## Material and Craftsmanship",
            "{{product_image:3}}\n\n## Material and Craftsmanship",
        )
        payload = {"body_markdown": body}

        stoneart_products.ensure_product_body_quality(
            payload, {}, image_count=4
        )

        self.assertEqual(payload["body_markdown"].count("{{product_image:"), 1)

    def test_single_image_does_not_add_body_placeholder(self):
        payload = {"body_markdown": BODY}

        stoneart_products.ensure_product_body_quality(
            payload, {}, image_count=1
        )

        self.assertNotIn("{{product_image:", payload["body_markdown"])

    def test_unrelated_legacy_update_does_not_append_faq(self):
        payload, _ = stoneart_products.merge_defaults(
            {
                "title": "Legacy Marble Fountain",
                "body_html": "<p>Existing legacy product copy.</p>",
            },
            {"PRODUCT_REQUIRE_FAQ": "true"},
        )

        self.assertNotIn("Frequently Asked Questions", payload["body_html"])


if __name__ == "__main__":
    unittest.main()
