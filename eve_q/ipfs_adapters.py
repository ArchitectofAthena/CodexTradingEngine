import ipaddress
import json
import mimetypes
import re
import uuid
from dataclasses import dataclass
from typing import Protocol
from urllib import parse, request

DEFAULT_KUBO_API_URL = "http://127.0.0.1:5001"
DEFAULT_MAX_ADD_BYTES = 16 * 1024 * 1024
DEFAULT_MAX_RESPONSE_BYTES = 32 * 1024 * 1024
DEFAULT_MAX_JSON_RESPONSE_BYTES = 1024 * 1024
_CIDV1_BASE32 = re.compile(r"^b[a-z2-7]{20,}$")


class IpfsWriter(Protocol):
    def add_and_pin(self, data: bytes) -> str:
        pass

    def cat(self, cid: str) -> bytes:
        pass

    def is_pinned(self, cid: str) -> bool:
        pass


class _NoRedirectHandler(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RuntimeError("Kubo HTTP redirects are forbidden")


_NO_REDIRECT_OPENER = request.build_opener(
    request.ProxyHandler({}),
    _NoRedirectHandler(),
)


def _open_url(req: request.Request, timeout: float):
    return _NO_REDIRECT_OPENER.open(req, timeout=timeout)


def validate_cid(cid: str) -> str:
    candidate = cid.strip()
    if not _CIDV1_BASE32.fullmatch(candidate):
        raise ValueError("expected a CIDv1 base32 identifier")
    return candidate


def _is_loopback_host(host: str) -> bool:
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def validate_kubo_api_url(api_url: str, *, allow_remote: bool = False) -> str:
    parsed = parse.urlsplit(api_url)
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"}:
        raise ValueError("Kubo API URL must use http or https")
    if not parsed.hostname:
        raise ValueError("Kubo API URL must include a hostname")
    if parsed.username or parsed.password:
        raise ValueError("Kubo API URL must not contain credentials")
    if parsed.query or parsed.fragment:
        raise ValueError("Kubo API URL must not contain query or fragment data")
    if parsed.path not in {"", "/"}:
        raise ValueError("Kubo API URL must not contain a base path")
    try:
        parsed.port
    except ValueError as exc:
        raise ValueError("Kubo API URL contains an invalid port") from exc

    loopback = _is_loopback_host(parsed.hostname)
    if not loopback and not allow_remote:
        raise ValueError("Kubo API URL must be loopback unless allow_remote=True")
    if not loopback and scheme != "https":
        raise ValueError("remote Kubo API URLs must use https")

    return api_url.rstrip("/")


def validate_kubo_request_url(url: str, *, allow_remote: bool = False) -> str:
    parsed = parse.urlsplit(url)
    base = parse.urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))
    validate_kubo_api_url(base, allow_remote=allow_remote)
    if not parsed.path.startswith("/api/v0/"):
        raise ValueError("Kubo request path must remain under /api/v0/")
    if parsed.fragment:
        raise ValueError("Kubo request URL must not contain a fragment")
    return url


@dataclass(frozen=True)
class KuboHttpIpfsWriter:
    api_url: str = DEFAULT_KUBO_API_URL
    timeout_seconds: float = 10.0
    max_add_bytes: int = DEFAULT_MAX_ADD_BYTES
    max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES
    max_json_response_bytes: int = DEFAULT_MAX_JSON_RESPONSE_BYTES
    allow_remote: bool = False

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if self.max_add_bytes <= 0:
            raise ValueError("max_add_bytes must be positive")
        if self.max_response_bytes <= 0:
            raise ValueError("max_response_bytes must be positive")
        if self.max_json_response_bytes <= 0:
            raise ValueError("max_json_response_bytes must be positive")
        validate_kubo_api_url(self.api_url, allow_remote=self.allow_remote)

    def endpoint(self, path: str) -> str:
        if not path.startswith("/api/v0/"):
            raise ValueError("Kubo endpoint path must remain under /api/v0/")
        base = validate_kubo_api_url(self.api_url, allow_remote=self.allow_remote)
        return base + path

    def add_and_pin(self, data: bytes) -> str:
        if not isinstance(data, bytes):
            raise TypeError("IPFS payload must be bytes")
        if len(data) > self.max_add_bytes:
            raise ValueError(
                f"IPFS payload exceeds max_add_bytes={self.max_add_bytes}"
            )

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
            max_response_bytes=self.max_json_response_bytes,
            allow_remote=self.allow_remote,
        )

        payload = json.loads(response.decode("utf-8"))
        if not isinstance(payload, dict):
            raise RuntimeError("Kubo add response must be a JSON object")
        cid = payload.get("Hash")

        if not cid:
            raise RuntimeError("Kubo add response did not include Hash")

        return validate_cid(str(cid))

    def cat(self, cid: str) -> bytes:
        validated = validate_cid(cid)
        query = parse.urlencode({"arg": validated})
        url = self.endpoint(f"/api/v0/cat?{query}")

        return post_bytes(
            url,
            b"",
            headers={},
            timeout_seconds=self.timeout_seconds,
            max_response_bytes=self.max_response_bytes,
            allow_remote=self.allow_remote,
        )

    def is_pinned(self, cid: str) -> bool:
        validated = validate_cid(cid)
        query = parse.urlencode({"arg": validated, "type": "recursive"})
        url = self.endpoint(f"/api/v0/pin/ls?{query}")

        try:
            response = post_bytes(
                url,
                b"",
                headers={},
                timeout_seconds=self.timeout_seconds,
                max_response_bytes=self.max_json_response_bytes,
                allow_remote=self.allow_remote,
            )
            payload = json.loads(response.decode("utf-8"))
        except (OSError, UnicodeDecodeError, ValueError, RuntimeError):
            return False

        if not isinstance(payload, dict):
            return False
        keys = payload.get("Keys", {})
        return isinstance(keys, dict) and validated in keys


def post_bytes(
    url: str,
    data: bytes,
    headers: dict[str, str],
    timeout_seconds: float,
    max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
    *,
    allow_remote: bool = False,
) -> bytes:
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    if max_response_bytes <= 0:
        raise ValueError("max_response_bytes must be positive")
    validate_kubo_request_url(url, allow_remote=allow_remote)

    req = request.Request(
        url,
        data=data,
        headers=headers,
        method="POST",
    )

    with _open_url(req, timeout_seconds) as response:
        content_length = response.headers.get("Content-Length")
        if content_length is not None and int(content_length) > max_response_bytes:
            raise ValueError(
                f"Kubo response exceeds max_response_bytes={max_response_bytes}"
            )
        payload = response.read(max_response_bytes + 1)

    if len(payload) > max_response_bytes:
        raise ValueError(
            f"Kubo response exceeds max_response_bytes={max_response_bytes}"
        )
    return payload


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
        (
            f'Content-Disposition: form-data; name="{field_name}"; '
            f'filename="{filename}"'
        ),
        f"Content-Type: {final_type}",
        "",
    ]

    head = "\r\n".join(lines).encode("utf-8") + b"\r\n"
    tail = f"\r\n--{boundary}--\r\n".encode("utf-8")

    return head + data + tail
