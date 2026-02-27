#!/usr/bin/env python3
"""
AITBC CLI Setup Script
"""

from setuptools import setup, find_packages
import os

# Read README file
def read_readme():
    with open("README.md", "r", encoding="utf-8") as fh:
        return fh.read()

# Read requirements
def read_requirements():
    with open("requirements.txt", "r", encoding="utf-8") as fh:
        return [line.strip() for line in fh if line.strip() and not line.startswith("#")]

setup(
    name="aitbc-cli",
    version="0.1.0",
    author="AITBC Team",
    author_email="team@aitbc.net",
    description="AITBC Command Line Interface Tools",
    long_description=read_readme(),
    long_description_content_type="text/markdown",
    url="https://aitbc.net",
    project_urls={
        "Homepage": "https://aitbc.net",
        "Repository": "https://github.com/aitbc/aitbc",
        "Documentation": "https://docs.aitbc.net",
    },
    packages=find_packages(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "Operating System :: OS Independent",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: System :: Distributed Computing",
    ],
    python_requires=">=3.13",
    install_requires=read_requirements(),
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "pytest-asyncio>=0.21.0",
            "pytest-cov>=4.0.0",
            "pytest-mock>=3.10.0",
            "black>=22.0.0",
            "isort>=5.10.0",
            "flake8>=5.0.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "aitbc=aitbc_cli.main:main",
        ],
    },
    include_package_data=True,
    package_data={
        "aitbc_cli": ["*.yaml", "*.yml", "*.json"],
    },
    zip_safe=False,
)
