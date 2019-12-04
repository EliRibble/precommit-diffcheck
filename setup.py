"Setup the module."
import setuptools

setuptools.setup(
	install_requires=["unidiff==0.5.5"],
	extras_require={
		"develop": [
			"nose2",
			"twine",
		]
	},
	package_data={
		"precommit_diffcheck": ["py.typed"],
	},
)
