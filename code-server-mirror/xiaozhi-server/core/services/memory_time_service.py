"""Memory time-service layer: wraps MemoryStore with time-reference helpers.

Thin wrapper around ``MemoryStore`` that exposes timeline queries and
auto-associates time references when facts are created.
"""
import logging
from typing import List, Optional
from datetime import datetime

from core.providers.memory.mem_holographic.store import MemoryStore

TAG = __name__
logger = logging.getLogger(TAG)


class MemoryTimeService:
    """Time-dimension service on top of MemoryStore."""

    def __init__(self, store: MemoryStore):
        self.store = store

    # ---- Fact creation with time extraction --------------------------------------------------------

    def create_fact(self, content: str, category: str = "general",
                    tags: str = "", trust_score: Optional[float] = None,
                    status: str = "active", agent_id: str = "",
                    device_id: str = "", session_id: str = "") -> int:
        """Create a fact and attach extracted time references."""
        from .time_utils import extract_time_references
        fact_id = self.store.add_fact(
            content=content, category=category, tags=tags,
            trust_score=trust_score, status=status,
            agent_id=agent_id, device_id=device_id, session_id=session_id,
        )
        refs = extract_time_references(content)
        self.store.add_time_references(fact_id, refs)
        logger.info(f"Created fact {fact_id} with {len(refs)} time reference(s)")
        return fact_id

    # ---- Timeline queries --------------------------------------------------------------------------

    def get_timeline(self, from_time: Optional[str] = None, to_time: Optional[str] = None,
                     limit: int = 50, offset: int = 0) -> dict:
        """Return paginated timeline (facts + time references)."""
        return self.store.get_timeline(
            from_time=from_time, to_time=to_time,
            limit=limit, offset=offset,
        )

    def get_facts_by_date(self, date: str) -> list:
        """Return all active facts for a given YYYY-MM-DD string."""
        from datetime import timedelta
        start = f"{date}T00:00:00"
        end_dt = datetime.fromisoformat(start) + timedelta(days=1)
        end = end_dt.isoformat()
        result = self.store.search_facts(start=start, end=end)
        return result.get("items", [])

    def get_facts_by_time_range(self, from_time: str, to_time: str,
                                 limit: int = 50, offset: int = 0) -> dict:
        """Return facts in a time range with time references."""
        return self.store.get_timeline(
            from_time=from_time, to_time=to_time,
            limit=limit, offset=offset,
        )

    # ---- Time-reference management ------------------------------------------------------------------

    def add_time_references(self, fact_id: int,
                             refs: List[tuple]) -> None:
        self.store.add_time_references(fact_id, refs)

    def remove_time_references(self, fact_id: int) -> int:
        return self.store.remove_time_references(fact_id)

    def get_time_references(self, fact_id: int) -> list:
        return self.store.get_time_references(fact_id)
