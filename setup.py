from __future__ import absolute_import, division, print_function

import os
# To use a consistent encoding
from codecs import open

import setuptools

import versioneer

here = os.path.abspath(os.path.dirname(__file__))

description = "NSLS-II Hard X-ray Nanoprobe data acquisition tools"

# Get the long description from the README file
readme_file = os.path.join(here, 'README.md')
long_description = description
if os.path.isfile(readme_file):
    with open(readme_file, encoding='utf-8') as f:
        long_description = f.read()

req_file = os.path.join(here, 'requirements.txt')
requirements = []
if os.path.isfile(req_file):
    with open(req_file) as f:
        requirements = f.read().splitlines()

setuptools.setup(
    name="hxntools",
    version=versioneer.get_version(),
    cmdclass=versioneer.get_cmdclass(),
    license="BSD-3-Clause",
    packages=setuptools.find_packages(),
    long_description=long_description,
    long_description_content_type="text/markdown",
    description=description,
    author="Brookhaven National Laboratory",
    install_requires=requirements,
)
