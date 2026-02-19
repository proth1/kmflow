"""Canonical API version constant.

Extracted to its own module to avoid circular imports when the
middleware needs the version but importing from ``main.py`` would
pull in the full application factory.
"""

API_VERSION = "0.8.0"
