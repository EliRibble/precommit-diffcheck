"Test module for precommit_diffcheck"
import contextlib
import subprocess
import unittest
from unittest import mock

from nose2.tools import params # type: ignore
from unidiff import PatchSet # type: ignore
import precommit_diffcheck


@contextlib.contextmanager
def set_git_output(output: str):
	"Set the output from git subprocess calls."
	with mock.patch("subprocess.check_output", return_value=output):
		yield


class TestHasStagedChanges(unittest.TestCase):
	"Test has_staged_changes function."

	@params("M", "A", "D")
	def test_no_staged_changes(self, status: str) -> None:
		"Can we detect when we have changes, but not staged changes?"
		output = " {} test.py\n?? test2.py".format(status)
		with set_git_output(output):
			self.assertFalse(precommit_diffcheck.has_staged_changes())
			self.assertTrue(precommit_diffcheck.has_unstaged_changes())

	@params("M", "A", "D")
	def test_has_staged_changes(self, status: str) -> None:
		"Can we detect when we have staged changes?"
		output = "{}  test.py\n?? test2.py".format(status)
		with set_git_output(output):
			self.assertTrue(precommit_diffcheck.has_staged_changes())
			self.assertFalse(precommit_diffcheck.has_unstaged_changes())

	@params("M", "A", "D")
	def test_has_both_changes(self, status: str) -> None:
		"Can we detect when we have both staged and unstaged changes?"
		output = "{status}  test.py\n {status} test2.py".format(status=status)
		with set_git_output(output):
			self.assertTrue(precommit_diffcheck.has_staged_changes())
			self.assertTrue(precommit_diffcheck.has_unstaged_changes())

class TestGitStatus(unittest.TestCase):
	"Test get_git_status function."
	def test_get_git_status(self) -> None:
		"Can get get git status for a bunch of lines?"
		output = "\n".join((
			"M  test.py",
			" A test2.py",
			"D  test3.py",
			"?? test4.py",
		))
		with set_git_output(output):
			result = precommit_diffcheck.get_git_status()
		expected = [
			precommit_diffcheck.GitStatusEntry(
				filename="test.py",
				is_staged=True,
				state=precommit_diffcheck.FileState.modified,
			),
			precommit_diffcheck.GitStatusEntry(
				filename="test2.py",
				is_staged=False,
				state=precommit_diffcheck.FileState.added,
			),
			precommit_diffcheck.GitStatusEntry(
				filename="test3.py",
				is_staged=True,
				state=precommit_diffcheck.FileState.deleted,
			),
		]
		self.assertEqual(result, expected)

	def test_get_git_status_no_repository(self) -> None:
		"Do we detect when we aren't in a git repo?"
		exc = subprocess.CalledProcessError(
			cmd=["git", "status", "--prcelain"],
			returncode=125,
			stderr="not a git repository")
		with mock.patch("subprocess.check_output", side_effect=exc):
			result = precommit_diffcheck.get_git_status()
		self.assertEqual(result, [])


class TestGetContentAsDiff(unittest.TestCase):
	"Test get_content_as_diff()"
	def test_simple_file(self) -> None:
		"Can we get a simple file as a diff?"
		content = "\n".join((
			"Line 1",
			"Line 2",
			"Line new",
			"Line 3",
		))
		with mock.patch("precommit_diffcheck.open", mock.mock_open(read_data=content)):
			result = precommit_diffcheck.get_content_as_diff(["test3.txt"])
		expected = "\n".join((
			"--- /dev/null",
			"+++ b/test3.txt",
			"@@ -0,0 +1,4 @@",
			"+Line 1",
			"+Line 2",
			"+Line new",
			"+Line 3",
			"",
		))
		self.assertEqual(str(result), expected)

class TestLinesChanged(unittest.TestCase):
	"Test the ability to get the changed lines for a diff."
	TEST_PATCHSET = PatchSet("""
diff --git a/test.py b/test.py
index 8d58bdd..3ba9934 100755
--- a/test.py
+++ b/test.py
@@ -10,10 +10,6 @@ class ErrorContext(error_reporting.HTTPContext):
        def __dict__(self):
                return {
                        "method": "insanity",
-                       "url": "none-of-your-business",
-                       "userAgent": "Mozilla 1.0",
-                       "referrer": "bwahahaha",
-                       "responseStatusCode": 427,
                        "remoteIp": "1.2.3.4",
                }
 
@@ -22,6 +18,8 @@ def main():
   logging.basicConfig(level=logging.DEBUG)
   logging.info("Hey, you")
 
+  # foo bar
+
   client = error_reporting.Client.from_service_account_json("service_account.json",
        service="my-service",
        version="0.0.1",
""")

	def test_lines_added(self) -> None:
		"Test that we can get just the added lines"
		with mock.patch("precommit_diffcheck.get_diff_or_content",
			return_value=TestLinesChanged.TEST_PATCHSET):
			lines = list(precommit_diffcheck.lines_added())
		expected = [precommit_diffcheck.Diffline(a, c, "test.py", l) for (a, c, l) in (
			(True, '  # foo bar\n', 21),
			(True, '\n', 22),
		)]
		self.assertEqual(lines, expected)

	def test_lines_changed(self) -> None:
		"Test that we can get the right changed lines"
		with mock.patch("precommit_diffcheck.get_diff_or_content",
			return_value=TestLinesChanged.TEST_PATCHSET):
			lines = list(precommit_diffcheck.lines_changed())
		expected = [precommit_diffcheck.Diffline(a, c, "test.py", l) for (a, c, l) in (
			(False, '                       "url": "none-of-your-business",\n', 13),
			(False, '                       "userAgent": "Mozilla 1.0",\n', 14),
			(False, '                       "referrer": "bwahahaha",\n', 15),
			(False, '                       "responseStatusCode": 427,\n', 16),
			(True, '  # foo bar\n', 21),
			(True, '\n', 22),
		)]
		self.assertEqual(lines, expected)

	def test_lines_removed(self) -> None:
		"Test that we can get the right removed lines"
		with mock.patch("precommit_diffcheck.get_diff_or_content",
			return_value=TestLinesChanged.TEST_PATCHSET):
			lines = list(precommit_diffcheck.lines_removed())
		expected = [precommit_diffcheck.Diffline(a, c, "test.py", l) for (a, c, l) in (
			(False, '                       "url": "none-of-your-business",\n', 13),
			(False, '                       "userAgent": "Mozilla 1.0",\n', 14),
			(False, '                       "referrer": "bwahahaha",\n', 15),
			(False, '                       "responseStatusCode": 427,\n', 16),
		)]
		self.assertEqual(lines, expected)
