"""Datakällsadaptrar. Lägg till nya marknader genom att skapa ett nytt
sub-paket (t.ex. travai.sources.pmu) med en SourceAdapter-implementation.
"""

from travai.sources.base import SourceAdapter

__all__ = ["SourceAdapter"]
