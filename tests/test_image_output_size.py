import sys
import tempfile
import unittest
from os import environ
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import stoneart_products
from PIL import Image


class ImageOutputSizeTests(unittest.TestCase):
    def test_default_output_is_1024_square(self):
        self.assertEqual(stoneart_products.image_edit_output_size({}), (1024, 1024))

    def test_output_size_is_environment_configurable(self):
        config = {
            "IMAGE_EDIT_OUTPUT_WIDTH": "1200",
            "IMAGE_EDIT_OUTPUT_HEIGHT": "800",
        }
        self.assertEqual(stoneart_products.image_edit_output_size(config), (1200, 800))

    def test_output_size_is_loaded_from_environment(self):
        with patch.dict(
            environ,
            {
                "IMAGE_EDIT_OUTPUT_WIDTH": "1400",
                "IMAGE_EDIT_OUTPUT_HEIGHT": "900",
            },
        ):
            config = stoneart_products.load_config(Path("/nonexistent/config.env"))

        self.assertEqual(stoneart_products.image_edit_output_size(config), (1400, 900))

    def test_non_square_edit_is_normalized_without_distortion(self):
        config = {"IMAGE_EDIT_OUTPUT_WIDTH": "512", "IMAGE_EDIT_OUTPUT_HEIGHT": "512"}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "edited.jpg"
            Image.new("RGB", (900, 600), "white").save(path, format="JPEG")

            result = stoneart_products.normalize_edited_image(path, config)

            with Image.open(path) as image:
                self.assertEqual(image.size, (512, 512))
            self.assertTrue(result["adjusted"])
            self.assertEqual(result["fit"], "cover")

    def test_already_exact_image_is_not_reencoded(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "edited.jpg"
            Image.new("RGB", (1024, 1024), "white").save(
                path, format="JPEG", quality=82
            )
            before = path.read_bytes()

            result = stoneart_products.normalize_edited_image(path, {})

            self.assertEqual(path.read_bytes(), before)
            self.assertFalse(result["adjusted"])


if __name__ == "__main__":
    unittest.main()
