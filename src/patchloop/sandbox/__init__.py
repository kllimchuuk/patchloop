"""Docker sandbox: image preparation (network) and no-network runs (SPEC §6)."""

from patchloop.sandbox.errors import SandboxError
from patchloop.sandbox.image import ensure_image
from patchloop.sandbox.runner import ExecResult, run_in_sandbox
from patchloop.sandbox.workspace import make_workspace, remove_workspace, workspace

__all__ = [
    "ExecResult",
    "SandboxError",
    "ensure_image",
    "make_workspace",
    "remove_workspace",
    "run_in_sandbox",
    "workspace",
]
