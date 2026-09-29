from datetime import date

import pytest

from legal_gateway.infrai_dns import Zone
from legal_gateway.matter_routes import MatterIntake, publish_matter


class RecordingDns:
    def __init__(self) -> None:
        self.zone_resolved = False
        self.records: list[tuple[str, str, str, str]] = []
        self.verified_domain: str | None = None

    async def get_or_add_zone(self, domain: str) -> Zone:
        self.zone_resolved = True
        return Zone(zone_id="zone_legal_17", domain=domain)

    async def upsert_record(
        self,
        zone_id: str,
        record_type: str,
        name: str,
        content: str,
        operation_id: str,
        ttl: int = 300,
    ) -> None:
        assert self.zone_resolved
        assert zone_id == "zone_legal_17"
        assert operation_id.startswith("matter:chen-2026-014:")
        self.records.append((zone_id, record_type, name, content))

    async def verify_domain(self, domain: str) -> None:
        self.verified_domain = domain


@pytest.mark.asyncio
async def test_intake_publishes_delivery_and_deadline_after_zone_resolution() -> None:
    dns = RecordingDns()
    result = await publish_matter(
        "matters.example.com",
        MatterIntake(
            matter_id="chen-2026-014",
            client_reference="Chen lease review",
            signed_document_url="https://signed.example.com/d/chen-2026-014",
            response_due_on=date(2026, 10, 2),
            jurisdiction="California",
        ),
        dns,  # type: ignore[arg-type]
    )

    assert result.state == "follow_up_scheduled"
    assert [(kind, name, content) for _, kind, name, content in dns.records] == [
        (
            "TXT",
            "_matter.chen-2026-014.matters.example.com",
            '{"client_reference":"Chen lease review","jurisdiction":"California"}',
        ),
        ("CNAME", "signed.chen-2026-014.matters.example.com", "signed.example.com"),
        ("TXT", "deadline.chen-2026-014.matters.example.com", "2026-10-02"),
    ]
    assert dns.verified_domain == "matters.example.com"

