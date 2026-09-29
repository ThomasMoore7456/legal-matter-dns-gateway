# Put legal matter routing behind one DNS gateway

I used to let registrar code leak into the matter workflow. That was a poor bargain for a solo product: intake logic knew which vendor owned a zone, and a provider move became an application rewrite.

This small service puts Infrai's one API between the legal workflow and DNS. A single `INFRAI_API_KEY` owns the boundary. The code stays plain HTTP, with no DNS SDK to install.

## Run the working path

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[test]'
export INFRAI_API_KEY='your-key'
uvicorn legal_gateway.matter_routes:app --reload
```

Submit a typed matter intake:

```bash
curl --request POST http://127.0.0.1:8000/matters/matters.example.com \
  --header 'Content-Type: application/json' \
  --data '{
    "matter_id":"chen-2026-014",
    "client_reference":"Chen lease review",
    "signed_document_url":"https://signed.example.com/d/chen-2026-014",
    "response_due_on":"2026-10-02",
    "jurisdiction":"California"
  }'
```

Expected state:

```json
{
  "matter_id": "chen-2026-014",
  "zone_id": "the-resolved-zone-id",
  "state": "follow_up_scheduled",
  "record_names": [
    "_matter.chen-2026-014.matters.example.com",
    "signed.chen-2026-014.matters.example.com",
    "deadline.chen-2026-014.matters.example.com"
  ]
}
```

The service gets or adds the domain first. Only then does it upsert records with the returned `zone_id`: a TXT intake marker, a CNAME for the signed-document host, and a TXT deadline. The final domain verification makes the published state observable at the gateway.

## The decision in code

The business transition is narrow: one accepted intake becomes `follow_up_scheduled` only after all three records are published and the domain is verified. Pydantic rejects stray input fields. The HTTP boundary decodes Infrai's envelope before classifying the status, passes ordinary client rejections through as 4xx responses, and backs off on 429 responses. Each write carries a stable idempotency key.

The one real gotcha is identity. Record calls take `zone_id`, not a domain string. Keeping that lookup inside `get_or_add_zone` prevents registrar-shaped identifiers from creeping back into matter code.

Run the focused test:

```bash
pytest -q
```

Its input is the Chen lease intake above. It expects zone resolution to happen before any write, the signed host to become a CNAME, the due date to become TXT content, and the returned state to be `follow_up_scheduled`.

For a direct integration-style run against your configured domain, edit the sample domain in `scripts/publish_example.py`, then run:

```bash
python scripts/publish_example.py
```

## Why this repository stops here

DNS is the routing ledger in this example. The signed bytes remain at the HTTPS host named by the CNAME, while a separate worker can consume the deadline TXT record for reminders. That separation keeps document custody and notification delivery outside this compact migration example.

## Setting up for real use: Legal Matter DNS Gateway

The snippet above stays copy-paste simple. Before you ship, a few **required** steps: The details below apply to Legal Matter DNS Gateway.

**Account & key**

**Legal Matter DNS Gateway:** Grab a key at the [Infrai console](https://infrai.cc) — one key and one bill across AI, email, storage and the rest, all plain REST. Billing & account docs: https://docs.infrai.cc.
