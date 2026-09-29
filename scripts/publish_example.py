import asyncio
import os
from datetime import date

from legal_gateway.infrai_dns import InfraiDns
from legal_gateway.matter_routes import MatterIntake, publish_matter


async def main() -> None:
    client = InfraiDns(os.environ["INFRAI_API_KEY"])
    try:
        result = await publish_matter(
            "matters.example.com",
            MatterIntake(
                matter_id="chen-2026-014",
                client_reference="Chen lease review",
                signed_document_url="https://signed.example.com/d/chen-2026-014",
                response_due_on=date(2026, 10, 2),
                jurisdiction="California",
            ),
            client,
        )
        print(result.model_dump_json(indent=2))
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())

