"""Root conftest.py - Loaded before pytest plugins.

This file provides pytest configuration for the entire project.
"""

import sys

if sys.platform == "win32":
    def pytest_configure(config):
        """Pytest hook - called after command line options have been parsed."""
        # Windows-specific pytest configuration can go here
        pass
