"""Interrogazione della conoscenza compilata (retrieval + sintesi)."""
from .query_service import QueryResult, run_query  # noqa: F401
from .retriever import ScoredNote, deterministic_answer, retrieve  # noqa: F401
