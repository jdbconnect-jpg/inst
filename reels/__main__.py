import argparse
import json
from pathlib import Path
import sys

from .instagram import ApiError, InstagramClient, load_receipt, prepare, publish
from .render import inspect_video, render


def main():
    parser = argparse.ArgumentParser(description="인스타그램 릴스 제작·게시 CLI")
    commands = parser.add_subparsers(dest="command", required=True)
    rendering = commands.add_parser("render", help="JSON 대본으로 세로 MP4 만들기")
    rendering.add_argument("job", type=Path)
    rendering.add_argument("--out", type=Path, default=Path("out/demo"))
    check = commands.add_parser("check", help="MP4 코덱·크기·길이 검사")
    check.add_argument("video", type=Path)
    commands.add_parser("account", help="연결된 Instagram 계정 확인")
    upload = commands.add_parser("upload", help="공개 MP4 URL을 Meta 처리 컨테이너에 전달 (게시 안 함)")
    upload.add_argument("--video-url", required=True)
    upload.add_argument("--caption-file", type=Path, required=True)
    upload.add_argument("--receipt", type=Path, default=Path(".state/upload.json"))
    status = commands.add_parser("status", help="Meta 영상 처리 상태 확인")
    status.add_argument("--receipt", type=Path, default=Path(".state/upload.json"))
    status.add_argument("--wait", action="store_true")
    posting = commands.add_parser("publish", help="준비된 릴스를 Instagram에 실제 게시")
    posting.add_argument("--receipt", type=Path, default=Path(".state/upload.json"))
    args = parser.parse_args()
    try:
        if args.command == "render":
            result = render(args.job, args.out)
        elif args.command == "check":
            result = inspect_video(args.video)
        else:
            client = InstagramClient.from_env()
            if args.command == "account":
                result = client.account()
            elif args.command == "upload":
                result = prepare(client, args.video_url, args.caption_file.read_text(encoding="utf-8"), args.receipt)
            elif args.command == "status":
                receipt = load_receipt(args.receipt, client)
                if not receipt.get("container_id"):
                    raise ValueError("컨테이너 생성 응답을 받지 못했습니다. README의 복구 절차를 확인하세요.")
                code = client.wait_ready(receipt["container_id"]) if args.wait else client.status(receipt["container_id"])
                result = {"container_id": receipt["container_id"], "status": code, "local_state": receipt["state"]}
            else:
                result = publish(client, args.receipt)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, ApiError, OSError) as error:
        print(f"오류: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
