#!/usr/bin/env python3
"""AITBC CLI Setup Script"""

from pathlib import Path
from setuptools import find_packages, setup


def read_readme() -> str:
    readme = Path("README.md")
    if readme.is_file():
        return readme.read_text(encoding="utf-8")
    return "AITBC Command Line Interface"


def read_requirements() -> list[str]:
    req = Path("requirements.txt")
    if req.is_file():
        return [
            line.strip() for line in req.read_text(encoding="utf-8").splitlines() if line.strip() and not line.startswith("#")
        ]
    return []


setup(
    name="aitbc-cli",
    version="0.10.18",
    author="AITBC Team",
    author_email="team@aitbc.net",
    description="AITBC Command Line Interface Tools",
    long_description=read_readme(),
    long_description_content_type="text/markdown",
    url="https://aitbc.net",
    packages=find_packages(include=["aitbc_cli", "aitbc_cli.*"]),
    python_requires=">=3.13",
    install_requires=read_requirements(),
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "pytest-asyncio>=0.23.0",
            "pytest-cov>=4.0.0",
            "pytest-mock>=3.10.0",
            "black>=22.0.0",
            "isort>=5.10.0",
            "flake8>=5.0.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "aitbc=aitbc_cli.core.main:main",
        ],
    },
    include_package_data=True,
    package_data={
        "": ["*.yaml", "*.yml", "*.json"],
    },
    zip_safe=False,
)
