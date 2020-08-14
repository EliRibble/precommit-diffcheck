"Test module for precommit_diffcheck"
import contextlib
import re
import subprocess
from typing import Iterable, Pattern
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

class TestAddedLines(unittest.TestCase):
	"Test the ability to calculated the added lines by file."
	TEST_PATCHSET = PatchSet("""
diff --git a/file1.py b/file1.py
index 268983e..bdde27b 100644
--- a/file1.py
+++ b/file1.py
@@ -1,5 +1,9 @@
+# A module for saying stuff.
 def main():
 	print("Hello world. File 1.")
 	print("This is just")
 	print("A file for getting")
 	print("A diff.")
+
+import helper
+helper.help()
diff --git a/file2.py b/file2.py
index f4f14b5..f3439c2 100644
--- a/file2.py
+++ b/file2.py
@@ -1,5 +1,4 @@
-def helper():
+def help():
 	print("This file does")
-	print("nothing.")
 	print("But help.")
 
""")
	def test_get_added_lines_for_file(self) -> None:
		"Do we properly get the set of added lines?"
		added_lines = precommit_diffcheck.get_added_lines_for_file(
			TestAddedLines.TEST_PATCHSET,
			"b/file1.py",
		)
		self.assertEqual(added_lines, {1, 7, 8, 9})

	def test_get_filename_to_added_lines(self) -> None:
		"Do we properly get a mapping of filenames to added lines?"
		filename_to_added_lines = precommit_diffcheck.get_filename_to_added_lines(
			TestAddedLines.TEST_PATCHSET,
		)
		expected = {
			"file1.py": {1, 7, 8, 9},
			"file2.py": {1},
		}
		self.assertEqual(filename_to_added_lines, expected)

class TestExclusion(unittest.TestCase):
	"Test logic around excluding files."
	@params(
		((re.compile(r"foo/\w+\.txt"),),),
		((re.compile("not matching"), re.compile("foo/")),),
	)
	def test_is_excluded(self, exclusions: Iterable[Pattern]):
		"Do we detect when exclusions match?"
		result = precommit_diffcheck.is_excluded("foo/bar.txt", exclusions)
		self.assertTrue(result)

	@params(
		((re.compile("not matching"),),),
		((re.compile(r"foo/\w+\.tx$"), re.compile(r"^bar\.txt")),),
	)
	def test_not_is_excluded(self, exclusions: Iterable[Pattern]):
		"Do we detect when exclusions don't match?"
		result = precommit_diffcheck.is_excluded("foo/bar.txt", exclusions)
		self.assertFalse(result)

	@params(
		((
			re.compile(r"foo/"),
		), []),
		((
			re.compile(r"foo/\w+\.txt"),
		), []),
		((
			re.compile(r"foo/bar\.txt"),
		), ["foo/baz.txt",])
		)
	def test_filter_files(self,
			exclusions: Iterable[Pattern],
			expected: Iterable[str]):
		"Do we filter out filenames that match?"
		results = precommit_diffcheck.filter_filenames([
			"foo/bar.txt",
			"foo/baz.txt",
		], exclusions)
		self.assertEqual(expected, results)
