"""Service-role adapter for private Supabase Storage buckets."""
from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import time
from http.client import IncompleteRead
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from backend.storage.layout import REQUIRED_BUCKETS, validate_bucket_path

# Supabase Storage HTTP calls over a long run intermittently hit transient TCP
# resets (e.g. WinError 10054 "connection forcibly closed"). These succeed on a
# retry, so transient network errors are retried with exponential backoff.
_STORAGE_MAX_ATTEMPTS = 4
_STORAGE_BASE_DELAY = 0.5


class SupabaseStorageError(RuntimeError):
    pass


class SupabaseStorageAdapter:
    def __init__(self, url: str | None = None, service_role_key: str | None = None) -> None:
        project_id = os.getenv("SUPABASE_PROJECT_ID", "")
        self.url = (url or os.getenv("SUPABASE_URL") or (f"https://{project_id}.supabase.co" if project_id else "")).rstrip("/")
        self.service_role_key = (
            service_role_key
            or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
            or os.getenv("SUPABASE_SECRET_KEY")
            or ""
        )
        if not self.url or not self.service_role_key:
            raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required")

    def _request(
        self,
        method: str,
        endpoint: str,
        *,
        body: bytes | None = None,
        content_type: str = "application/json",
        extra_headers: dict[str, str] | None = None,
        expected: tuple[int, ...] = (200,),
    ) -> bytes:
        headers = {
            "Authorization": f"Bearer {self.service_role_key}",
            "apikey": self.service_role_key,
            "Content-Type": content_type,
        }
        headers.update(extra_headers or {})
        request = Request(f"{self.url}/storage/v1/{endpoint}", data=body, headers=headers, method=method)
        last_exc: Exception | None = None
        for attempt in range(_STORAGE_MAX_ATTEMPTS):
            try:
                with urlopen(request, timeout=120) as response:
                    payload = response.read()
                    if response.status not in expected:
                        raise SupabaseStorageError(f"Unexpected Supabase Storage status {response.status}")
                    return payload
            except HTTPError as exc:
                # Real HTTP error response (4xx/5xx) — not a transient reset; do not retry.
                detail = exc.read().decode("utf-8", errors="replace")
                raise SupabaseStorageError(f"Supabase Storage {method} {endpoint} failed: {exc.code} {detail}") from exc
            except (URLError, ConnectionError, TimeoutError, OSError, IncompleteRead) as exc:
                # Transient network reset (e.g. WinError 10054, dropped TLS) — retry with backoff.
                last_exc = exc
                if attempt == _STORAGE_MAX_ATTEMPTS - 1:
                    raise SupabaseStorageError(
                        f"Supabase Storage {method} {endpoint} failed after {_STORAGE_MAX_ATTEMPTS} attempts: {exc}"
                    ) from exc
                time.sleep(_STORAGE_BASE_DELAY * (2 ** attempt))
        raise SupabaseStorageError(  # pragma: no cover - loop returns or raises above
            f"Supabase Storage {method} {endpoint} failed: {last_exc}"
        )

    @staticmethod
    def checksum_file(local_path: str | Path) -> str:
        digest = hashlib.sha256()
        with Path(local_path).open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def upload_file(
        self,
        bucket: str,
        path: str,
        local_path: str | Path,
        content_type: str | None,
        *,
        upsert: bool = False,
    ) -> dict[str, Any]:
        validate_bucket_path(bucket, path)
        source = Path(local_path)
        media_type = content_type or mimetypes.guess_type(source.name)[0] or "application/octet-stream"
        payload = self._request(
            "POST",
            f"object/{quote(bucket)}/{quote(path, safe='/')}",
            body=source.read_bytes(),
            content_type=media_type,
            extra_headers={"x-upsert": "true" if upsert else "false"},
            expected=(200, 201),
        )
        return json.loads(payload or b"{}")

    def download_file(self, bucket: str, path: str, destination: str | Path) -> Path:
        validate_bucket_path(bucket, path)
        target = Path(destination)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(self._request("GET", f"object/{quote(bucket)}/{quote(path, safe='/')}"))
        return target

    def upload_json(
        self,
        bucket: str,
        path: str,
        payload: Any,
        *,
        upsert: bool = False,
    ) -> dict[str, Any]:
        validate_bucket_path(bucket, path)
        body = json.dumps(payload, indent=2, ensure_ascii=False, default=str).encode("utf-8")
        result = self._request(
            "POST",
            f"object/{quote(bucket)}/{quote(path, safe='/')}",
            body=body,
            content_type="application/json",
            extra_headers={"x-upsert": "true" if upsert else "false"},
            expected=(200, 201),
        )
        return json.loads(result or b"{}")

    def download_json(self, bucket: str, path: str) -> Any:
        validate_bucket_path(bucket, path)
        return json.loads(self._request("GET", f"object/{quote(bucket)}/{quote(path, safe='/')}"))

    def download_bytes(self, bucket: str, path: str) -> bytes:
        validate_bucket_path(bucket, path)
        return self._request("GET", f"object/{quote(bucket)}/{quote(path, safe='/')}")

    def exists(self, bucket: str, path: str) -> bool:
        validate_bucket_path(bucket, path)
        try:
            self._request("GET", f"object/{quote(bucket)}/{quote(path, safe='/')}", expected=(200,))
            return True
        except SupabaseStorageError as exc:
            if "404" in str(exc):
                return False
            raise

    def signed_url(self, bucket: str, path: str, expires_in: int) -> str:
        validate_bucket_path(bucket, path)
        if bucket != "exports":
            raise ValueError("User-facing signed URLs may only be created for the exports bucket")
        payload = self._request(
            "POST",
            f"object/sign/{quote(bucket)}/{quote(path, safe='/')}",
            body=json.dumps({"expiresIn": expires_in}).encode(),
        )
        signed_path = json.loads(payload)["signedURL"]
        return signed_path if signed_path.startswith("http") else f"{self.url}/storage/v1{signed_path}"

    def validate_checksum(self, bucket: str, path: str, expected_checksum: str) -> bool:
        validate_bucket_path(bucket, path)
        digest = hashlib.sha256(self._request("GET", f"object/{quote(bucket)}/{quote(path, safe='/')}")).hexdigest()
        return digest == expected_checksum

    def list_buckets(self) -> list[dict[str, Any]]:
        return json.loads(self._request("GET", "bucket"))

    def create_private_bucket(self, bucket: str) -> None:
        if bucket not in REQUIRED_BUCKETS:
            raise ValueError(f"Unsupported storage bucket: {bucket}")
        self._request(
            "POST",
            "bucket",
            body=json.dumps({"id": bucket, "name": bucket, "public": False}).encode(),
            expected=(200, 201),
        )

    def list_objects(self, bucket: str, prefix: str = "", limit: int = 1000, offset: int = 0) -> list[dict[str, Any]]:
        if bucket not in REQUIRED_BUCKETS:
            raise ValueError(f"Unsupported storage bucket: {bucket}")
        return json.loads(
            self._request(
                "POST",
                f"object/list/{quote(bucket)}",
                body=json.dumps({"prefix": prefix, "limit": limit, "offset": offset}).encode(),
            )
        )
