import unittest
from unittest.mock import patch

import brd_parser


class TestParseBrdRouting(unittest.TestCase):
    def test_routes_pdf_extension(self):
        with patch("brd_parser.parse_pdf", return_value="pdf text") as parser:
            result = brd_parser.parse_brd("sample.PDF", b"bytes")
        self.assertEqual(result, "pdf text")
        parser.assert_called_once_with(b"bytes")

    def test_routes_doc_extensions(self):
        with patch("brd_parser.parse_docx", return_value="doc text") as parser:
            result = brd_parser.parse_brd("sample.docx", b"bytes")
        self.assertEqual(result, "doc text")
        parser.assert_called_once_with(b"bytes")

        with patch("brd_parser.parse_docx", return_value="doc text") as parser:
            result = brd_parser.parse_brd("sample.doc", b"bytes")
        self.assertEqual(result, "doc text")
        parser.assert_called_once_with(b"bytes")

    def test_routes_ppt_extensions(self):
        with patch("brd_parser.parse_pptx", return_value="ppt text") as parser:
            result = brd_parser.parse_brd("sample.pptx", b"bytes")
        self.assertEqual(result, "ppt text")
        parser.assert_called_once_with(b"bytes")

        with patch("brd_parser.parse_pptx", return_value="ppt text") as parser:
            result = brd_parser.parse_brd("sample.ppt", b"bytes")
        self.assertEqual(result, "ppt text")
        parser.assert_called_once_with(b"bytes")

    def test_rejects_unsupported_extension(self):
        with self.assertRaises(ValueError) as ctx:
            brd_parser.parse_brd("sample.txt", b"bytes")
        self.assertIn("Unsupported file type", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
