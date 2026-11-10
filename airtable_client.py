"""Minimal Airtable client: creates the Calls table and upserts records by a unique key."""

import json
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.airtable.com/v0"

# Table schema used by setup (the first field becomes the primary field).
CALLS_FIELDS = [
    {"name": "Call ID", "type": "singleLineText"},
    {"name": "Title", "type": "singleLineText"},
    {"name": "Date", "type": "dateTime", "options": {
        "dateFormat": {"name": "iso"},
        "timeFormat": {"name": "24hour"},
        "timeZone": "utc",
    }},
    {"name": "Duration (min)", "type": "number", "options": {"precision": 1}},
    {"name": "Direction", "type": "singleSelect", "options": {"choices": [
        {"name": "Inbound"}, {"name": "Outbound"}, {"name": "Conference"}, {"name": "Unknown"},
    ]}},
    {"name": "Reps", "type": "singleLineText"},
    {"name": "Customers", "type": "singleLineText"},
    {"name": "Customer Emails", "type": "multilineText"},
    {"name": "Summary", "type": "multilineText"},
    {"name": "Transcript", "type": "multilineText"},
    {"name": "Gong URL", "type": "url"},
]


class AirtableError(Exception):
    pass


class AirtableClient:
    BATCH_SIZE = 10  # Airtable accepts at most 10 records per request

    def __init__(self, token, base_id, table):
        self.base_id = base_id
        self.table = table
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    def _request(self, method, url, body=None, retries=5):
        data = json.dumps(body).encode() if body is not None else None
        for attempt in range(retries):
            req = urllib.request.Request(url, data=data, headers=self.headers, method=method)
            try:
                with urllib.request.urlopen(req, timeout=60) as resp:
                    return json.loads(resp.read())
            except urllib.error.HTTPError as e:
                if e.code == 429 and attempt < retries - 1:
                    time.sleep(30)  # Airtable asks clients to wait 30 s after a 429
                    continue
                raise AirtableError(
                    f"Airtable API error {e.code}: {e.read().decode(errors='replace')}"
                ) from None
        raise AirtableError("rate limit: too many retries")

    def ensure_table(self):
        """Create the table with CALLS_FIELDS unless a table with that name exists.

        Returns True if it was created. Needs schema.bases:read and schema.bases:write scopes.
        """
        meta_url = f"{API}/meta/bases/{self.base_id}/tables"
        tables = self._request("GET", meta_url).get("tables", [])
        if any(t.get("name") == self.table for t in tables):
            return False
        self._request("POST", meta_url, {"name": self.table, "fields": CALLS_FIELDS})
        return True

    def upsert(self, rows, key_field="Call ID"):
        """Create new records or update existing ones matched by key_field.

        Running the sync twice never creates duplicates.
        Returns (created_count, updated_count).
        """
        url = f"{API}/{self.base_id}/{urllib.parse.quote(self.table, safe='')}"
        created = updated = 0
        for i in range(0, len(rows), self.BATCH_SIZE):
            batch = rows[i:i + self.BATCH_SIZE]
            body = {
                "performUpsert": {"fieldsToMergeOn": [key_field]},
                "records": [{"fields": fields} for fields in batch],
                "typecast": True,
            }
            resp = self._request("PATCH", url, body)
            created += len(resp.get("createdRecords", []))
            updated += len(resp.get("updatedRecords", []))
            time.sleep(0.25)  # stay under 5 requests per second
        return created, updated
