from __future__ import annotations

from contextlib import contextmanager
import ipaddress
import json
import os
from pathlib import Path
import re
import time
import urllib.error
import urllib.parse
import urllib.request


class ApiError(RuntimeError):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # Never forward an Authorization header to another host.


def public_video_url(value: str) -> str:
    url = urllib.parse.urlsplit(value)
    if url.scheme != "https" or not url.hostname or url.username or url.password or url.fragment or url.port not in (None, 443):
        raise ValueError("인증 없이 접근 가능한 HTTPS MP4 URL이 필요합니다.")
    host = url.hostname.lower()
    if "." not in host or host.endswith((".localhost", ".local", ".internal")):
        raise ValueError("로컬 주소는 Meta에서 접근할 수 없습니다.")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        if not address.is_global:
            raise ValueError("공개 인터넷 주소가 필요합니다.")
    return value


class InstagramClient:
    def __init__(self, user_id: str, token: str, version: str = "v24.0"):
        if not re.fullmatch(r"[0-9]+", user_id):
            raise ValueError("INSTAGRAM_USER_ID에 Instagram 프로페셔널 계정 ID를 설정하세요.")
        if not token or any(c in token for c in "\r\n"):
            raise ValueError("INSTAGRAM_ACCESS_TOKEN을 환경 설정에 등록하세요.")
        if not re.fullmatch(r"v[0-9]+\.0", version):
            raise ValueError("INSTAGRAM_API_VERSION은 v24.0 같은 형식이어야 합니다.")
        self.user_id, self.token, self.version = user_id, token, version
        self.base = f"https://graph.instagram.com/{version}"
        self.opener = urllib.request.build_opener(NoRedirect())

    @classmethod
    def from_env(cls):
        return cls(os.getenv("INSTAGRAM_USER_ID", ""), os.getenv("INSTAGRAM_ACCESS_TOKEN", ""),
                   os.getenv("INSTAGRAM_API_VERSION", "v24.0"))

    def request(self, method: str, resource: str, values: dict | None = None) -> dict:
        query = urllib.parse.urlencode(values or {})
        url = f"{self.base}/{resource}"
        data = query.encode() if method == "POST" else None
        if method == "GET" and query:
            url += "?" + query
        request = urllib.request.Request(url, data=data, method=method, headers={
            "Authorization": f"Bearer {self.token}", "Content-Type": "application/x-www-form-urlencoded"})
        try:
            with self.opener.open(request, timeout=30) as response:
                result = json.load(response)
        except urllib.error.HTTPError as error:
            # Response messages can echo credentials or signed URLs; report codes only.
            raise ApiError(f"Instagram API HTTP {error.code}. 권한·토큰·계정 설정을 확인하세요.") from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise ApiError("Instagram API 연결 실패. POST 요청은 자동 재시도하지 않습니다.") from None
        except (ValueError, UnicodeError):
            raise ApiError("Instagram API에서 올바르지 않은 JSON 응답을 받았습니다.") from None
        if not isinstance(result, dict) or "error" in result:
            raise ApiError("Instagram API 오류 응답. 계정 권한을 확인하세요.")
        return result

    def account(self):
        return self.request("GET", self.user_id, {"fields": "id,username"})

    def create_container(self, video_url, caption):
        if not isinstance(caption, str) or len(caption) > 2200:
            raise ValueError("캡션은 최대 2200자입니다.")
        result = self.request("POST", f"{self.user_id}/media", {
            "media_type": "REELS", "video_url": public_video_url(video_url),
            "caption": caption, "share_to_feed": "true"})
        return self.require_id(result)

    @staticmethod
    def require_id(result):
        identifier = str(result.get("id", ""))
        if not identifier.isdigit():
            raise ApiError("API 응답에 유효한 ID가 없습니다.")
        return identifier

    def status(self, container_id):
        if not str(container_id).isdigit():
            raise ValueError("유효한 컨테이너 ID가 필요합니다.")
        result = self.request("GET", container_id, {"fields": "status_code"})
        code = result.get("status_code")
        if code not in {"IN_PROGRESS", "FINISHED", "ERROR", "EXPIRED", "PUBLISHED"}:
            raise ApiError("알 수 없는 컨테이너 상태입니다.")
        return code

    def wait_ready(self, container_id, timeout=300, interval=5):
        deadline = time.monotonic() + timeout
        while True:
            code = self.status(container_id)
            if code == "FINISHED":
                return code
            if code != "IN_PROGRESS":
                raise ApiError(f"컨테이너 상태: {code}. 게시할 수 없습니다.")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ApiError("처리 대기시간 초과. 같은 영상을 다시 업로드하지 말고 status로 확인하세요.")
            time.sleep(min(interval, remaining))


def save_receipt(path, receipt):
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


@contextmanager
def receipt_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = path.with_suffix(path.suffix + ".lock")
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise ValueError("이 영수증의 다른 작업이 실행 중입니다. 중단된 작업이면 README 복구 절차를 확인하세요.") from None
    try:
        os.close(descriptor)
        yield
    finally:
        lock.unlink(missing_ok=True)


def load_receipt(path, client):
    receipt = json.loads(path.read_text(encoding="utf-8"))
    if receipt.get("user_id") != client.user_id or receipt.get("api_version") != client.version:
        raise ValueError("계정 또는 API 버전이 업로드 영수증과 다릅니다.")
    return receipt


def prepare(client, url, caption, receipt_path):
    public_video_url(url)
    if len(caption) > 2200:
        raise ValueError("캡션은 최대 2200자입니다.")
    with receipt_lock(receipt_path):
        if receipt_path.exists():
            raise ValueError("영수증이 이미 존재합니다. status로 기존 업로드를 확인하세요.")
        receipt = {"user_id": client.user_id, "api_version": client.version, "state": "creating"}
        # Persist before POST: a lost response must not silently create a duplicate.
        save_receipt(receipt_path, receipt)
        receipt["container_id"] = client.create_container(url, caption)
        receipt["state"] = "created"
        save_receipt(receipt_path, receipt)
        return receipt


def publish(client, receipt_path):
    with receipt_lock(receipt_path):
        receipt = load_receipt(receipt_path, client)
        if receipt["state"] == "published":
            return receipt
        if receipt["state"] != "created":
            raise ValueError("이전 요청의 결과가 불확실합니다. 상태를 확인한 후 수동 복구하세요.")
        status = client.status(receipt["container_id"])
        if status == "PUBLISHED":
            receipt["state"] = "published"
            save_receipt(receipt_path, receipt)
            return receipt
        if status != "FINISHED":
            raise ValueError(f"게시 준비가 완료되지 않았습니다: {status}")
        receipt["state"] = "publishing"
        save_receipt(receipt_path, receipt)
        result = client.request("POST", f"{client.user_id}/media_publish", {"creation_id": receipt["container_id"]})
        receipt.update(state="published", media_id=client.require_id(result))
        save_receipt(receipt_path, receipt)
        return receipt
