from __future__ import annotations

import json
import httpx
import pytest

from claros_sdk import ClarOSClient


@pytest.mark.asyncio
async def test_storage_endpoints() -> None:
    file_id = "11111111-2222-3333-4444-555555555555"
    tenant_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

    asset_payload = {
        "id": file_id,
        "tenant_id": tenant_id,
        "category": "data",
        "file_name": "report.csv",
        "content_type": "text/csv",
        "file_size_bytes": 11,
        "bucket_name": "claros-assets",
        "file_key": f"{tenant_id}/data/{file_id}/report.csv",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.method == "POST" and path == "/api/v1/platform/storage/upload":
            assert request.headers.get("X-Tenant-ID") == tenant_id
            return httpx.Response(201, json={"payload": asset_payload})

        if request.method == "GET" and path == "/api/v1/platform/storage/files":
            assert request.url.params.get("category") == "data"
            return httpx.Response(
                200,
                json={
                    "payload": [asset_payload],
                    "meta": {"total": 1, "has_next": False, "page": 1, "limit": 20},
                },
            )

        if request.method == "GET" and path == f"/api/v1/platform/storage/files/{file_id}/metadata":
            return httpx.Response(200, json={"payload": asset_payload})

        if request.method == "GET" and path == f"/api/v1/platform/storage/files/{file_id}":
            if request.url.params.get("presign") == "true":
                return httpx.Response(
                    200,
                    json={
                        "payload": {
                            "id": file_id,
                            "download_url": "https://s3.inductiv.dev/claros-assets/key?sig=123",
                            "expires_in": 900,
                        }
                    },
                )
            return httpx.Response(200, content=b"hello,world")

        if request.method == "GET" and path == f"/api/v1/platform/storage/files/{file_id}/stream":
            if request.headers.get("Range") == "bytes=0-4":
                return httpx.Response(
                    206,
                    content=b"hello",
                    headers={"Content-Range": "bytes 0-4/11"},
                )
            return httpx.Response(200, content=b"hello,world")

        if request.method == "DELETE" and path == f"/api/v1/platform/storage/files/{file_id}":
            return httpx.Response(200, json={"message": "File deleted successfully"})

        return httpx.Response(404, text=f"Unhandled {request.method} {path}")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = ClarOSClient(
            base_url="https://api.claros.ai",
            httpx_client=http_client,
            tenant_id=tenant_id,
        )

        uploaded = await client.storage.upload(
            b"hello,world", file_name="report.csv", category="data"
        )
        assert uploaded.id == file_id
        assert uploaded.file_name == "report.csv"

        listed = await client.storage.list_files(category="data")
        assert listed.meta.total == 1
        assert len(listed.items) == 1
        assert listed.items[0].id == file_id

        meta = await client.storage.get_metadata(file_id)
        assert meta.file_key.endswith("report.csv")

        presigned = await client.storage.get_presigned_url(file_id)
        assert presigned.download_url.startswith("https://s3.inductiv.dev/")
        assert presigned.expires_in == 900

        downloaded = await client.storage.download(file_id)
        assert downloaded == b"hello,world"

        chunks = [
            chunk
            async for chunk in client.storage.stream(file_id, range_header="bytes=0-4")
        ]
        assert b"".join(chunks) == b"hello"

        deleted = await client.storage.delete(file_id)
        assert deleted is True
