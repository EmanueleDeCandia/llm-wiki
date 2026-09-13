"""Sandbox computazionale (esecuzione Python isolata)."""
from .kernel_manager import (  # noqa: F401
    Figure,
    KernelManager,
    SandboxResult,
    create_kernel,
    dataset_loader_snippet,
)
from .prelude import PRELUDE, build_script  # noqa: F401
