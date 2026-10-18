import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import stoneart_products


GALLERY = [
    {"url": "/uploads/cover.jpg", "alt": "Marble statue cover"},
    {"url": "/uploads/detail.jpg", "alt": "Marble statue detail"},
]


class BodyImagePlaceholderTests(unittest.TestCase):
    def test_markdown_placeholders_use_final_gallery_urls(self):
        payload = {
            "body_markdown": (
                "Intro\n\n{{product_image:1}}\n\n"
                "## Detail\n\n{{product_image:2}}"
            )
        }

        stoneart_products.render_product_images_in_body(payload, GALLERY)

        self.assertIn(
            "![Marble statue cover](/uploads/cover.jpg)",
            payload["body_markdown"],
        )
        self.assertIn(
            "![Marble statue detail](/uploads/detail.jpg)",
            payload["body_markdown"],
        )
        self.assertEqual(
            stoneart_products.unresolved_body_image_placeholders(payload), []
        )

    def test_html_placeholders_render_as_figures(self):
        payload = {"body_html": "<p>Intro</p>{{product_image:1}}"}

        stoneart_products.render_product_images_in_body(payload, GALLERY)

        self.assertIn(
            '<figure><img src="/uploads/cover.jpg" '
            'alt="Marble statue cover" loading="lazy"></figure>',
            payload["body_html"],
        )
        self.assertEqual(
            stoneart_products.unresolved_body_image_placeholders(payload), []
        )

    def test_unresolved_placeholder_is_reported(self):
        payload = {"body_html": "{{product_image:3}}"}

        stoneart_products.render_product_images_in_body(payload, GALLERY)

        self.assertEqual(
            stoneart_products.unresolved_body_image_placeholders(payload), [3]
        )

    def test_placeholder_inside_existing_figure_is_reported(self):
        payload = {
            "body_html": (
                '<figure><img src="{{product_image:1}}" alt="Wrong"></figure>'
            )
        }

        self.assertEqual(
            stoneart_products.body_image_placeholders_inside_figures(payload), [1]
        )

    def test_placeholder_between_figures_is_not_reported(self):
        payload = {
            "body_html": (
                "<figure><img src=\"/uploads/cover.jpg\" alt=\"Cover\"></figure>"
                "{{product_image:2}}"
                "<figure><img src=\"/uploads/detail.jpg\" alt=\"Detail\"></figure>"
            )
        }

        self.assertEqual(
            stoneart_products.body_image_placeholders_inside_figures(payload), []
        )


if __name__ == "__main__":
    unittest.main()
