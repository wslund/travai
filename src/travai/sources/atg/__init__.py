"""ATG-adapter - svensk trav från AB Trav och Galopp."""

from travai.sources.atg.adapter import AtgAdapter
from travai.sources.atg.client import ATGClient

__all__ = ["ATGClient", "AtgAdapter"]
