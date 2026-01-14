# coding: utf-8

from setuptools import setup, find_packages  # noqa: H301

# To install the library, run the following
#
# python setup.py install
#
# prerequisite: setuptools
# http://pypi.python.org/pypi/setuptools
NAME = "pacifica-ccxt-adapter"
VERSION = "0.1"
PYTHON_REQUIRES = ">=3.7"
REQUIRES = [
    "python-dotenv",
    "ccxt",
]

setup(
    name=NAME,
    version=VERSION,
    description="Python CCXT Adapter for pacifica.fi",
    author="marcelkb",
    author_email="",
    url="",
    keywords=["pacifica", "ccxt", ""],
    install_requires=REQUIRES,
    packages=find_packages(exclude=["test", "tests"]),
    include_package_data=True,
    long_description_content_type="text/markdown",
    long_description="""\
    Python CCXT Wrapper for pacifica trading.
    """,  # noqa: E501
    package_data={"pacifica": ["py.typed", "signers/*"]},
)
