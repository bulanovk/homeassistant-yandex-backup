"""Root conftest.py for all tests.

This file is loaded before any tests and can be used to set up
global configurations that apply to all tests.
"""

import sys
import asyncio

# On Windows, set up the event loop policy and mock Unix-only modules
if sys.platform == "win32":
    # Mock Unix-only modules before importing homeassistant.runner
    import types

    # Mock fcntl module
    fcntl_mock = types.ModuleType("fcntl")
    fcntl_mock.fcntl = lambda *args, **kwargs: 0
    fcntl_mock.F_GETFL = 0
    fcntl_mock.F_SETFL = 0
    fcntl_mock.O_NONBLOCK = 0
    sys.modules["fcntl"] = fcntl_mock

    # Mock resource module
    resource_mock = types.ModuleType("resource")
    resource_mock.getrlimit = lambda *args: (0, 0)
    resource_mock.setrlimit = lambda *args, **kwargs: None
    resource_mock.RLIMIT_NOFILE = 0
    sys.modules["resource"] = resource_mock
