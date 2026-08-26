import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from ..Renderer.PrtsImageCache import PrtsImageCache


class PrtsImageCacheTests(unittest.TestCase):
    def test_valid_png_is_cached_and_reused_without_second_request(self):
        png_content = PrtsImageCache.PNG_SIGNATURE + b"test-image"
        response = Mock(
            content=png_content,
            headers={"Content-Type": "image/png"},
        )
        response.raise_for_status.return_value = None

        with tempfile.TemporaryDirectory() as temporary_dir:
            cache = PrtsImageCache(Path(temporary_dir))
            with patch(
                f"{PrtsImageCache.__module__}.requests.get",
                return_value=response,
            ) as request:
                first = cache.get_png("测试干员", "https://example.test/avatar.png")
                second = cache.get_png("测试干员", "https://example.test/avatar.png")

        self.assertTrue(first.startswith("data:image/png;base64,"))
        self.assertEqual(second, first)
        request.assert_called_once_with(
            "https://example.test/avatar.png",
            timeout=PrtsImageCache.REQUEST_TIMEOUT,
        )


if __name__ == "__main__":
    unittest.main()
