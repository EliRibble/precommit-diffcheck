"Setup the module."
import setuptools  # type: ignore

setuptools.setup(
	install_requires=["unidiff==0.5.5"],
	extras_require={
		"develop": [
			"mypy",
			"nose2",
			"pylint",
			"twine",
			"wheel",
		]
	},
	package_data={
		"precommit_diffcheck": ["py.typed"],
	},
)
