"All the logic for the module"
import collections
from enum import Enum
import functools
import logging
import os
import re
import subprocess
from typing import Iterable, Iterator, List, Mapping, Optional, Pattern, Set

from unidiff import Hunk, PatchSet  # type: ignore
import unidiff.patch  # type: ignore

LOGGER = logging.getLogger(__name__)

PRE_COMMIT_FROM_REF = "PRE_COMMIT_FROM_REF"
PRE_COMMIT_ORIGIN = "PRE_COMMIT_ORIGIN"
PRE_COMMIT_SOURCE = "PRE_COMMIT_SOURCE"
PRE_COMMIT_TO_REF = "PRE_COMMIT_TO_REF"
PRE_COMMIT_REF_SPECIFIERS = (
	PRE_COMMIT_FROM_REF,
	PRE_COMMIT_ORIGIN,
	PRE_COMMIT_SOURCE,
	PRE_COMMIT_TO_REF,
)

class DiffcheckError(Exception):
	"Base class for any exceptions from this library"

Diffline = collections.namedtuple("Diffline", (
	"added",  # True if the line is added, false otherwise
	"content",  # The content of the change
	"filename",  # The name of the target file to change
	"linenumber",  # If the line was removed, the line number it previously had.
	               # Otherwise the line number of the added line.
))
Filenames = Iterable[str]
class FileState(Enum):
	"The various states a file can be in for git."
	added = "A"
	deleted = "D"
	modified = "M"

GitStatusEntry = collections.namedtuple("GitStatusEntry", (
	"filename", # The name of the file
	"is_staged", # True if the change is staged, otherwise unstaged
	"state", # FileState, represents what happened to the file
))

def filter_filenames(filenames: Iterable[str], exclusions: Iterable[Pattern]) -> Iterable[str]:
	"""Filter the provided filenames by the regex exclusions.

	Args:
		filenames: The list of filenames provided by the user. These will generally be
			relative paths within a git repository.
		exclusions: A list of regex patterns to apply to the filenames. The exclusions
			are applied after transforming the filenames to be relative to the git
			repository root.
	Returns:
		file paths relative to git root that were not excluded.
	"""
	# Convert provided filenames into absolute paths
	cwd = os.path.abspath(".")
	abs_filenames = [os.path.join(cwd, f) for f in filenames]

	# Use the git root for calculating absolute paths
	git_root = get_git_root()

	results = []
	for abs_filename in abs_filenames:
		common_path = os.path.commonprefix([git_root, abs_filename])
		if common_path != git_root:
			LOGGER.warning((
				"Skipping %s because it appears to be outside of the git source "
				"tree (common path is '%s')."), abs_filename, common_path)
			continue
		git_relative_path = os.path.relpath(abs_filename, git_root)
		if is_excluded(git_relative_path, exclusions):
			continue
		# Always filter out internal .git files
		if git_relative_path.startswith(".git/"):
			LOGGER.debug("Skipping '%s' because it appears to be a git internal file.", git_relative_path)
			continue
		results.append(git_relative_path)
	return results


def get_added_lines_for_file(patchset: PatchSet, filename: str) -> Set[int]:
	"""Get the set of lines added for a given filename in a patchset.

	Args:
		patchset: The patchset to extract added lines from.
		filename: The path of the file to use in calculating added lines.
			The path should match whatever is in the patchset.
	Returns:
		The set of lines added for the given filename in the patchset.
	"""
	results = set()
	for patch in patchset:
		if patch.target_file != filename:
			continue
		for hunk in patch:
			for line in hunk:
				if line.is_added:
					results.add(line.target_line_no)
	return results

def get_content_as_diff(filenames: Filenames) -> PatchSet:
	"""Gets the content of a file and converts it into a diff like it was all added."""
	patchset = PatchSet("")
	for filename in filenames:
		try:
			with open(filename, "r") as input_:
				content = input_.read()
		except UnicodeDecodeError as ex:
			LOGGER.warning("Failed to read in %s. Skipping. Error: %s",
				filename, ex)
			continue
		patchedfile = unidiff.patch.PatchedFile(
			source="/dev/null",
			target="b/" + filename,
		)
		lines = content.split("\n")
		# Handle the fact that split will give us a final empty string if we ended with a newline
		if lines[-1] == "":
			lines = lines[:-1]
		total_lines = len(lines)
		hunk = unidiff.patch.Hunk(
			src_start=0,
			src_len=0,
			tgt_start=1,
			tgt_len=total_lines,
		)
		for i, line in enumerate(lines):
			line = line + "\n"
			hunk.append(unidiff.patch.Line(
				value=line,
				line_type=unidiff.patch.LINE_TYPE_ADDED,
				source_line_no=i,
				target_line_no=i,
			))
		patchedfile.append(hunk)
		patchset.append(patchedfile)
	return patchset

def get_diff_or_content(filenames: Optional[Filenames] = None) -> PatchSet:
	"""Gets the current diff or the content.

	This is a convenience function that is designed to make it easy for hooks
	to query a single interface to get the lines that should be considered
	for the hook. If the special pre-commit environment variables are present
	indicating a `pre-commit run --from-ref --to-ref` then those values will
	be used. If there are staged changes then it will return the unified
	diff for the staged changes. If there are unstaged changes it will return
	the unified diff for the unstaged changes. If there are no staged or
	unstaged changes it will return a unified diff with the entire content of the
	file.

	This special environment variables provided by pre-commit run tell
	us that we need to get a diff ourselves from a specific revision to
	another. For example, if the user performs:

	pre-commit run --source HEAD^ -- origin HEAD

	Then the following environment variables will be set (depending on
	pre-commit version):

	PRE_COMMIT_FROM_REF=HEAD^
	PRE_COMMIT_ORIGIN=HEAD^
	PRE_COMMIT_SOURCE=HEAD
	PRE_COMMIT_TO_REF=HEAD

	Args:
		filenames: If present, constrain the diff to the provided files.
	"""
	filenames = filenames or []
	normalized_filenames = [os.path.normpath(f) for f in filenames]
	if has_ref_specifiers():
		from_ref = get_ref_from()
		to_ref = get_ref_to()
		if from_ref and to_ref:
			command = ["git", "diff-tree", "-p", from_ref, to_ref]
		elif from_ref:
			command = ["git", "diff-tree", "-p", from_ref, "HEAD"]
		elif to_ref:
			raise DiffcheckError(
				"You cannot specify PRE_COMMIT_TO_REF without an accompanying "
				"PRE_COMMIT_FROM_REF.")
		raise AssertionError(
			"Somehow we have ref specifiers but they are both 'None'. This means "
			"my programmer made a wrong assumption - please file a bug for me.")
	if has_staged_changes(normalized_filenames):
		command = ["git", "diff-index", "-p", "--cached"]
	elif has_unstaged_changes(normalized_filenames):
		command = ["git", "diff-files", "-p"]
	else:
		if not normalized_filenames:
			raise DiffcheckError(("You have no staged changes, no unstaged changes,"
				" and didn't specify any filenames. This guarantees there is nothing "
				"to analyze, which I'm pretty sure is not what you want."))
		LOGGER.debug("git workspace is clean, returning the content of files as a diff")
		return get_content_as_diff(normalized_filenames)
	if normalized_filenames:
		command += normalized_filenames
	try:
		LOGGER.debug("Executing %s", command)
		diff_content = subprocess.check_output(command)
		try:
			unicode_content = diff_content.decode("utf-8")
			return PatchSet(unicode_content)
		except UnicodeDecodeError as ex:
			LOGGER.error((
				"Running the command '%s' produced a diff that cannot be decoded as unicode: "
				"%s\nIf you are introducing the bad Unicode you should fix the file in question.  "
				"If the bad Unicode has already been introduced there may not be much you can "
				"do now without rewriting git history. As near as I can tell, the content near "
				"the bad Unicode is character %d to %d:\n\n"
				"*** begin ***\n"
				"...%s<bad unicode here>%s...\n"
				"*** end ***"),
				command,
				ex,
				ex.start,
				ex.end,
				diff_content[max(0, ex.start - 100):ex.start-1].decode("utf-8"),
				diff_content[ex.end+1:min(len(diff_content), ex.end + 100)].decode("utf-8"))
			raise
	except subprocess.CalledProcessError as exc:
		raise DiffcheckError("Failed to get patchset: {}".format(exc))

def get_filename_to_added_lines(patchset: Optional[PatchSet] = None) -> Mapping[str, Set[int]]:
	"""Get a mapping of filenames to the line numbers added.

	Given a PatchSet this will return a mapping of the filenames in the PatchSet
	to the set of lines that were added in the PatchSet. This is useful when
	a hook gets a list of violations that correspond to a specific filename
	and line number and the hook wants to filter out any violations that do
	not apply to the given PatchSet.

	Args:
		patchset: The patchset to operate on, or None to calculate the patchset.
	Returns:
		A mapping of filenames relative to the git repository root to the set
		of line numbers, starting at 1, that were added in the patchset.
	"""
	patchset = patchset or get_diff_or_content()
	unique_filenames = {patch.target_file for patch in patchset}
	return {
		filename[2:]: get_added_lines_for_file(patchset, filename) for filename in unique_filenames
	}

def get_files_to_analyze(filenames: List[str], patchset: PatchSet = None) -> List[str]:
	"""Get the intersection of a list of files and a patchset.

	The idea here is that the user could specify some number of files. There may
	also be a patchset in play which identifies another set of files. We only want
	to tell the client of the library to analyze files if they are part of the
	intersection of the files in the patchset and the files specified by the user.

	If there is no intersection and the list of files has content, we prefer the list
	of files. If there is no files specified in the file list we prefer the patchset.

	Returns:
		A list of absolute file paths.
	"""
	git_root = get_git_root()
	cwd = os.path.abspath(".")
	normalized_filenames = [os.path.normpath(f) for f in filenames]
	abs_filenames = [os.path.normpath(os.path.join(cwd, f)) for f in normalized_filenames]

	patchset = patchset or get_diff_or_content(normalized_filenames)

	abs_changed_files = []
	for patch in patchset:
		# Remove 'b/' from git patch format
		target = patch.target_file[2:]
		# Make the path absolute
		abs_target = os.path.join(git_root, target)
		if abs_filenames and abs_target not in abs_filenames:
			LOGGER.debug("Skipping %s because it wasn't one of the specified files", target)
			continue
		abs_changed_files.append(os.path.normpath(abs_target))
	if not set(abs_changed_files).intersection(abs_filenames):
		LOGGER.info((
			"Looks like there's no overlap between requested files (%s) and "
			"current dirty git files (%s)."),
			" ".join(sorted(abs_filenames)), " ".join(sorted(abs_changed_files)))
		if filenames:
			LOGGER.info("We'll use the requested files.")
			return [os.path.normpath(f) for f in filenames]
		LOGGER.info("We'll use the current git dirty files.")
	return abs_changed_files

@functools.lru_cache()
def get_git_root() -> str:
	"""Return the absolute path to the root of the current git repository."""
	return subprocess.check_output(
		["git", "rev-parse", "--show-toplevel"],
		encoding="UTF-8").strip()

def get_git_status(filenames: Optional[Filenames] = None) -> List[GitStatusEntry]:
	"""Get the current git status."""
	command = ["git", "status", "--porcelain"]
	if filenames:
		command += filenames
	try:
		output = subprocess.check_output(command, encoding="UTF-8", stderr=subprocess.PIPE)
	except subprocess.CalledProcessError as ex:
		if "not a git repository" in ex.stderr:
			return []
		raise
	entries = []
	for line in output.splitlines():
		# If the line indicates we know nothing then ignore it
		if line[:2] == "??":
			continue
		staged_status = line[0]
		is_staged = staged_status not in " ?"
		unstaged_status = line[1]
		filename = line[3:]
		entries.append(GitStatusEntry(
			filename=filename,
			is_staged=is_staged,
			state=FileState(staged_status if is_staged else unstaged_status),
		))
	return entries

def get_ref_from() -> Optional[str]:
	"""Return the 'from' ref pre-commit may have provided."""
	return os.environ.get(PRE_COMMIT_FROM_REF,
		os.environ.get(PRE_COMMIT_SOURCE, None))

def get_ref_to() -> Optional[str]:
	"""Return the 'to' ref pre-commit may have provided."""
	return os.environ.get(PRE_COMMIT_TO_REF,
		os.environ.get(PRE_COMMIT_ORIGIN, None))

def has_ref_specifiers() -> bool:
	"""Return whether or not we have pre-commit provided ref specifiers."""
	for specifier in PRE_COMMIT_REF_SPECIFIERS:
		if os.environ.get(specifier, None):
			return True
	return False

def has_staged_changes(filenames: Optional[Filenames] = None) -> bool:
	"""Determine if the current git repository has staged changes or not."""
	status = get_git_status(filenames)
	return any(s.is_staged for s in status)

def has_unstaged_changes(filenames: Optional[Filenames] = None) -> bool:
	"""Determine if the current git repository has unstaged changes."""
	status = get_git_status(filenames)
	return any(not s.is_staged for s in status)

def is_excluded(git_relative_path: str, exclusions: Iterable[Pattern]) -> bool:
	"""True if the provided git-relative path matches one of the exclusion patterns.

	Args:
		git_relative_path: The path of some file relative to the git repository root.
		exclusions: An iterable of regex patterns identifying file paths to exclude.
	Returns:
		True if the file should be excluded based on the exclusion patterns.
	"""
	for exclusion in exclusions:
		match = exclusion.match(git_relative_path)
		if match:
			LOGGER.info("Excluding '%s'", git_relative_path)
			LOGGER.debug("Matching pattern was '%s'", exclusion.pattern)
			return True
	return False

def lines_added(patchset: Optional[PatchSet] = None) -> Iterator[Diffline]:
	"Get the added lines. A convenience wrapper for changedlines."
	return lines_changed(patchset, include_removed_lines=False)

def lines_changed(
	patchset: Optional[PatchSet] = None,
	include_added_lines: bool = True,
	include_removed_lines: bool = True) -> Iterator[Diffline]:
	"""Get the changed lines one at a time.

	Args:
		filenames: If truthy then this argument constrains the iterator
			to only lines that are in the set of provided files.
	Yields:
		One Diffline for each changed line (added or removed).
	"""
	patchset = patchset or get_diff_or_content()
	for patch in patchset:
		# Remove 'b/' from git patch format
		target = patch.target_file[2:]
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

def lines_removed(patchset: Optional[PatchSet] = None) -> Iterator[Diffline]:
	"Get the removed lines. A convenience wrapper for changedlines."
	return lines_changed(patchset, include_added_lines=False)
