"""Match metadata: an explicit code commit must win over the current HEAD."""

import unittest
from pathlib import Path

from tools import match


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
