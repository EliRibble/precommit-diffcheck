"Test module for precommit_diffcheck"
import contextlib
import typing
import unittest
import unittest.mock

from nose2.tools import params # pylint: disable=import-error
import precommit_diffcheck


@contextlib.contextmanager
def set_git_output(output: typing.Text):
	"Set the output from git subprocess calls."
	with unittest.mock.patch("subprocess.check_output", return_value=output.encode("utf-8")):
		yield


class TestHasStagedChanges(unittest.TestCase):
	"Test has_staged_changes function."

	@params("M", "A", "D")
	def test_no_staged_changes(self, status):
		"Can we detect when we have changes, but not staged changes?"
		output = " {} test.py\n?? test2.py".format(status)
		with set_git_output(output):
			self.assertFalse(precommit_diffcheck.has_staged_changes())

	@params("M", "A", "D")
	def test_has_staged_changes(self, status):
		"Can we detect when we have staged changes?"
		output = "{}  test.py\n?? test2.py".format(status)
		with set_git_output(output):
			self.assertTrue(precommit_diffcheck.has_staged_changes())

class TestChangedLines(unittest.TestCase):
	"Test the ability to get the changed lines for a diff."
	TEST_PATCH = """
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
"""
	def test_addedlines(self):
		"Test that we can get just the added lines"
		with unittest.mock.patch("precommit_diffcheck.get_diff",
			return_value=TestChangedLines.TEST_PATCH):
			lines = list(precommit_diffcheck.addedlines())
		expected = [precommit_diffcheck.Diffline(a, c, "test.py", l) for (a, c, l) in (
			(True, '  # foo bar\n', 21),
			(True, '\n', 22),
		)]
		self.assertEqual(lines, expected)

	def test_changedlines(self):
		"Test that we can get the right changed lines"
		with unittest.mock.patch("precommit_diffcheck.get_diff",
			return_value=TestChangedLines.TEST_PATCH):
			lines = list(precommit_diffcheck.changedlines())
		expected = [precommit_diffcheck.Diffline(a, c, "test.py", l) for (a, c, l) in (
			(False, '                       "url": "none-of-your-business",\n', 13),
			(False, '                       "userAgent": "Mozilla 1.0",\n', 14),
			(False, '                       "referrer": "bwahahaha",\n', 15),
			(False, '                       "responseStatusCode": 427,\n', 16),
			(True, '  # foo bar\n', 21),
			(True, '\n', 22),
		)]
		self.assertEqual(lines, expected)

	def test_removedlines(self):
		"Test that we can get the right removed lines"
		with unittest.mock.patch("precommit_diffcheck.get_diff",
			return_value=TestChangedLines.TEST_PATCH):
			lines = list(precommit_diffcheck.removedlines())
		expected = [precommit_diffcheck.Diffline(a, c, "test.py", l) for (a, c, l) in (
			(False, '                       "url": "none-of-your-business",\n', 13),
			(False, '                       "userAgent": "Mozilla 1.0",\n', 14),
			(False, '                       "referrer": "bwahahaha",\n', 15),
			(False, '                       "responseStatusCode": 427,\n', 16),
		)]
		self.assertEqual(lines, expected)
