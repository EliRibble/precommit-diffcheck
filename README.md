# precommit-message-perservation

This is a simple library that makes it easier to code hooks for [pre-commit](https://pre-commit.com) that validate commit messages that preserve the commit message on failure.
In other words, if the user writes a long commit message and your pre-commit hook tells them the message is bad, they won't have their message entirely thrown away.

## Hacking

You'll want to install the developer dependencies:

```
pip install -e .[develop]
```

This will include `nose2`, which is the test runner of choice. After you make modifications you can run tests with

```
nose2
```

When you're satisfied you'll want to update the version number and do build-and-upload:

```
python setup.py sdist bdist_wheel
twine upload dist/* --verbose
```
