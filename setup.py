import sys
from os import path

from setuptools import find_packages, setup

import versioneer

# NOTE: This file must remain Python 2 compatible for the foreseeable future,
# to ensure that we error out properly for people with outdated setuptools
# and/or pip.
min_version = (3, 6)
if sys.version_info < min_version:
    error = """
hxntools does not support Python {0}.{1}.
Python {2}.{3} and above is required. Check your Python version like so:

python3 --version

This may be due to an out-of-date pip. Make sure you have pip >= 9.0.1.
Upgrade pip like so:

pip install --upgrade pip
""".format(*(sys.version_info[:2] + min_version))
    sys.exit(error)

here = path.abspath(path.dirname(__file__))

description = "NSLS-II Hard X-ray Nanoprobe data acquisition tools"

readme_file = path.join(here, 'README.md')
long_description = description
if path.isfile(readme_file):
    with open(readme_file, encoding='utf-8') as f:
        long_description = f.read()

req_file = path.join(here, 'requirements.txt')
if path.isfile(req_file):
    with open(req_file) as f:
        # Parse requirements.txt, ignoring any commented-out lines.
        requirements = [line for line in f.read().splitlines()
                        if not line.startswith('#')]


setup(
    name="hxntools",
    version=versioneer.get_version(),
    cmdclass=versioneer.get_cmdclass(),
    description=description,
    long_description=long_description,
    long_description_content_type='text/markdown',
    author="Brookhaven National Laboratory",
    author_email="DAMA@bnl.gov",
    url="https://github.com/NSLS-II-HXN/hxntools",
    python_requires='>={}'.format('.'.join(str(n) for n in min_version)),
    packages=find_packages(exclude=['docs', 'tests']),
    include_package_data=True,
    install_requires=requirements,
    license="BSD-3-Clause",
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Natural Language :: English",
        "Programming Language :: Python :: 3",
    ],
)
