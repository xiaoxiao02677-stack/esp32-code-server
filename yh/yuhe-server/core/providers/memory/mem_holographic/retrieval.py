"""Hybrid keyword/BM25 retrieval for the memory store: FTS5 candidates reranked with
Jaccard similarity and HRR vector similarity, trust-weighted (ported from KIK memory_agent.py).

Vendored from hermes-agent-main plugins/memory/holographic/retrieval.py for yuhe-server.
Adaptation is limited to the status workflow: every retrieval path (FTS5 candidates,
vector rows) filters ``status = 'active'`` so rejected facts are never injected into
conversations. All scoring math (weights 0.4/0.3/0.3, numpy-missing redistribution to
0.6/0.4/0, temporal decay, compositional probe/related/reason/contradict) is unchanged."""

from __future__ import annotations

import math
import re
from collections.abc import Callable
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .store import MemoryStore

from . import holographic as hrr

_FACT_COLUMNS = ("fact_id, content, category, tags, trust_score, status, agent_id, device_id, session_id, "
                 "retrieval_count, helpful_count, created_at, updated_at")
_ROLE_ENTITY, _ROLE_CONTENT = hrr.ROLE_ENTITY, hrr.ROLE_CONTENT
_PUNCT = ".,;:!?\"'()[]{}#@<>"
_FTS_OPERATORS = str.maketrans("", "", '"()*^:-+')
# Stopwords dropped before FTS5 OR-expansion: short English function words that
# carry no retrieval signal and force false-negative AND matches.
_FTS_STOPWORDS = frozenset("""
    a about above after again all am an and any are as at be because been before being between both but by can could
    did do does doing don down during each few for from further had has have having he her here hers herself him himself
    his how i if in into is it its itself just me more most my myself no nor not now of off on once only or other our
    ours ourselves out over own same she should so some such than that the their theirs them themselves then there these
    they this those through to too under until up very was we were what when where which while who whom why will with
    would you your yours yourself yourselves""".split())


def _shift(sim: float) -> float:
    """Cosine similarity [-1, 1] -> [0, 1]."""
    return (sim + 1.0) / 2.0


def _category_clause_cond(category: str | None) -> str:
    return "AND f.category = ? " if category else ""


class FactRetriever:
    """Multi-strategy fact retrieval with trust-weighted scoring."""

    def __init__(self, store: MemoryStore, temporal_decay_half_life: int = 0,  # days, 0 = disabled
                 fts_weight: float = 0.4, jaccard_weight: float = 0.3, hrr_weight: float = 0.3, hrr_dim: int = 1024):
        self.store, self.half_life, self.hrr_dim = store, temporal_decay_half_life, hrr_dim
        if hrr_weight > 0 and not hrr._HAS_NUMPY:  # redistribute weights without numpy
            fts_weight, jaccard_weight, hrr_weight = 0.6, 0.4, 0.0
        self.fts_weight, self.jaccard_weight, self.hrr_weight = fts_weight, jaccard_weight, hrr_weight

    def _atom(self, word: str):
        return hrr.encode_atom(word, self.hrr_dim)

    def _phases(self, blob: bytes):
        return hrr.bytes_to_phases(blob, dim=self.hrr_dim)

    def search(self, query: str, category: str | None = None, min_trust: float = 0.3, limit: int = 10) -> list[dict]:
        """FTS5 candidates (limit*3) → Jaccard + HRR rerank → trust weighting → optional temporal decay
        0.5^(age_days / half_life). Returns fact dicts with 'score', sorted desc. Only active facts ever
        become candidates, so rejected facts can never be injected."""
        candidates = self._fts_candidates(query, category, min_trust, limit * 3)
        query_tokens = self._tokenize(query)
        # Query vector is loop-invariant; encode lazily on the first candidate that carries an HRR vector
        # so stores whose hrr_vector was never backfilled don't pay for it.
        query_vec = None
        for fact in candidates:
            jaccard = self._jaccard_similarity(query_tokens, self._tokenize(fact["content"]) | self._tokenize(fact.get("tags", "")))
            hrr_sim = 0.5  # neutral
            if self.hrr_weight > 0 and fact.get("hrr_vector"):
                fact_vec = self._phases(fact["hrr_vector"])
                if query_vec is None:
                    query_vec = hrr.encode_text(query, self.hrr_dim)
                hrr_sim = _shift(hrr.similarity(query_vec, fact_vec))
            relevance = self.fts_weight * fact.get("fts_rank", 0.0) + self.jaccard_weight * jaccard + self.hrr_weight * hrr_sim
            fact["score"] = relevance * fact["trust_score"]
            if self.half_life > 0:
                fact["score"] *= self._temporal_decay(fact.get("updated_at") or fact.get("created_at"))
        results = sorted(candidates, key=lambda x: x["score"], reverse=True)[:limit]
        for fact in results:
            fact.pop("hrr_vector", None)  # callers expect JSON-serializable dicts
        return results

    def _vector_query(self, fallback: str, category: str | None, limit: int, sim_fn: Callable) -> list[dict]:
        """Rank every fact vector (optionally per category) by sim_fn; FTS5 fallback when no vectors exist."""
        rows = self._vector_rows(category)
        return self._rank_by_vector(rows, sim_fn, limit) if rows else self.search(fallback, category=category, limit=limit)

    def probe(self, entity: str, category: str | None = None, limit: int = 10) -> list[dict]:
        """Compositional entity query: unbind bind(entity, ROLE_ENTITY) from the category bank (or each fact vector)
        to find facts where the entity plays a structural role. Not keyword search. Falls back to FTS5 without numpy."""
        if not hrr._HAS_NUMPY:
            return self.search(entity, category=category, limit=limit)
        probe_key = hrr.bind(self._atom(entity.lower()), self._atom(_ROLE_ENTITY))
        if category:  # category bank first, then individual fact vectors
            bank_row = self.store._conn.execute("SELECT vector FROM memory_banks WHERE bank_name = ?", (f"cat:{category}",)).fetchone()
            if bank_row:
                extracted = hrr.unbind(self._phases(bank_row["vector"]), probe_key)
                return self._rank_by_vector(self._vector_rows(category), lambda _f, fact_vec: hrr.similarity(extracted, fact_vec), limit)
        role_content = self._atom(_ROLE_CONTENT)  # loop-invariant: encode once, not per row
        # Does unbinding the probe key leave the fact's content signal?
        return self._vector_query(entity, category, limit, lambda fact, fact_vec: hrr.similarity(
            hrr.unbind(fact_vec, probe_key), hrr.bind(hrr.encode_text(fact["content"], self.hrr_dim), role_content)))

    def related(self, entity: str, category: str | None = None, limit: int = 10) -> list[dict]:
        """Facts structurally connected to an entity (shared context), not just facts *about* it as in probe.
        Falls back to FTS5 without numpy."""
        if not hrr._HAS_NUMPY:
            return self.search(entity, category=category, limit=limit)
        entity_vec = self._atom(entity.lower())  # bare atom, not role-bound: ANY structural match
        roles = (self._atom(_ROLE_ENTITY), self._atom(_ROLE_CONTENT))  # loop-invariant: encode once
        # A residual similar to ANY role vector means the entity plays a structural role in the fact.
        return self._vector_query(entity, category, limit, lambda _f, fact_vec: max(
            hrr.similarity(hrr.unbind(fact_vec, entity_vec), role) for role in roles))

    def reason(self, entities: list[str], category: str | None = None, limit: int = 10) -> list[dict]:
        """Multi-entity compositional query (vector-space JOIN): facts where ALL entities play structural roles.
        Falls back to FTS5 without numpy."""
        if not hrr._HAS_NUMPY or not entities:
            return self.search(" ".join(entities), category=category, limit=limit)
        role_entity, role_content = self._atom(_ROLE_ENTITY), self._atom(_ROLE_CONTENT)
        probe_keys = [hrr.bind(self._atom(entity.lower()), role_entity) for entity in entities]
        # AND semantics via min: high only if EVERY entity is structurally present.
        return self._vector_query(" ".join(entities), category, limit, lambda _f, fact_vec: min(
            hrr.similarity(hrr.unbind(fact_vec, key), role_content) for key in probe_keys))

    def contradict(self, category: str | None = None, threshold: float = 0.3, limit: int = 10) -> list[dict]:
        """Pairs of facts sharing entities (same subject) with low content-vector similarity (different claims). Empty without numpy."""
        if not hrr._HAS_NUMPY:
            return []
        rows = self._vector_rows(category, columns="fact_id, content, category, tags, trust_score, status, created_at, updated_at, hrr_vector")
        if len(rows) < 2:
            return []
        if len(rows) > 500:  # O(n²) guard: only compare the most recently updated facts
            rows = sorted(rows, key=lambda r: r["updated_at"] or r["created_at"], reverse=True)[:500]
        facts = []  # (public dict, lower-cased entity names, phase vector)
        for row in rows:
            fact = dict(row)
            entity_rows = self.store._conn.execute(
                "SELECT e.name FROM entities e JOIN fact_entities fe ON fe.entity_id = e.entity_id WHERE fe.fact_id = ?",
                (fact["fact_id"],),
            ).fetchall()
            facts.append((fact, {r["name"].lower() for r in entity_rows}, self._phases(fact.pop("hrr_vector"))))
        contradictions = []
        for i, (f1, ents1, vec1) in enumerate(facts):
            for f2, ents2, vec2 in facts[i + 1:]:
                if not ents1 or not ents2:
                    continue
                entity_overlap = len(ents1 & ents2) / len(ents1 | ents2)
                if entity_overlap < 0.3:
                    continue  # not enough shared subject to be contradictory
                content_sim = hrr.similarity(vec1, vec2)
                contradiction_score = entity_overlap * (1.0 - _shift(content_sim))  # high overlap + low similarity
                if contradiction_score >= threshold:
                    contradictions.append({
                        "fact_a": f1, "fact_b": f2,
                        "entity_overlap": round(entity_overlap, 3),
                        "content_similarity": round(content_sim, 3),
                        "contradiction_score": round(contradiction_score, 3),
                        "shared_entities": sorted(ents1 & ents2),
                    })
        return sorted(contradictions, key=lambda x: x["contradiction_score"], reverse=True)[:limit]

    def _vector_rows(self, category: str | None, columns: str = _FACT_COLUMNS + ", hrr_vector") -> list:
        """All active facts that carry an HRR vector, optionally filtered by category."""
        where = "WHERE status = 'active' AND hrr_vector IS NOT NULL" + (" AND category = ?" if category else "")
        return self.store._conn.execute(f"SELECT {columns} FROM facts {where}", [category] if category else []).fetchall()

    def _rank_by_vector(self, rows: list, sim_fn: Callable[[dict, object], float], limit: int) -> list[dict]:
        """Score each row as (sim + 1) / 2 * trust_score (sim shifted to [0, 1]), sorted desc."""
        scored = [dict(row) for row in rows]
        for fact in scored:
            fact["score"] = _shift(sim_fn(fact, self._phases(fact.pop("hrr_vector")))) * fact["trust_score"]
        return sorted(scored, key=lambda x: x["score"], reverse=True)[:limit]

    def _fts_candidates(self, query: str, category: str | None, min_trust: float, limit: int) -> list[dict]:
        """Raw FTS5 MATCH candidates (active facts only) with rank normalized to [0, 1] as 'fts_rank'.

        unicode61 indexes a whole CJK run as ONE token, so a short Chinese query (e.g. 西瓜)
        never MATCHes against a longer run (我喜欢吃西瓜). For queries containing non-ASCII
        characters we therefore also pull a LIKE fallback candidate set and merge (dedup by
        fact_id) — Jaccard/HRR rerank then sorts out relevance exactly as for FTS hits."""
        category_clause = "AND f.category = ? " if category else ""
        params = [self._sanitize_fts_query(query)] + ([category] if category else []) + [min_trust, limit]
        sql = ("SELECT f.*, facts_fts.rank as fts_rank_raw FROM facts_fts JOIN facts f ON f.fact_id = facts_fts.rowid "
               f"WHERE facts_fts MATCH ? {category_clause}AND f.trust_score >= ? AND f.status = 'active' "
               "ORDER BY facts_fts.rank LIMIT ?")
        try:
            results = [dict(row) for row in self.store._conn.execute(sql, params).fetchall()]
        except Exception:
            results = []  # FTS5 MATCH can fail on malformed queries
        if any(ord(ch) > 127 for ch in query):
            results = self._merge_like_candidates(query, category, min_trust, limit, results)
        # FTS5 rank is negative (lower = better); normalize |rank| / max to [0, 1] (1e-6 floor avoids div by zero)
        max_rank = max([abs(f["fts_rank_raw"]) for f in results if "fts_rank_raw" in f] + [1e-6])
        for fact in results:
            if "fts_rank_raw" in fact:
                fact["fts_rank"] = abs(fact.pop("fts_rank_raw")) / max_rank
            else:
                fact["fts_rank"] = 0.0  # LIKE-fallback candidates carry no FTS rank signal
        return results

    def _merge_like_candidates(self, query: str, category: str | None, min_trust: float,
                               limit: int, fts_results: list[dict]) -> list[dict]:
        """Substring (LIKE) candidate backfill for non-ASCII queries, merged with FTS results.

        unicode61 indexes a whole CJK run as ONE token, so FTS can only hit when a query
        phrase exactly equals an indexed run. Recall therefore comes from LIKE needles:
        the whole query, then each CJK run's whole form and its 2-char sliding windows
        (喜欢什么歌 → 喜欢/欢什/什么/么歌; 喜欢 ⊂ 我喜欢听粤语歌). Needles are interleaved
        ACROSS runs (run1[0], run2[0], run1[1], run2[1], ...) so no single long run can
        monopolize the capped needle list — a long multi-topic query (你还记得我吗？我喜欢
        听什么音乐？) must keep bigrams from BOTH runs or its second topic loses all recall
        (qa-e2e A1 preview finding). Jaccard/HRR rerank sorts out relevance afterwards,
        exactly as for FTS hits. Both sets are active-only and trust-filtered; needle count
        and row count are capped."""
        runs = hrr.cjk_runs(query)
        needles: list[str] = []
        if query and query not in needles:
            needles.append(query)
        for run in runs:  # every run's whole form first — one scan each, before any bigrams
            if run not in needles:
                needles.append(run)
        # Interleaved bigrams, round-robin by position (run1[0], run2[0], run1[1], run2[1],
        # ...) so no single long run can monopolize the capped needle list — a multi-topic
        # query (你还记得我吗？我喜欢听什么音乐？) keeps bigrams from EVERY run and its
        # second topic stays recallable (qa-e2e A1 preview finding).
        max_bigrams = max((len(run) - 1 for run in runs), default=0)
        for i in range(max_bigrams):
            for run in runs:
                if i < len(run) - 1:
                    bigram = run[i] + run[i + 1]
                    if bigram not in needles:
                        needles.append(bigram)
        seen_ids = [f["fact_id"] for f in fts_results]

        def _esc(s: str) -> str:
            return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

        for needle in needles[:10]:  # bound the number of scans
            remaining = max(limit - len(seen_ids), 0)
            if remaining <= 0:
                break
            placeholders = ",".join(str(i) for i in seen_ids) or "0"
            params = ([f"%{_esc(needle)}%"] + ([category] if category else [])
                      + [min_trust, remaining])
            sql = (f"SELECT f.* FROM facts f WHERE f.content LIKE ? ESCAPE '\\' {_category_clause_cond(category)}"
                   f"AND f.trust_score >= ? AND f.status = 'active' "
                   f"AND f.fact_id NOT IN ({placeholders}) LIMIT ?")
            try:
                rows = [dict(row) for row in self.store._conn.execute(sql, params).fetchall()]
            except Exception:
                rows = []
            if rows:
                fts_results.extend(rows)
                seen_ids.extend(r["fact_id"] for r in rows)
        return fts_results

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        """Shared tokenizer (hrr.tokenize_text): lowercase whitespace tokens + overlapping
        CJK bigrams, so Chinese queries overlap the token sets of Chinese facts."""
        return set(hrr.tokenize_text(text))

    @staticmethod
    def _sanitize_fts_query(query: str) -> str:
        """Natural-language query -> FTS5-safe OR expression of quoted tokens. FTS5 AND-joins a multi-word
        MATCH by default, which tanks recall on prose: drop stopwords and <2-char tokens, strip FTS5 operator
        chars, phrase-quote each survivor. CJK handling: whole words do not intersect across run lengths
        (indexed run 我喜欢吃西瓜 is ONE token), so CJK runs are phrase-quoted AND decomposed into
        bigram phrases — a 2-char query (西瓜) then directly matches a 2+ char run in the index, and
        longer queries still get whole-run + bigram coverage. If nothing survives, return the raw query
        (zero results, not a SQL error)."""
        if not query:
            return ""
        phrases = []
        for raw in query.lower().split():
            cleaned = raw.strip(_PUNCT)
            if not cleaned:
                continue
            cjk = hrr.cjk_runs(cleaned)
            if cjk:
                for run in cjk:
                    phrases.append(f'"{run}"')
                    if len(run) > 2:  # 2-char runs are already exact bigrams
                        phrases.extend(f'"{run[i]}{run[i + 1]}"' for i in range(len(run) - 1))
            elif len(cleaned) >= 2 and cleaned.translate(_FTS_OPERATORS) not in _FTS_STOPWORDS:
                phrases.append(f'"{cleaned.translate(_FTS_OPERATORS)}"')
        return " OR ".join(phrases) if phrases else query

    @staticmethod
    def _jaccard_similarity(set_a: set, set_b: set) -> float:
        """Jaccard similarity coefficient: |A ∩ B| / |A ∪ B|."""
        return len(set_a & set_b) / len(set_a | set_b) if set_a and set_b else 0.0

    def _temporal_decay(self, timestamp_str: str | None) -> float:
        """0.5^(age_days / half_life); 1.0 if disabled, missing, unparseable, or in the future."""
        if not self.half_life or not timestamp_str:
            return 1.0
        try:
            ts = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00")) if isinstance(timestamp_str, str) else timestamp_str
            age_days = (datetime.now(timezone.utc) - (ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc))).total_seconds() / 86400
            return 1.0 if age_days < 0 else math.pow(0.5, age_days / self.half_life)
        except (ValueError, TypeError):
            return 1.0
