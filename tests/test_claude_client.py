import unittest

from claude_client import ApproachNoteSession


class TestClaudeJsonParsing(unittest.TestCase):
    def setUp(self):
        self.session = ApproachNoteSession.__new__(ApproachNoteSession)

    def test_parses_plain_json(self):
        raw = '{"background": "x"}'
        result = self.session._parse_json(raw)
        self.assertEqual(result["background"], "x")

    def test_parses_fenced_json(self):
        raw = """```json
        {"requirement": "abc"}
        ```"""
        result = self.session._parse_json(raw)
        self.assertEqual(result["requirement"], "abc")

    def test_raises_when_json_missing(self):
        with self.assertRaises(ValueError) as ctx:
            self.session._parse_json("No JSON here")
        self.assertIn("No JSON object found", str(ctx.exception))

    def test_raises_when_json_malformed(self):
        with self.assertRaises(ValueError) as ctx:
            self.session._parse_json('{"background": "x",}')
        self.assertIn("malformed JSON", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
