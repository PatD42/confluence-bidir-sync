"""Conversion result data model."""

from dataclasses import dataclass, field
from typing import Dict, List, Any


@dataclass
class ConversionResult:
    """Result of XHTML to markdown conversion.

    Contains the converted markdown content along with metadata
    and warnings about unsupported features encountered during conversion.

    Attributes:
        markdown: Converted markdown content
        metadata: Additional metadata about the conversion (e.g., page info)
        warnings: List of warnings about unsupported macros or features
    """
    markdown: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
