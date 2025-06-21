import re
from typing import List

CLEAN_REGEX = re.compile(r"[\u00A0\n\r]+")

WHITESPACE_RE = re.compile(r"\s+")


def normalize_whitespace(text: str) -> str:
    """Collapse all whitespace (including non-breaking spaces) into single spaces."""
    text = CLEAN_REGEX.sub(" ", text)
    return WHITESPACE_RE.sub(" ", text).strip()


def chunk_list(items: List, chunk_size: int):
    """Yield successive chunks from a list."""
    for i in range(0, len(items), chunk_size):
        yield items[i : i + chunk_size] 