import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import stoneart_products


class ImageEditFallbackTests(unittest.TestCase):
    def test_local_success_skips_wan(self):
        config = {"LOCAL_IMAGE_ENABLED": "true", "LOCAL_IMAGE_MODEL": "qwen-image-2.1"}
        with patch.object(
            stoneart_products, "call_local_image_edit", return_value="http://local/image.jpg"
        ), patch.object(
            stoneart_products,
            "call_wan_edit",
            side_effect=AssertionError("Wan must not be called"),
        ):
            result = stoneart_products.edit_image_with_fallback(
                config, Path("source.jpg"), "clean watermark", "auto"
            )
        self.assertEqual(result["provider"], "local-qwen")
        self.assertEqual(result["remote_url"], "http://local/image.jpg")
        self.assertEqual(result["attempts"][0]["status"], "succeeded")

    def test_local_failure_falls_back_to_wan(self):
        config = {
            "LOCAL_IMAGE_ENABLED": "true",
            "LOCAL_IMAGE_MODEL": "qwen-image-2.1",
            "WAN_IMAGE_MODEL": "wan2.7-image",
        }
        with patch.object(
            stoneart_products,
            "call_local_image_edit",
            side_effect=RuntimeError("local offline"),
        ), patch.object(
            stoneart_products,
            "call_wan_edit",
            return_value=("http://wan/image.jpg", "wan-compatible"),
        ):
            result = stoneart_products.edit_image_with_fallback(
                config, Path("source.jpg"), "clean watermark", "auto"
            )
        self.assertEqual(result["provider"], "wan2.7")
        self.assertEqual(result["model"], "wan2.7-image")
        self.assertEqual(result["attempts"][0]["status"], "failed")
        self.assertEqual(result["attempts"][1]["status"], "succeeded")

    def test_disabling_local_skips_local_attempt(self):
        config = {"LOCAL_IMAGE_ENABLED": "false", "WAN_IMAGE_MODEL": "wan2.7-image"}
        with patch.object(
            stoneart_products,
            "call_local_image_edit",
            side_effect=AssertionError("local must be skipped"),
        ), patch.object(
            stoneart_products,
            "call_wan_edit",
            return_value=("http://wan/image.jpg", "wan-compatible"),
        ):
            result = stoneart_products.edit_image_with_fallback(
                config, Path("source.jpg"), "clean watermark", "auto"
            )
        self.assertEqual(len(result["attempts"]), 1)
        self.assertEqual(result["attempts"][0]["provider"], "wan2.7")


if __name__ == "__main__":
    unittest.main()
