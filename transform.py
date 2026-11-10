"""Turns Gong API call objects into flat Airtable rows."""

# Airtable long text fields hold up to 100,000 characters.
MAX_TEXT = 95_000

FIELDS = [
    "Call ID",
    "Title",
    "Date",
    "Duration (min)",
    "Direction",
    "Reps",
    "Customers",
    "Customer Emails",
    "Summary",
    "Transcript",
    "Gong URL",
]


def _name(party):
    return party.get("name") or party.get("emailAddress") or "Unknown"


def format_transcript(entry, speakers):
    """Join Gong monologues into 'Speaker: text' lines."""
    lines = []
    for mono in (entry or {}).get("transcript", []):
        speaker = speakers.get(mono.get("speakerId"), "Unknown speaker")
        text = " ".join(
            s.get("text", "").strip() for s in mono.get("sentences", [])
        ).strip()
        if text:
            lines.append(f"{speaker}: {text}")
    out = "\n".join(lines)
    if len(out) > MAX_TEXT:
        out = out[:MAX_TEXT] + "\n[transcript truncated]"
    return out


def call_to_fields(call, transcript_entry=None):
    meta = call.get("metaData") or {}
    parties = call.get("parties") or []
    internal = [p for p in parties if p.get("affiliation") == "Internal"]
    external = [p for p in parties if p.get("affiliation") != "Internal"]
    speakers = {p["speakerId"]: _name(p) for p in parties if p.get("speakerId")}

    fields = {
        "Call ID": str(meta.get("id", "")),
        "Title": meta.get("title"),
        "Date": meta.get("started"),
        "Duration (min)": round((meta.get("duration") or 0) / 60, 1),
        "Direction": meta.get("direction"),
        "Reps": ", ".join(_name(p) for p in internal),
        "Customers": ", ".join(_name(p) for p in external),
        "Customer Emails": ", ".join(
            p["emailAddress"] for p in external if p.get("emailAddress")
        ),
        "Summary": (call.get("content") or {}).get("brief"),
        "Transcript": format_transcript(transcript_entry, speakers)
        if transcript_entry
        else None,
        "Gong URL": meta.get("url"),
    }
    # Empty values are left out so they never overwrite data already in Airtable.
    return {k: v for k, v in fields.items() if v not in (None, "")}
