"""
{{ cookiecutter.extension_display_name }} - AITBC Extension

{{ cookiecutter.extension_description }}
"""

__version__ = "{{ cookiecutter.version }}"
__author__ = "{{ cookiecutter.author_name }} <{{ cookiecutter.author_email }}>"
__license__ = "{{ cookiecutter.license }}"

from .{{ cookiecutter.extension_name }} import {{ cookiecutter.class_name }}

__all__ = ["{{ cookiecutter.class_name }}"]
