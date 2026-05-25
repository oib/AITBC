#!/usr/bin/env python3
"""
setup.py for AITBC Agent SDK
Prepares the package for GitHub Packages distribution
"""

from setuptools import setup, find_packages
import os

# Read the README file
def read_readme():
    readme_path = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'README.md')
    if os.path.exists(readme_path):
        with open(readme_path, 'r', encoding='utf-8') as f:
            return f.read()
    return "AITBC Agent SDK - Python package for AI agent network participation"

# Read requirements from pyproject.toml
def read_requirements():
    import tomli
    pyproject_path = os.path.join(os.path.dirname(__file__), 'pyproject.toml')
    if os.path.exists(pyproject_path):
        try:
            with open(pyproject_path, 'rb') as f:
                data = tomli.load(f)
                return data.get("project", {}).get("dependencies", [])
        except ImportError:
            pass
    # Fallback to hardcoded list
    return [
        'requests>=2.32.4',
        'pydantic>=2.11.0'
    ]

setup(
    name="aitbc-agent-sdk",
    version="0.1.0",
    author="AITBC Agent Network",
    author_email="dev@aitbc.bubuit.net",
    description="Python SDK for AITBC AI Agent Network",
    long_description=read_readme(),
    long_description_content_type="text/markdown",
    url="https://github.com/oib/AITBC",
    project_urls={
        "Bug Tracker": "https://github.com/oib/AITBC/issues",
        "Documentation": "https://docs.aitbc.bubuit.net",
        "Source Code": "https://github.com/oib/AITBC",
    },
    packages=find_packages(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: POSIX :: Linux",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.13",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
        "Topic :: System :: Distributed Computing",
    ],
    python_requires=">=3.13",
    install_requires=read_requirements(),
    extras_require={
        "dev": [
            "pytest>=7.4.0",
            "pytest-asyncio>=0.21.0",
            "black>=23.9.0",
            "flake8>=6.1.0",
            "mypy>=1.6.0",
            "pre-commit>=3.4.0",
        ],
        "gpu": [
            "torch>=2.1.0",
            "torchvision>=0.16.0",
            "torchaudio>=2.1.0",
            "nvidia-ml-py>=12.535.0",
        ],
        "edge": [
            "paho-mqtt>=1.6.0",
            "aiohttp>=3.9.0",
            "cryptography>=41.0.0",
        ]
    },
    entry_points={
        "console_scripts": [
            "aitbc-agent=aitbc_agent.cli:main",
            "aitbc-agent-provider=aitbc_agent.provider:main",
            "aitbc-agent-consumer=aitbc_agent.consumer:main",
            "aitbc-agent-coordinator=aitbc_agent.coordinator:main",
        ],
    },
    include_package_data=True,
    package_data={
        "aitbc_agent": [
            "config/*.yaml",
            "templates/*.json",
            "schemas/*.json",
        ],
    },
    keywords="ai agents blockchain decentralized computing swarm intelligence",
    zip_safe=False,
)
