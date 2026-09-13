"""Parsers multimodali (PDF, documenti, immagini, dataset)."""
from .base import DatasetParser as _DatasetParserProto  # noqa: F401
from .base import DocumentParser, ImageParser  # noqa: F401
from .dataset import ColumnProfile, DatasetParser, DatasetProfile  # noqa: F401
from .image_doc import ImageParser as PillowImageParser  # noqa: F401
from .pdf_doc import PdfParser  # noqa: F401
from .registry import (  # noqa: F401
    DATASET_EXTENSIONS,
    DOCUMENT_EXTENSIONS,
    IMAGE_EXTENSIONS,
    ParserRegistry,
    branch_for_extension,
)
from .text_doc import DocxDocumentParser, TextDocumentParser  # noqa: F401
