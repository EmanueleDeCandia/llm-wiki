"""Motore di compilazione: note atomiche, wikilink, indice (Skill §2, §4-A)."""
from .base import CompilationResult, CompiledNote, CompileContext, Compiler  # noqa: F401
from .deterministic import DeterministicCompiler  # noqa: F401
from .links import (  # noqa: F401
    GraphNode,
    LinkRegistry,
    extract_link_targets,
    extract_links,
    extract_abstract,
    strip_links,
)
from .llm_compiler import LLMCompiler  # noqa: F401


def build_compiler(ctx_llm=None, max_notes: int = 12):
    """Factory: usa LLMCompiler se c'è un client LLM, altrimenti deterministico."""
    if ctx_llm is not None:
        from .llm_compiler import LLMCompiler as _LLMC

        return _LLMC(ctx_llm)
    return DeterministicCompiler()
