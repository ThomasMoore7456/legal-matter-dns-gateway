from __future__ import annotations

import hashlib
import json
import os
from datetime import date
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from .infrai_dns import InfraiDns, InfraiError


class MatterIntake(BaseModel):
    model_config = ConfigDict(extra="forbid")

    matter_id: str = Field(pattern=r"^[a-z0-9-]+$", min_length=3, max_length=48)
    client_reference: str = Field(min_length=1, max_length=80)
    signed_document_url: HttpUrl
    response_due_on: date
    jurisdiction: str = Field(min_length=2, max_length=40)


class PublishedMatter(BaseModel):
    matter_id: str
    zone_id: str
    state: Literal["follow_up_scheduled"]
    record_names: list[str]


def dns_client() -> InfraiDns:
    api_key = os.environ.get("INFRAI_API_KEY")
    if not api_key:
        raise RuntimeError("INFRAI_API_KEY is required")
    return InfraiDns(api_key)


app = FastAPI(title="Legal matter DNS gateway")


@app.post("/matters/{domain}", response_model=PublishedMatter, status_code=201)
async def publish_matter(
    domain: str,
    intake: MatterIntake,
    client: InfraiDns = Depends(dns_client),
) -> PublishedMatter:
    try:
        zone = await client.get_or_add_zone(domain)
        prefix = f"_matter.{intake.matter_id}"
        intake_name = f"{prefix}.{domain}"
        document_name = f"signed.{intake.matter_id}.{domain}"
        deadline_name = f"deadline.{intake.matter_id}.{domain}"
        intake_content = json.dumps(
            {
                "client_reference": intake.client_reference,
                "jurisdiction": intake.jurisdiction,
            },
            separators=(",", ":"),
            sort_keys=True,
        )
        document_target = intake.signed_document_url.host
        if document_target is None:
            raise HTTPException(status_code=422, detail="Signed document host is required")

        records = [
            ("TXT", intake_name, intake_content),
            ("CNAME", document_name, document_target),
            ("TXT", deadline_name, intake.response_due_on.isoformat()),
        ]
        for record_type, name, content in records:
            digest = hashlib.sha256(f"{zone.zone_id}:{name}:{content}".encode()).hexdigest()
            await client.upsert_record(
                zone.zone_id,
                record_type,
                name,
                content,
                operation_id=f"matter:{intake.matter_id}:{digest}",
            )
        await client.verify_domain(domain)
        return PublishedMatter(
            matter_id=intake.matter_id,
            zone_id=zone.zone_id,
            state="follow_up_scheduled",
            record_names=[name for _, name, _ in records],
        )
    except InfraiError as error:
        status = error.status_code if 400 <= error.status_code < 500 else 502
        raise HTTPException(
            status_code=status,
            detail={"code": error.code, "message": str(error)},
        ) from error

