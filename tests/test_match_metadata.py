"""Match metadata: an explicit code commit must win over the current HEAD."""

import unittest
from pathlib import Path
from types import SimpleNamespace

from tools import match
from tools.uci_client import parse_option_line


class BookMetadataTests(unittest.TestCase):
    def probe(self, ownbook="false", bookfile="openings/book.bin"):
        options = [parse_option_line(f"option name OwnBook type check default {ownbook}"),
                   parse_option_line(f"option name BookFile type string default {bookfile}")]
        return SimpleNamespace(options={option.name.lower(): option for option in options})

    def test_advertised_defaults_are_recorded(self):
        self.assertEqual(match.book_settings(self.probe(), []),
                         {"opening_book": False, "book_file": "openings/book.bin"})
        self.assertTrue(match.book_settings(self.probe("true"), [])["opening_book"])

    def test_ownbook_and_custom_file_match_the_last_case_insensitive_override(self):
        options = match.parse_option_assignments(["OwnBook=false", "OWNBOOK=true", "BookFile=my books/custom.bin"])
        self.assertEqual(match.book_settings(self.probe(), options),
                         {"opening_book": True, "book_file": "my books/custom.bin"})

    def test_disabling_keeps_the_configured_file_without_claiming_a_book_hit(self):
        options = match.parse_option_assignments(["OwnBook=false"])
        self.assertEqual(match.book_settings(self.probe("true"), options),
                         {"opening_book": False, "book_file": "openings/book.bin"})

    def test_unsupported_options_are_unknown(self):
        self.assertEqual(match.book_settings(SimpleNamespace(options={}), []),
                         {"opening_book": None, "book_file": None})


class GitOverrideTests(unittest.TestCase):
    def test_override_replaces_the_commit_outside_a_repository(self) -> None:
        git = match._git_info(Path("/nonexistent/acemi"), "abc1234")
        self.assertEqual(git["commit"], "abc1234")
        self.assertIsNone(git["dirty"])

    def test_no_override_outside_a_repository_stays_unknown(self) -> None:
        git = match._git_info(Path("/nonexistent/acemi"))
        self.assertIsNone(git["commit"])

    def test_cli_accepts_the_override(self) -> None:
        args = match._parse_args(["--git-commit", "abc1234", "--no-record"])
        self.assertEqual(args.git_commit, "abc1234")


if __name__ == "__main__":
    unittest.main()
