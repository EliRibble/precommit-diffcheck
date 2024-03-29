# Changelog

## 1.12

* Fix error with unstaged changes and diff created in 1.11
* Fix error with --from-ref/--to-ref created even earlier.

## 1.11

* Emit `precommit_diffcheck.DiffcheckError` instead of `UnicodeDecode` exceptions on failure to decode content. Also avoid double-decoding in failure.
* Fix diff command when --from-ref/--to-ref is not provided (default case)

## 1.10

* Show useful error when we can't get a diff due to Unicode issues.
* Improve commands for getting diffs to handle --from-ref better

## 1.9

* Restore support for Python 3.6

## 1.8

* Add `filter_filenames()` and `is_excluded()` functions.
* Add an `lru_cache` on `get_git_root()` for performance.

## 1.7

* Add `get_added_lines_for_file()`
* Add `get_filname_to_added_lines()`

## 1.6

* Normalize filenames when providing file content as a diff

## 1.5

* Return normalized paths from `get_files_to_analyze()`

## 1.4

* Fix return type on `get_files_to_analyze()`

## 1.3

* Add `get_git_root()` function.

## 1.2

* Add `get_files_to_analyze` function.

## 1.1

* Honor --to-ref and --from-ref environment variables from pre-commit run
* Warn-and-ignore unicode decode errors.

## 1.0

* Reworked some of the APIs,
* committed to exposing unidiff's types through the library
* added the `get_diff_or_content()` function.

## 0.3

Initial release
