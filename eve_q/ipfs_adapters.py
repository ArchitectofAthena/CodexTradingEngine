import json
import mimetypes
import uuid
from dataclasses import dataclass
from typing import Protocol
from urllib import parse, request

DEFAULT_KUBO_API_URL = "http://127.0.0.1:5001"


class IpfsWriter(Protocol):
    def add_and_pin(self, data: bytes) -> str:
        pass

    def cat(self, cid: str) -> bytes:
        pass

    def is_pinned(self, cid: str) -> bool:
        pass


@dataclass(frozen=True)
class KuboHttpIpfsWriter:
    api_url: str = DEFAULT_KUBO_API_URL
    timeout_seconds: int = 10

    def endpoint(self, path: str) -> str:
        return self.api_url.rstrip("/") + path

    def add_and_pin(self, data: bytes) -> str:
        boundary = "----eveqreceipt" + uuid.uuid4().hex
        body = multipart_body(
            boundary=boundary,
            field_name="file",
            filename="receipt.json",
            data=data,
            content_type="application/json",
        )

        url = self.endpoint("/api/v0/add?pin=true&cid-version=1")
        headers = {
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        }

        response = post_bytes(
            url,
            body,
            headers=headers,
            timeout_seconds=self.timeout_seconds,
        )

        payload = json.loads(response.decode("utf-8"))
        cid = payload.get("Hash")

        if not cid:
            raise RuntimeError("Kubo add response did not include Hash")

        return str(cid)

    def cat(self, cid: str) -> bytes:
        query = parse.urlencode({"arg": cid})
        url = self.endpoint(f"/api/v0/cat?{query}")

        return post_bytes(
            url,
            b"",
            headers={},
            timeout_seconds=self.timeout_seconds,
        )

    def is_pinned(self, cid: str) -> bool:
        query = parse.urlencode({"arg": cid, "type": "recursive"})
        url = self.endpoint(f"/api/v0/pin/ls?{query}")

        try:
            response = post_bytes(
                url,
                b"",
                headers={},
                timeout_seconds=self.timeout_seconds,
            )
        except Exception:
            return False

        payload = json.loads(response.decode("utf-8"))
        keys = payload.get("Keys", {})

        return cid in keys


def post_bytes(
    url: str,
    data: bytes,
    headers: dict[str, str],
    timeout_seconds: int,
) -> bytes:
    req = request.Request(
        url,
        data=data,
        headers=headers,
        method="POST",
    )

    with request.urlopen(req, timeout=timeout_seconds) as response:
        return response.read()


def multipart_body(
    boundary: str,
    field_name: str,
    filename: str,
    data: bytes,
    content_type: str | None = None,
) -> bytes:
    guessed_type = mimetypes.guess_type(filename)[0]
    final_type = content_type or guessed_type or "application/octet-stream"

    lines = [
        f"--{boundary}",
        (f'Content-Disposition: form-data; name="{field_name}"; ' f'filename="{filename}"'),
        f"Content-Type: {final_type}",
        "",
    ]

    head = "\r\n".join(lines).encode("utf-8") + b"\r\n"
    tail = f"\r\n--{boundary}--\r\n".encode("utf-8")

    return head + data + tail
