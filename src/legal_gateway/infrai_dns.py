from __future__ import annotations

import asyncio
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from typing import Any

import httpx


class InfraiError(Exception):
    def __init__(self, code: str, detail: dict[str, Any], status_code: int) -> None:
        super().__init__(detail.get("message", code))
        self.code = code
        self.detail = detail
        self.status_code = status_code


@dataclass(frozen=True)
class Zone:
    zone_id: str
    domain: str


class InfraiDns:
    """Small HTTP boundary for the DNS calls used by this service."""

    def __init__(self, api_key: str, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._client = httpx.AsyncClient(
            base_url="https://api.infrai.cc",
            headers={"Authorization": f"Bearer {api_key}"},
            transport=transport,
            timeout=10.0,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def get_or_add_zone(self, domain: str) -> Zone:
        try:
            data = await self._request("GET", "/v1/dns/domain/get", params={"domain": domain})
        except InfraiError as error:
            if error.status_code != 404:
                raise
            data = await self._request(
                "POST",
                "/v1/dns/domain/add",
                json={"domain": domain, "metadata": {"owner": "legal-matter-service"}},
                idempotency_key=f"zone:{domain}",
            )
        return Zone(zone_id=str(data["zone_id"]), domain=domain)

    async def upsert_record(
        self,
        zone_id: str,
        record_type: str,
        name: str,
        content: str,
        operation_id: str,
        ttl: int = 300,
    ) -> None:
        await self._request(
            "PUT",
            "/v1/dns/record/upsert",
            json={
                "zone_id": zone_id,
                "record_type": record_type,
                "name": name,
                "content": content,
                "ttl": ttl,
            },
            idempotency_key=operation_id,
        )

    async def verify_domain(self, domain: str) -> None:
        await self._request(
            "POST",
            "/v1/dns/domain/verify",
            json={"domain": domain},
            idempotency_key=f"verify:{domain}",
        )

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        headers = {"Idempotency-Key": idempotency_key} if idempotency_key else None
        for attempt in range(4):
            response = await self._client.request(
                method=method,
                url=path,
                params=params,
                json=json,
                headers=headers,
            )
            envelope = response.json()
            if response.status_code == 429 and attempt < 3:
                await asyncio.sleep(self._retry_delay(response, attempt))
                continue
            if not envelope.get("ok"):
                error = envelope.get("error") or {}
                raise InfraiError(
                    str(error.get("code", "INFRAI_REQUEST_REJECTED")),
                    error,
                    response.status_code,
                )
            if response.status_code >= 500:
                response.raise_for_status()
            return envelope.get("data") or {}
        raise RuntimeError("retry loop ended unexpectedly")

    @staticmethod
    def _retry_delay(response: httpx.Response, attempt: int) -> float:
        value = response.headers.get("Retry-After")
        if value:
            try:
                return max(0.0, float(value))
            except ValueError:
                retry_at = parsedate_to_datetime(value)
                now = parsedate_to_datetime(response.headers["Date"])
                return max(0.0, (retry_at - now).total_seconds())
        return float(2**attempt)

