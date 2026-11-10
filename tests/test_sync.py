import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gong_client import MockGongClient  # noqa: E402
from transform import MAX_TEXT, call_to_fields, format_transcript  # noqa: E402


class TransformTests(unittest.TestCase):
    def setUp(self):
        gong = MockGongClient()
        self.calls = list(gong.iter_calls())
        self.transcripts = gong.get_transcripts(c["metaData"]["id"] for c in self.calls)

    def test_basic_fields(self):
        call = self.calls[0]
        row = call_to_fields(call, self.transcripts[call["metaData"]["id"]])
        self.assertEqual(row["Call ID"], "7782342274025937895")
        self.assertEqual(row["Duration (min)"], 31.0)
        self.assertEqual(row["Reps"], "Anna Kowalska")
        self.assertEqual(row["Customers"], "James Carter")
        self.assertEqual(row["Customer Emails"], "james.carter@northwind.example")
        self.assertTrue(row["Transcript"].startswith("Anna Kowalska: Thanks for joining"))

    def test_multiple_customers(self):
        row = call_to_fields(self.calls[1])
        self.assertEqual(row["Customers"], "Sara Lee, Tom Reed")
        self.assertNotIn("Transcript", row)  # no transcript passed -> field left out

    def test_missing_data_does_not_crash(self):
        row = call_to_fields({"metaData": {"id": 42}})
        self.assertEqual(row, {"Call ID": "42", "Duration (min)": 0.0})

    def test_long_transcript_is_truncated(self):
        entry = {"transcript": [{"speakerId": "s1", "sentences": [{"text": "x" * (MAX_TEXT + 500)}]}]}
        out = format_transcript(entry, {"s1": "A"})
        self.assertTrue(out.endswith("[transcript truncated]"))
        self.assertLess(len(out), 100_000)


if __name__ == "__main__":
    unittest.main()
