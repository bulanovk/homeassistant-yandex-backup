"""sitecustomize.py - Loaded by Python before any other module.

This file is used to mock Unix-only modules on Windows before pytest
or any other modules are imported.
"""

import sys
import types

# On Windows, mock Unix-only modules before anything else imports them
if sys.platform == "win32":
    # Mock fcntl module (Unix file control)
    fcntl_mock = types.ModuleType("fcntl")
    fcntl_mock.fcntl = lambda *args, **kwargs: 0
    fcntl_mock.F_GETFL = 0
    fcntl_mock.F_SETFL = 0
    fcntl_mock.O_NONBLOCK = 0
    sys.modules["fcntl"] = fcntl_mock

    # Mock resource module (Unix resource limits)
    resource_mock = types.ModuleType("resource")
    resource_mock.getrlimit = lambda *args: (0, 0)
    resource_mock.setrlimit = lambda *args, **kwargs: None
    resource_mock.RLIMIT_NOFILE = 0
    sys.modules["resource"] = resource_mock
