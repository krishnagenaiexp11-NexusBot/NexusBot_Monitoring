"""
optimizer/walkforward.py
Thin re-export of research.walkforward for use within the optimizer package.
"""
from research.walkforward import split_walkforward  # noqa: F401

__all__ = ["split_walkforward"]
