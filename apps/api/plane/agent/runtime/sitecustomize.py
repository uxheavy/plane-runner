"""Production-only CPython child-launch compatibility for the runtime image.

The pinned Hermes Code Mode implementation uses ``subprocess.Popen``. Python
3.12 enables its vfork optimization by default, but the runtime policy keeps
vfork denied. The runtime service sets this flag only in the disposable child
environment; the image-local hook then selects CPython's classic clone/exec
path before Hermes imports or runs the genuine AIAgent.
"""

from __future__ import annotations

import os


if os.environ.get("PLANE_AGENT_RUNTIME_DISABLE_VFORK") == "1":
    import subprocess

    subprocess._USE_VFORK = False
