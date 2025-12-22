"""
Setup script for {{ cookiecutter.extension_display_name }}
"""

from setuptools import setup, find_packages
import os

# Read the contents of README file
this_directory = os.path.abspath(os.path.dirname(__file__))
with open(os.path.join(this_directory, 'README.md'), encoding='utf-8') as f:
    long_description = f.read()

# Read requirements
with open(os.path.join(this_directory, 'requirements.txt'), encoding='utf-8') as f:
    requirements = f.read().splitlines()

setup(
    name="{{ cookiecutter.package_name }}",
    version="{{ cookiecutter.version }}",
    author="{{ cookiecutter.author_name }}",
    author_email="{{ cookiecutter.author_email }}",
    description="{{ cookiecutter.extension_description }}",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/{{ cookiecutter.github_username }}/{{ cookiecutter.extension_name }}",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: {{ cookiecutter.license }} License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: {{ cookiecutter.python_version }}",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: Office/Business :: Financial",
        {% if cookiecutter.extension_type == "payment" %}
        "Topic :: Office/Business :: Financial :: Point-Of-Sale",
        {% elif cookiecutter.extension_type == "erp" %}
        "Topic :: Office/Business",
        {% elif cookiecutter.extension_type == "analytics" %}
        "Topic :: Scientific/Engineering :: Information Analysis",
        {% else %}
        "Topic :: Software Development :: Libraries",
        {% endif %}
    ],
    python_requires=">={{ cookiecutter.python_version }}",
    install_requires=requirements,
    extras_require={
        "dev": [
            "pytest>=6.0",
            "pytest-asyncio>=0.18.0" if {{ cookiecutter.use_asyncio|lower }} else "",
            "pytest-cov>=2.12",
            "black>=21.0",
            "isort>=5.9",
            "flake8>=3.9",
            "mypy>=0.910",
            "pre-commit>=2.15",
        ],
        "docs": [
            "sphinx>=4.0",
            "sphinx-rtd-theme>=1.0",
            "myst-parser>=0.15",
        ],
        {% if cookiecutter.extension_type == "analytics" %}
        "viz": [
            "matplotlib>=3.5.0",
            "plotly>=5.0.0",
            "seaborn>=0.11.0",
        ],
        {% endif %}
    },
    entry_points={
        "console_scripts": [
            "{{ cookiecutter.package_name }}={{ cookiecutter.package_name }}.cli:main",
        ],
        "aitbc.extensions": [
            "{{ cookiecutter.extension_name }}={{ cookiecutter.package_name }}.{{ cookiecutter.class_name }}",
        ],
    },
    include_package_data=True,
    package_data={
        "{{ cookiecutter.package_name }}": [
            "templates/*.yaml",
            "templates/*.json",
            "static/*",
        ],
    },
    zip_safe=False,
    keywords="aitbc {{ cookiecutter.extension_type }} {{ cookiecutter.extension_name }}",
    project_urls={
        "Bug Reports": "https://github.com/{{ cookiecutter.github_username }}/{{ cookiecutter.extension_name }}/issues",
        "Source": "https://github.com/{{ cookiecutter.github_username }}/{{ cookiecutter.extension_name }}",
        "Documentation": "https://{{ cookiecutter.extension_name }}.readthedocs.io",
    },
)
