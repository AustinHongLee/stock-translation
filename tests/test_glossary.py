from __future__ import annotations

import unittest

from app.glossary.service import glossary_payload, load_glossary


class GlossaryTests(unittest.TestCase):
    def test_glossary_payload_contains_terms_and_aliases(self) -> None:
        entries = load_glossary()
        payload = glossary_payload()

        self.assertGreaterEqual(len(entries), 10)
        self.assertIn("價格位階", payload["aliases"])
        self.assertEqual(payload["aliases"]["最新收盤"], "收盤價")  # type: ignore[index]
        self.assertTrue(any(entry.term == "EPS" for entry in entries))


if __name__ == "__main__":
    unittest.main()

