from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from PIL import Image, ImageDraw, ImageFont, ImageOps

WIDTH, HEIGHT, FPS = 1080, 1920, 30


def load_job(path: Path) -> dict:
    job = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(job, dict) or not isinstance(job.get("scenes"), list):
        raise ValueError("scenes 배열이 있는 JSON을 사용하세요.")
    if not 1 <= len(job["scenes"]) <= 30:
        raise ValueError("장면은 1~30개가 필요합니다.")
    total = 0
    for scene in job["scenes"]:
        if not isinstance(scene, dict):
            raise ValueError("장면은 JSON 객체여야 합니다.")
        duration = scene.get("duration", 3)
        if isinstance(duration, bool) or not isinstance(duration, (int, float)) or not math.isfinite(duration) or not 1 <= duration <= 60:
            raise ValueError("장면 길이는 1~60초여야 합니다.")
        scene["duration"] = round(duration * FPS) / FPS
        total += scene["duration"]
        for field, limit in (("title", 50), ("text", 180)):
            if not isinstance(scene.get(field), str) or not 1 <= len(scene[field].strip()) <= limit:
                raise ValueError(f"장면 {field}는 1~{limit}자 문자열이어야 합니다.")
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", scene.get("color", "#102C34")):
            raise ValueError("color는 #RRGGBB 형식이어야 합니다.")
        if scene.get("image"):
            scene["image"] = str((path.parent / scene["image"]).resolve())
            if not Path(scene["image"]).is_file():
                raise ValueError("장면 이미지 파일이 없습니다.")
    if not 3 <= total <= 180:
        raise ValueError("이 템플릿은 전체 길이 3~180초를 지원합니다.")
    for field, limit in (("caption", 2200), ("brand", 40), ("title", 100)):
        if not isinstance(job.get(field, ""), str) or len(job.get(field, "")) > limit:
            raise ValueError(f"{field}는 {limit}자 이하 문자열이어야 합니다.")
    if job.get("audio"):
        job["audio"] = str((path.parent / job["audio"]).resolve())
        if not Path(job["audio"]).is_file():
            raise ValueError("음성 또는 음악 파일이 없습니다.")
    return job


def font_path() -> str:
    candidates = [os.environ.get("REELS_FONT", ""),
                  "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
                  "/System/Library/Fonts/AppleSDGothicNeo.ttc"]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    raise ValueError("한글 폰트가 필요합니다. REELS_FONT에 폰트 파일 경로를 지정하세요.")


def wrap(draw, text, font, width):
    lines = []
    for paragraph in text.split("\n"):
        current = ""
        for char in paragraph:
            if current and draw.textlength(current + char, font=font) > width:
                lines.append(current)
                current = ""
            current += char
        lines.append(current)
    return lines


def text_block(draw, text, top, size, max_lines, fill):
    for current_size in range(size, 23, -2):
        font = ImageFont.truetype(font_path(), current_size)
        lines = wrap(draw, text, font, 840)
        if len(lines) <= max_lines:
            break
    else:
        raise ValueError("텍스트가 화면에 너무 깁니다. 내용을 줄여주세요.")
    for index, line in enumerate(lines):
        draw.text((120, top + index * (current_size + 22)), line, font=font, fill=fill)


def make_frame(job, scene, index, target):
    base = scene.get("color", "#102C34")
    rgb = tuple(int(base[i:i + 2], 16) for i in (1, 3, 5))
    canvas = Image.new("RGB", (WIDTH, HEIGHT), rgb)
    draw = ImageDraw.Draw(canvas)
    for y in range(HEIGHT):
        factor = 0.6 + 0.5 * (1 - y / HEIGHT)
        draw.line((0, y, WIDTH, y), fill=tuple(int(c * factor) for c in rgb))
    if scene.get("image"):
        with Image.open(scene["image"]) as source:
            background = ImageOps.fit(ImageOps.exif_transpose(source).convert("RGB"), (WIDTH, HEIGHT))
        canvas = Image.blend(background, canvas, 0.6)
        draw = ImageDraw.Draw(canvas)
    accent = "#E6C681"
    small = ImageFont.truetype(font_path(), 32)
    draw.rounded_rectangle((120, 250, 960, 254), radius=2, fill=accent)
    draw.text((120, 285), job.get("brand", "REELS STUDIO"), font=small, fill=accent)
    draw.text((120, 430), f"{index + 1:02d} / {len(job['scenes']):02d}", font=small, fill="#B7C7CA")
    text_block(draw, scene["title"], 550, 100, 3, "#FFFFFF")
    text_block(draw, scene["text"], 1010, 58, 5, "#E1EAED")
    for n in range(len(job["scenes"])):
        left = 120 + n * (840 / len(job["scenes"]))
        draw.rounded_rectangle((left, 1530, left + 840 / len(job["scenes"]) - 8, 1537), radius=3,
                               fill=accent if n <= index else "#637377")
    canvas.save(target)


def run_ffmpeg(args):
    result = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", *args], capture_output=True, text=True)
    if result.returncode:
        raise ValueError("FFmpeg 처리 실패: " + result.stderr[-1500:])


def inspect_video(path: Path) -> dict:
    result = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)], capture_output=True, text=True)
    if result.returncode:
        raise ValueError("FFprobe로 영상 정보를 읽을 수 없습니다.")
    data = json.loads(result.stdout)
    video = next((s for s in data["streams"] if s["codec_type"] == "video"), {})
    audio = next((s for s in data["streams"] if s["codec_type"] == "audio"), {})
    duration = float(data["format"]["duration"])
    if (video.get("width"), video.get("height")) != (WIDTH, HEIGHT) or video.get("codec_name") != "h264" or video.get("pix_fmt") != "yuv420p":
        raise ValueError("1080×1920 H.264 / yuv420p 영상이 필요합니다.")
    if audio.get("codec_name") != "aac" or not 3 <= duration <= 181:
        raise ValueError("AAC 오디오와 3~180초 길이의 영상이 필요합니다.")
    numerator, denominator = video.get("avg_frame_rate", "0/1").split("/")
    if not 23 <= float(numerator) / float(denominator) <= 60:
        raise ValueError("지원하는 프레임 속도는 23~60fps입니다.")
    with path.open("rb") as source:
        digest = hashlib.file_digest(source, "sha256").hexdigest()
    return {"width": WIDTH, "height": HEIGHT, "duration": duration, "sha256": digest,
            "video_codec": "h264", "audio_codec": "aac", "bytes": path.stat().st_size}


def render(job_path: Path, output: Path) -> dict:
    job = load_job(job_path.resolve())
    font_path()
    for binary in ("ffmpeg", "ffprobe"):
        if not shutil.which(binary):
            raise ValueError(f"{binary}를 설치하세요.")
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValueError("출력 폴더가 비어 있지 않습니다. 새 폴더를 지정하세요.")
    duration = sum(s["duration"] for s in job["scenes"])
    with tempfile.TemporaryDirectory(prefix="reels-") as temp:
        work = Path(temp)
        for i, scene in enumerate(job["scenes"]):
            frame, clip = work / f"frame-{i}.png", work / f"clip-{i}.mp4"
            make_frame(job, scene, i, frame)
            if i == 0:
                shutil.copyfile(frame, output / "cover.png")
            run_ffmpeg(["-loop", "1", "-framerate", str(FPS), "-i", str(frame), "-t", str(scene["duration"]),
                        "-vf", f"fade=t=in:st=0:d=0.2,fade=t=out:st={scene['duration'] - 0.2}:d=0.2",
                        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
                        "-threads", "2", "-an", str(clip)])
        # All paths here are generated, so ffconcat never receives user-provided strings.
        (work / "clips.txt").write_text("".join(f"file 'clip-{i}.mp4'\n" for i in range(len(job["scenes"]))))
        audio_input = ["-i", job["audio"]] if job.get("audio") else ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
        run_ffmpeg(["-f", "concat", "-safe", "1", "-i", str(work / "clips.txt"), *audio_input,
                    "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-af", "apad",
                    "-t", str(duration), "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
                    "-movflags", "+faststart", str(output / "reel.mp4")])
    info = inspect_video(output / "reel.mp4")
    manifest = {"title": job.get("title", ""), "caption": job.get("caption", ""),
                "audio_source": "file" if job.get("audio") else "silent", "video": "reel.mp4", **info}
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "caption.txt").write_text(job.get("caption", ""), encoding="utf-8")
    return manifest
