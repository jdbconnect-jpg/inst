import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import urllib.error
import urllib.parse

from reels.instagram import ApiError, InstagramClient, NoRedirect, prepare, public_video_url, publish, receipt_lock


class InstagramTests(unittest.TestCase):
    def setUp(self):
        self.client = InstagramClient("123", "test-secret-token")
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.receipt = Path(self.directory.name) / "receipt.json"

    def test_official_reels_request_and_token_not_in_url(self):
        response = io.BytesIO(b'{"id":"456"}')
        self.client.opener.open = Mock(return_value=response)
        result = self.client.create_container("https://cdn.example.com/reel.mp4", "한글 캡션")
        self.assertEqual(result, "456")
        request = self.client.opener.open.call_args.args[0]
        self.assertEqual(request.full_url, "https://graph.instagram.com/v24.0/123/media")
        self.assertEqual(request.get_header("Authorization"), "Bearer test-secret-token")
        body = urllib.parse.parse_qs(request.data.decode())
        self.assertEqual(body["media_type"], ["REELS"])
        self.assertEqual(body["caption"], ["한글 캡션"])
        self.assertNotIn("access_token", body)

    def test_rejects_local_and_insecure_urls(self):
        for url in ("http://example.com/a.mp4", "https://127.0.0.1/a.mp4", "https://10.0.0.1/a.mp4",
                    "https://localhost/a.mp4", "https://host.local/a.mp4", "https://user:pass@example.com/a.mp4"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                public_video_url(url)

    def test_caption_length_checked_before_api(self):
        self.client.request = Mock()
        with self.assertRaises(ValueError):
            self.client.create_container("https://cdn.example.com/reel.mp4", "가" * 2201)
        self.client.request.assert_not_called()

    def test_waits_for_processing(self):
        self.client.status = Mock(side_effect=["IN_PROGRESS", "FINISHED"])
        with patch("reels.instagram.time.sleep"):
            self.assertEqual(self.client.wait_ready("456"), "FINISHED")

    def test_processing_failures_and_timeout(self):
        for status in ("ERROR", "EXPIRED", "PUBLISHED", "IN_PROGRESS"):
            with self.subTest(status=status):
                self.client.status = Mock(return_value=status)
                with self.assertRaises(ApiError):
                    self.client.wait_ready("456", timeout=0)

    def test_prepare_does_not_publish_and_does_not_repeat(self):
        self.client.request = Mock(return_value={"id": "456"})
        receipt = prepare(self.client, "https://cdn.example.com/reel.mp4?signature=private", "caption", self.receipt)
        self.assertEqual(receipt["state"], "created")
        self.assertNotIn("private", self.receipt.read_text())
        self.assertNotIn("test-secret-token", self.receipt.read_text())
        with self.assertRaises(ValueError):
            prepare(self.client, "https://cdn.example.com/reel.mp4", "caption", self.receipt)
        self.assertEqual(self.client.request.call_count, 1)
        self.assertEqual(self.client.request.call_args.args[1], "123/media")

    def test_publish_only_once(self):
        self.client.request = Mock(return_value={"id": "456"})
        prepare(self.client, "https://cdn.example.com/reel.mp4", "caption", self.receipt)
        self.client.status = Mock(return_value="FINISHED")
        self.client.request = Mock(return_value={"id": "789"})
        first = publish(self.client, self.receipt)
        second = publish(self.client, self.receipt)
        self.assertEqual(first, second)
        self.assertEqual(first["media_id"], "789")
        self.client.request.assert_called_once_with("POST", "123/media_publish", {"creation_id": "456"})

    def test_unfinished_container_is_not_published(self):
        self.client.request = Mock(return_value={"id": "456"})
        prepare(self.client, "https://cdn.example.com/reel.mp4", "caption", self.receipt)
        self.client.status = Mock(return_value="IN_PROGRESS")
        self.client.request.reset_mock()
        with self.assertRaises(ValueError):
            publish(self.client, self.receipt)
        self.client.request.assert_not_called()

    def test_uncertain_publish_does_not_retry(self):
        self.client.request = Mock(return_value={"id": "456"})
        prepare(self.client, "https://cdn.example.com/reel.mp4", "caption", self.receipt)
        self.client.status = Mock(return_value="FINISHED")
        self.client.request = Mock(side_effect=ApiError("Connection lost"))
        with self.assertRaises(ApiError):
            publish(self.client, self.receipt)
        self.assertEqual(json.loads(self.receipt.read_text())["state"], "publishing")
        with self.assertRaises(ValueError):
            publish(self.client, self.receipt)
        self.client.request.assert_called_once()

    def test_different_account_cannot_use_receipt(self):
        self.client.request = Mock(return_value={"id": "456"})
        prepare(self.client, "https://cdn.example.com/reel.mp4", "caption", self.receipt)
        other = InstagramClient("999", "other-token")
        other.request = Mock()
        with self.assertRaises(ValueError):
            publish(other, self.receipt)
        other.request.assert_not_called()

    def test_receipt_lock_excludes_concurrent_writes(self):
        with receipt_lock(self.receipt):
            with self.assertRaises(ValueError):
                with receipt_lock(self.receipt):
                    self.fail("Second lock acquired")

    def test_errors_do_not_echo_credentials(self):
        error = urllib.error.HTTPError("https://graph.instagram.com", 400, "test-secret-token", {}, io.BytesIO(b'test-secret-token'))
        self.client.opener.open = Mock(side_effect=error)
        with self.assertRaises(ApiError) as caught:
            self.client.account()
        self.assertNotIn("test-secret-token", str(caught.exception))

    def test_redirects_do_not_forward_token(self):
        handler = NoRedirect()
        self.assertIsNone(handler.redirect_request(None, None, 302, "redirect", {}, "https://other.example"))


if __name__ == "__main__":
    unittest.main()
