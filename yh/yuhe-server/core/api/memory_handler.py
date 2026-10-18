"""Internal memory management HTTP API (service-to-service).

Called by manager-api with ``Authorization: Bearer {server.secret}`` (same shared key as
the vision endpoint, see design §3.1). Paths are prefixed ``/api/memory`` and are
registered in ``core/http_server.py``.

All 8 endpoints from design §3.1:

- GET    /api/memory/agents
- GET    /api/memory/{agent_id}/facts
- GET    /api/memory/{agent_id}/facts/{fact_id}
- POST   /api/memory/{agent_id}/facts
- PUT    /api/memory/{agent_id}/facts/{fact_id}
- DELETE /api/memory/{agent_id}/facts/{fact_id}
- POST   /api/memory/{agent_id}/facts/{fact_id}/feedback
- POST   /api/memory/{agent_id}/facts/{fact_id}/review

Unified response envelope: ``{"code": int, "msg": str, "data": object|null}``, code=0 = success.
"""

import hmac
import json
from aiohttp import web
from core.api.base_handler import BaseHandler

TAG = __name__

# Design §5.2: approve restores trust to review_threshold + 0.2 (= 0.5)
_APPROVE_TRUST = 0.5
_DEFAULT_TRUST = 0.5
# Handler-side length caps (defense in depth): keyword is truncated, content is rejected.
_MAX_KEYWORD_LEN = 200
_MAX_CONTENT_LEN = 4000
# Status whitelist (design §5.1): anything else is a client error, not a silent default.
_VALID_STATUSES = ("active", "rejected")
_DEFAULT_DB_DIR = "data/memory/"


def _json_response(code: int, msg: str, data=None, status: int = 200) -> web.Response:
    body = json.dumps({"code": code, "msg": msg, "data": data}, ensure_ascii=False, separators=(",", ":"))
    response = web.Response(text=body, content_type="application/json", status=status)
    response.headers["Access-Control-Allow-Headers"] = "client-id, content-type, device-id, authorization"
    response.headers["Access-Control-Allow-Credentials"] = "true"
    response.headers["Access-Control-Allow-Origin"] = "*"
    return response


def _safe_agent_id(agent_id: str) -> str:
    """Reject path traversal (design §5.1): no '..', '/', '\\'; the id becomes a file name."""
    agent_id = (agent_id or "").strip()
    if not agent_id or any(sep in agent_id for sep in ("/", "\\")) or agent_id in (".", ".."):
        raise ValueError(f"非法 agent_id: {agent_id!r}")
    return agent_id


def _as_float(value, default=None):
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        raise ValueError("参数必须是数字")


def _as_int(value, default):
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValueError("参数必须是整数")


def _validate_status(status) -> str:
    """Whitelist the fact status at the handler boundary (design §5.1: active/rejected only)."""
    status = (status or "").strip()
    if status not in _VALID_STATUSES:
        raise ValueError("status 必须是 active 或 rejected")
    return status


class MemoryManageHandler(BaseHandler):
    def __init__(self, config: dict):
        super().__init__(config)
        # app.py:50-62 already resolved the three-tier auth_key (server.auth_key →
        # manager-api.secret → random) into config["server"]["auth_key"] before this
        # handler was constructed. We compare the RAW shared key, NOT a JWT: the vision
        # JWT is handed out to devices on connect, so accepting it here would let any
        # device manage every agent's memory (security review verdict).
        self._auth_key = (config.get("server", {}) or {}).get("auth_key") or ""

    def _verify_auth(self, request) -> bool:
        """Service-to-service auth: Authorization: Bearer {server.secret}.
        Constant-time comparison; an unresolvable (empty) key rejects everything."""
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return False
        token = auth_header[7:]
        return bool(self._auth_key) and hmac.compare_digest(token, self._auth_key)

    def _db_dir(self, request=None) -> str:
        """Resolve db_dir: request query param (Java passes the agent's model config value)
        takes precedence, falling back to the global mem_holographic config. This keeps the
        console API and the device link on the same directory (ten-probe audit B1 fix)."""
        from core.providers.memory.mem_holographic.mem_holographic import _resolve_db_dir
        if request is not None:
            requested = request.query.get("db_dir")
            if requested:
                return str(_resolve_db_dir(requested))
        configured = (self.config.get("Memory", {}) or {}).get("mem_holographic", {}) or {}
        return str(_resolve_db_dir(configured.get("db_dir", _DEFAULT_DB_DIR)))

    async def _handle(self, request, handler) -> web.Response:
        try:
            return await handler(request)
        except ValueError as e:
            self.logger.bind(tag=TAG).error(f"Memory API参数错误: {e}")
            return _json_response(400, str(e), None, status=400)
        except web.HTTPException:
            raise  # 404/405 etc. produced by handlers themselves pass through unchanged
        except Exception as e:
            self.logger.bind(tag=TAG).error(f"Memory API处理异常: {e}")
            return _json_response(500, "记忆服务不可用", None, status=500)

    def dispatch(self, handler):
        """Wrap a handler method for route registration so ValueError (validation,
        length caps, bad status, path traversal) maps to 400 instead of an aiohttp 500.
        Auth is enforced earlier by the loopback+Bearer middleware in http_server.py,
        so this wrapper only does error mapping."""
        async def _wrapped(request):
            return await self._handle(request, handler)
        return _wrapped

    # ---- Handlers ---------------------------------------------------------------------------

    async def handle_agents(self, request) -> web.Response:
        """GET /api/memory/agents — scan data/memory/*.db and report fact/pending counts."""
        from pathlib import Path
        from core.providers.memory.mem_holographic.mem_holographic import get_store
        db_dir = Path(self._db_dir(request))
        agents = []
        if db_dir.exists():
            for db_file in sorted(db_dir.glob("*.db")):
                agent_id = db_file.stem
                if not agent_id:
                    continue
                try:
                    store = get_store(agent_id, db_dir=str(db_dir))
                    # Ten-probe fix: pending threshold follows the configured min_trust_threshold
                    # (was hardcoded 0.3, drifting when admins raise the threshold).
                    threshold = None
                    mem_cfg = (self.config.get("Memory", {}) or {}).get("mem_holographic", {}) or {}
                    try:
                        threshold = float(mem_cfg.get("min_trust_threshold", 0.3))
                    except (TypeError, ValueError):
                        threshold = 0.3
                    agents.append({
                        "agent_id": agent_id,
                        "fact_count": store.count_facts(),
                        "pending_count": store.search_facts(
                            status="active", trust_max=threshold, page=1, size=1, sort_by="created"
                        )["total"],
                    })
                except Exception as e:
                    self.logger.bind(tag=TAG).error(f"扫描记忆库失败 {db_file}: {e}")
        return _json_response(0, "success", agents)

    async def handle_list_facts(self, request) -> web.Response:
        """GET /api/memory/{agent_id}/facts — paginated list with keyword/category/status/trust/time filters."""
        from core.providers.memory.mem_holographic.mem_holographic import get_store
        agent_id = _safe_agent_id(request.match_info.get("agent_id", ""))
        q = request.query
        keyword = (q.get("keyword", "") or "").strip()[:_MAX_KEYWORD_LEN]
        store = get_store(agent_id, db_dir=self._db_dir(request))
        result = store.search_facts(
            keyword=keyword,
            category=q.get("category") or None,
            status=q.get("status") or None,  # list filter: None = active-only default (store enforces)
            trust_min=_as_float(q.get("trust_min"), None),
            trust_max=_as_float(q.get("trust_max"), None),
            start=q.get("start") or None,
            end=q.get("end") or None,
            page=_as_int(q.get("page"), 1),
            size=_as_int(q.get("size"), 20),
            sort_by=q.get("sort_by", "created"),
            order=q.get("order", "desc"),
        )
        return _json_response(0, "success", result)

    async def handle_get_fact(self, request) -> web.Response:
        """GET /api/memory/{agent_id}/facts/{fact_id} — fact detail with entities."""
        from core.providers.memory.mem_holographic.mem_holographic import get_store
        agent_id = _safe_agent_id(request.match_info.get("agent_id", ""))
        store = get_store(agent_id, db_dir=self._db_dir(request))
        fact = store.get_fact(_as_int(request.match_info.get("fact_id"), 0))
        if fact is None:
            return _json_response(404, "记忆条目不存在", None, status=404)
        fact["entities"] = store.get_entities(fact["fact_id"])
        return _json_response(0, "success", fact)

    async def handle_create_fact(self, request) -> web.Response:
        """POST /api/memory/{agent_id}/facts — create (idempotent on duplicate content)."""
        from core.providers.memory.mem_holographic.mem_holographic import get_store
        agent_id = _safe_agent_id(request.match_info.get("agent_id", ""))
        body = await request.json()
        content = (body.get("content") or "").strip()
        if not content:
            raise ValueError("content 不能为空")
        if len(content) > _MAX_CONTENT_LEN:
            raise ValueError(f"内容过长（上限 {_MAX_CONTENT_LEN} 字符）")
        store = get_store(agent_id, db_dir=self._db_dir(request))
        fact_id = store.add_fact(
            content,
            category=body.get("category") or "general",
            tags=body.get("tags") or "",
            trust_score=_as_float(body.get("trust_score"), _DEFAULT_TRUST),
            status=_validate_status(body.get("status") or "active"),
            agent_id=agent_id,
            device_id=body.get("device_id") or "",
            session_id=body.get("session_id") or "",
        )
        fact = store.get_fact(fact_id)
        fact["entities"] = store.get_entities(fact_id)
        return _json_response(0, "success", fact)

    async def handle_update_fact(self, request) -> web.Response:
        """PUT /api/memory/{agent_id}/facts/{fact_id} — partial update; content change re-extracts entities."""
        from core.providers.memory.mem_holographic.mem_holographic import get_store
        agent_id = _safe_agent_id(request.match_info.get("agent_id", ""))
        fact_id = _as_int(request.match_info.get("fact_id"), 0)
        body = await request.json()
        store = get_store(agent_id, db_dir=self._db_dir(request))
        update_kwargs = {}
        if body.get("content") is not None:
            update_content = body["content"].strip()
            if len(update_content) > _MAX_CONTENT_LEN:
                raise ValueError(f"内容过长（上限 {_MAX_CONTENT_LEN} 字符）")
            update_kwargs["content"] = update_content
        if body.get("category") is not None:
            update_kwargs["category"] = body["category"]
        if body.get("tags") is not None:
            update_kwargs["tags"] = body["tags"]
        if body.get("status") is not None:
            update_kwargs["status"] = _validate_status(body["status"])
        if body.get("trust_score") is not None:
            update_kwargs["trust_score"] = _as_float(body["trust_score"], None)
        if not update_kwargs:
            raise ValueError("至少提供一个要更新的字段")
        if "trust_score" in update_kwargs:
            if not store.update_fact_trust(fact_id, update_kwargs.pop("trust_score")):
                return _json_response(404, "记忆条目不存在", None, status=404)
        if update_kwargs and not store.update_fact(fact_id, **update_kwargs):
            return _json_response(404, "记忆条目不存在", None, status=404)
        fact = store.get_fact(fact_id)
        fact["entities"] = store.get_entities(fact_id)
        return _json_response(0, "success", fact)

    async def handle_delete_fact(self, request) -> web.Response:
        """DELETE /api/memory/{agent_id}/facts/{fact_id} — physical delete."""
        from core.providers.memory.mem_holographic.mem_holographic import get_store
        agent_id = _safe_agent_id(request.match_info.get("agent_id", ""))
        store = get_store(agent_id, db_dir=self._db_dir(request))
        removed = store.remove_fact(_as_int(request.match_info.get("fact_id"), 0))
        if not removed:
            return _json_response(404, "记忆条目不存在", None, status=404)
        return _json_response(0, "success", {"removed": True})

    async def handle_feedback(self, request) -> web.Response:
        """POST /api/memory/{agent_id}/facts/{fact_id}/feedback — {helpful: bool} trust ±0.05/-0.10."""
        from core.providers.memory.mem_holographic.mem_holographic import get_store
        agent_id = _safe_agent_id(request.match_info.get("agent_id", ""))
        body = await request.json()
        helpful = bool(body.get("helpful", False))
        store = get_store(agent_id, db_dir=self._db_dir(request))
        try:
            result = store.record_feedback(_as_int(request.match_info.get("fact_id"), 0), helpful)
        except KeyError:
            return _json_response(404, "记忆条目不存在", None, status=404)
        return _json_response(0, "success", result)

    async def handle_review(self, request) -> web.Response:
        """POST /api/memory/{agent_id}/facts/{fact_id}/review — {action: approve|reject}.
        approve -> status=active and trust=0.5; reject -> status=rejected (design §3.1)."""
        from core.providers.memory.mem_holographic.mem_holographic import get_store
        agent_id = _safe_agent_id(request.match_info.get("agent_id", ""))
        fact_id = _as_int(request.match_info.get("fact_id"), 0)
        body = await request.json()
        action = body.get("action")
        if action not in ("approve", "reject"):
            raise ValueError("action 必须是 approve 或 reject")
        store = get_store(agent_id, db_dir=self._db_dir(request))
        if action == "approve":
            if not store.set_fact_status(fact_id, "active"):
                return _json_response(404, "记忆条目不存在", None, status=404)
            store.update_fact_trust(fact_id, _APPROVE_TRUST)
        else:
            if not store.set_fact_status(fact_id, "rejected"):
                return _json_response(404, "记忆条目不存在", None, status=404)
        fact = store.get_fact(fact_id)
        fact["entities"] = store.get_entities(fact_id)
        return _json_response(0, "success", fact)
