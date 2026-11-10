"""Read-only Gong API client (plus a mock client for demos without API access)."""

import base64
import json
import time
import urllib.error
import urllib.request
from pathlib import Path


class GongError(Exception):
    def __init__(self, status, message):
        super().__init__(f"Gong API error {status}: {message}")
        self.status = status


def _chunks(items, size):
    for i in range(0, len(items), size):
        yield items[i:i + size]


class GongClient:
    """Uses two endpoints: POST /v2/calls/extensive and POST /v2/calls/transcript."""

    def __init__(self, access_key, secret, base_url="https://api.gong.io"):
        token = base64.b64encode(f"{access_key}:{secret}".encode()).decode()
        self.headers = {
            "Authorization": f"Basic {token}",
            "Content-Type": "application/json",
        }
        self.base_url = base_url.rstrip("/")

    def _post(self, path, body, retries=5):
        data = json.dumps(body).encode()
        for attempt in range(retries):
            req = urllib.request.Request(
                self.base_url + path, data=data, headers=self.headers, method="POST"
            )
            try:
                with urllib.request.urlopen(req, timeout=60) as resp:
                    return json.loads(resp.read())
            except urllib.error.HTTPError as e:
                if e.code == 429 and attempt < retries - 1:
                    # Gong limits requests per second; wait as long as it asks.
                    time.sleep(int(e.headers.get("Retry-After", "2")))
                    continue
                raise GongError(e.code, e.read().decode(errors="replace")) from None
        raise GongError(429, "rate limit: too many retries")

    def iter_calls(self, from_dt, to_dt):
        """Yield calls (metadata, parties, brief) between two ISO-8601 datetimes."""
        cursor = None
        while True:
            body = {
                "filter": {"fromDateTime": from_dt, "toDateTime": to_dt},
                "contentSelector": {
                    "exposedFields": {"parties": True, "content": {"brief": True}}
                },
            }
            if cursor:
                body["cursor"] = cursor
            try:
                data = self._post("/v2/calls/extensive", body)
            except GongError as e:
                if e.status == 404:  # Gong answers 404 when no calls match
                    return
                raise
            yield from data.get("calls", [])
            cursor = (data.get("records") or {}).get("cursor")
            if not cursor:
                return

    def get_transcripts(self, call_ids):
        """Return {call_id: transcript_entry}."""
        result = {}
        for chunk in _chunks(list(call_ids), 100):
            cursor = None
            while True:
                body = {"filter": {"callIds": chunk}}
                if cursor:
                    body["cursor"] = cursor
                data = self._post("/v2/calls/transcript", body)
                for entry in data.get("callTranscripts", []):
                    result[str(entry["callId"])] = entry
                cursor = (data.get("records") or {}).get("cursor")
                if not cursor:
                    break
        return result


class MockGongClient:
    """Serves sample responses from sample_data/ in the same shape as the real API."""

    def __init__(self, data_dir=None):
        self.data_dir = Path(data_dir or Path(__file__).parent / "sample_data")

    def _load(self, name):
        return json.loads((self.data_dir / name).read_text(encoding="utf-8"))

    def iter_calls(self, from_dt=None, to_dt=None):
        # Sample data ignores the date range so the demo always has calls.
        yield from self._load("calls_extensive.json").get("calls", [])

    def get_transcripts(self, call_ids):
        wanted = {str(c) for c in call_ids}
        entries = self._load("transcripts.json").get("callTranscripts", [])
        return {str(e["callId"]): e for e in entries if str(e["callId"]) in wanted}
