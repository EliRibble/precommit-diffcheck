# Changelog

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
