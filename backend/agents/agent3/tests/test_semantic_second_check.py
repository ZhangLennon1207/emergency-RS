import tempfile
import unittest
from pathlib import Path

from PIL import Image

from backend.agents.agent3.src.second_check_crop_builder import mask_bbox


class SemanticSecondCheckTest(unittest.TestCase):
    def _mask(self, pixels):
        path = Path(tempfile.mkdtemp()) / "mask.png"
        image = Image.new("RGB", (8, 6), "black")
        for x, y, color in pixels:
            image.putpixel((x, y), color)
        image.save(path)
        return path

    def test_road_roi_uses_largest_affected_component(self):
        path = self._mask([
            (2, 1, (255, 0, 0)),
            (3, 1, (200, 20, 20)),
            (5, 4, (255, 0, 0)),
            (7, 5, (0, 255, 0)),
        ])
        self.assertEqual(mask_bbox(path, mode="road"), (2, 1, 4, 2))

    def test_surface_roi_uses_non_background_pixels(self):
        path = self._mask([(1, 2, (20, 20, 20)), (6, 4, (0, 0, 200))])
        self.assertEqual(mask_bbox(path, mode="surface"), (1, 2, 7, 5))


if __name__ == "__main__":
    unittest.main()
