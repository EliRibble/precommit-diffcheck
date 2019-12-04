"All the logic for the module"
import collections
import logging
import subprocess
import typing

import unidiff  # pylint: disable=import-error


LOGGER = logging.getLogger(__name__)


class DiffcheckError(Exception):
	"Base class for any exceptions from this library"

Diffline = collections.namedtuple("Diffline", (
	"added",  # True if the line is added, false otherwise
	"content",  # The content of the change
	"filename",  # The name of the target file to change
	"linenumber",  # If the line was removed, the line number it previously had.
	               # Otherwise the line number of the added line.
))

def get_diff() -> typing.Text:
	"Get the current set of changed files."
	command = ["git", "diff", "HEAD"]
	try:
		if has_staged_changes():
			command = ["git", "diff", "--cached"]
		return subprocess.check_output(command).decode("utf-8")
	except subprocess.CalledProcessError as exc:
		raise DiffcheckError("Failed to get patchset: {}".format(exc))

def get_patchset() -> unidiff.PatchSet:
	"Get the patchset representing the diff'd files"
	diff = get_diff()
	return unidiff.PatchSet(diff)


MaybeFilenames = typing.Optional[typing.Iterable[typing.Text]]
def addedlines(filenames: MaybeFilenames = None) -> typing.Iterator[Diffline]:
	"Get the added lines. A convenience wrapper for changedlines."
	return changedlines(filenames, include_removed_lines=False)

def changedlines(
	filenames: MaybeFilenames = None,
	include_added_lines: bool = True,
	include_removed_lines: bool = True) -> typing.Iterator[Diffline]:
	"""Get the changed lines one at a time.

	Args:
		filenames: If truthy then this argument constrains the iterator
			to only lines that are in the set of provided files.
	Yields:
		One Diffline for each changed line (added or removed).
	"""
	patchset = get_patchset()
	for patch in patchset:
		# Remove 'b/' from git patch format
		target = patch.target_file[2:]
		if filenames and target not in filenames:
			LOGGER.debug("Skipping %s which is part of the diff but not in "
				"the requested files to check.", target)
			continue
		for hunk in patch:
			for line in hunk:
				if line.is_context:
					continue
				if line.is_added and include_added_lines:
					yield Diffline(
						added=line.is_added,
						content=line.value,
						filename=target,
						linenumber=line.target_line_no,
					)
				if line.is_removed and include_removed_lines:
					yield Diffline(
						added=line.is_added,
						content=line.value,
						filename=target,
						linenumber=line.source_line_no,
					)

def removedlines(filenames: MaybeFilenames = None) -> typing.Iterator[Diffline]:
	"Get the removed lines. A convenience wrapper for changedlines."
	return changedlines(filenames, include_added_lines=False)

def has_staged_changes() -> bool:
	"""Determine if the current git repository has staged changes or not."""
	output = subprocess.check_output(["git", "status", "--porcelain"])
	for line in output.decode("utf-8").splitlines():
		if line[0] in "MAD":
			return True
	return False
