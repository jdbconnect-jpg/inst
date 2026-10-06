import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from PIL import Image

from reels.render import inspect_video, load_job, render


class RenderTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def job(self, **scene):
        path = self.root / "job.json"
        path.write_text(json.dumps({"caption": "한글 #릴스", "scenes": [
            {"title": "테스트 릴스", "text": "세로 영상과 한글 자막을 검증합니다", "duration": 3, **scene}]}))
        return path

    def test_invalid_duration_is_rejected(self):
        for value in (0, -1, float("nan"), float("inf"), True, "3"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                load_job(self.job(duration=value))

    def test_missing_image_is_rejected(self):
        with self.assertRaises(ValueError):
            load_job(self.job(image="missing.png"))

    def test_preserves_existing_output(self):
        target = self.root / "output"
        target.mkdir()
        (target / "user.txt").write_text("preserve")
        with self.assertRaises(ValueError):
            render(self.job(), target)
        self.assertEqual((target / "user.txt").read_text(), "preserve")

    def test_real_mp4_with_korean_image_and_audio(self):
        Image.new("RGB", (160, 120), "#2a5c60").save(self.root / "background.jpg")
        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=1", str(self.root / "tone.wav")], check=True)
        job = self.job(image="background.jpg")
        data = json.loads(job.read_text())
        data["audio"] = "tone.wav"
        job.write_text(json.dumps(data))
        result = render(job, self.root / "output")
        video = self.root / "output/reel.mp4"
        self.assertEqual(result["audio_source"], "file")
        self.assertAlmostEqual(result["duration"], 3, delta=0.1)
        self.assertEqual(inspect_video(video)["sha256"], result["sha256"])
        with Image.open(self.root / "output/cover.png") as image:
            self.assertEqual(image.size, (1080, 1920))
            self.assertGreater(len(image.getcolors(maxcolors=10_000_000)), 100)
        subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-f", "null", "-"], check=True)


if __name__ == "__main__":
    unittest.main()
