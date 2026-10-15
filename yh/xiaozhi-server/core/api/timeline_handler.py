"""HTTP API handlers for memory timeline endpoints.

New endpoints added to MemoryManageHandler (registered in core/http_server.py
under ``/api/memory/{agent_id}/timeline``):

- GET  /api/memory/{agent_id}/timeline          — paginated timeline view
- GET  /api/memory/{agent_id}/timeline/by-date  — facts for a specific date
- POST /api/memory/{agent_id}/facts/{fact_id}/times — attach time references
- DELETE /api/memory/{agent_id}/facts/{fact_id}/times — remove time references
- GET  /api/memory/{agent_id}/timeline/chart   — chart data for memory statistics
"""
import logging
from aiohttp import web
from core.api.base_handler import BaseHandler
from core.providers.memory.mem_holographic.store import MemoryStore
from core.providers.memory.mem_holographic.time_utils import extract_time_references

TAG = __name__

_MIN_LIMIT, _MAX_LIMIT = 1, 100


def _parse_iso_or_none(value: str | None):
    """Parse an ISO-8601 timestamp string, returning None if missing/empty."""
    if not value or not value.strip():
        return None
    return value.strip()


def _parse_int(value, default):
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValueError("参数必须是整数")


class TimelineHandler(BaseHandler):
    """Handles timeline-related memory endpoints."""

    def __init__(self, config: dict):
        super().__init__(config)
        self._db_dir = "data/memory/"  # default, can be overridden via query param

    def _get_store(self, agent_id: str, db_dir: str = None) -> MemoryStore:
        from core.providers.memory.mem_holographic.mem_holographic import get_store
        resolved_db_dir = db_dir or self._db_dir
        return get_store(agent_id, db_dir=resolved_db_dir)

    def _json_response(self, code: int, msg: str, data=None, status: int = 200) -> web.Response:
        import json
        body = json.dumps({"code": code, "msg": msg, "data": data}, ensure_ascii=False, separators=(",", ":"))
        response = web.Response(text=body, content_type="application/json", status=status)
        response.headers["Access-Control-Allow-Headers"] = "client-id, content-type, device-id, authorization"
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Allow-Origin"] = "*"
        return response

    async def _handle(self, request, handler) -> web.Response:
        try:
            return await handler(request)
        except ValueError as e:
            self.logger.bind(tag=TAG).error(f"Timeline API参数错误: {e}")
            return self._json_response(400, str(e), None, status=400)
        except web.HTTPException:
            raise
        except Exception as e:
            self.logger.bind(tag=TAG).error(f"Timeline API处理异常: {e}")
            return self._json_response(500, "记忆服务不可用", None, status=500)

    def dispatch(self, handler):
        """Wrap a handler method for route registration."""
        async def _wrapped(request):
            return await self._handle(request, handler)
        return _wrapped

    # ---- GET /api/memory/{agent_id}/timeline -------------------------------------------------------

    async def handle_list_timeline(self, request) -> web.Response:
        """Paginated timeline view with time references attached."""
        agent_id = request.match_info.get("agent_id", "")
        if not agent_id or any(sep in agent_id for sep in ("/", "\\")):
            return self._json_response(400, "非法 agent_id", None, status=400)

        db_dir = request.query.get("db_dir") or self._db_dir
        store = self._get_store(agent_id, db_dir=db_dir)

        q = request.query
        from_time = _parse_iso_or_none(q.get("from_time"))
        to_time = _parse_iso_or_none(q.get("to_time"))
        limit = _parse_int(q.get("limit"), 50)
        offset = _parse_int(q.get("offset"), 0)
        limit = max(_MIN_LIMIT, min(_MAX_LIMIT, limit))
        offset = max(0, offset)

        result = store.get_timeline(
            from_time=from_time, to_time=to_time,
            limit=limit, offset=offset,
        )
        return self._json_response(0, "success", result)

    # ---- GET /api/memory/{agent_id}/timeline/by-date -----------------------------------------------

    async def handle_list_by_date(self, request) -> web.Response:
        """All active facts for a specific YYYY-MM-DD date."""
        agent_id = request.match_info.get("agent_id", "")
        if not agent_id or any(sep in agent_id for sep in ("/", "\\")):
            return self._json_response(400, "非法 agent_id", None, status=400)

        date_str = request.match_info.get("date", "").strip()
        if not date_str:
            raise ValueError("date 参数不能为空")
        import re
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
            raise ValueError("date 格式必须是 YYYY-MM-DD")

        db_dir = request.query.get("db_dir") or self._db_dir
        store = self._get_store(agent_id, db_dir=db_dir)

        from datetime import datetime, timedelta
        start = f"{date_str}T00:00:00"
        end_dt = datetime.fromisoformat(start) + timedelta(days=1)
        end = end_dt.isoformat()

        result = store.search_facts(start=start, end=end)
        return self._json_response(0, "success", result)

    # ---- POST /api/memory/{agent_id}/facts/{fact_id}/times -----------------------------------------

    async def handle_add_times(self, request) -> web.Response:
        """Attach time references to a fact."""
        agent_id = request.match_info.get("agent_id", "")
        if not agent_id or any(sep in agent_id for sep in ("/", "\\")):
            return self._json_response(400, "非法 agent_id", None, status=400)

        db_dir = request.query.get("db_dir") or self._db_dir
        store = self._get_store(agent_id, db_dir=db_dir)
        fact_id = _parse_int(request.match_info.get("fact_id", ""), 0)

        body = await request.json()
        refs_input = body.get("references", [])
        if not refs_input:
            raise ValueError("references 不能为空")
        refs = [(str(r["time_reference"]), r.get("actual_date")) for r in refs_input]
        store.add_time_references(fact_id, refs)
        return self._json_response(0, "success", {"fact_id": fact_id, "added": len(refs)})

    # ---- DELETE /api/memory/{agent_id}/facts/{fact_id}/times ---------------------------------------

    async def handle_remove_times(self, request) -> web.Response:
        """Remove all time references for a fact."""
        agent_id = request.match_info.get("agent_id", "")
        if not agent_id or any(sep in agent_id for sep in ("/", "\\")):
            return self._json_response(400, "非法 agent_id", None, status=400)

        db_dir = request.query.get("db_dir") or self._db_dir
        store = self._get_store(agent_id, db_dir=db_dir)
        fact_id = _parse_int(request.match_info.get("fact_id", ""), 0)

        count = store.remove_time_references(fact_id)
        return self._json_response(0, "success", {"fact_id": fact_id, "removed": count})

    # ---- OPTIONS passthrough -----------------------------------------------------------------------

    async def handle_options(self, request):
        response = web.Response(body=b"", content_type="text/plain")
        response.headers["Access-Control-Allow-Headers"] = (
            "client-id, content-type, device-id, authorization"
        )
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, DELETE, OPTIONS"
        return response

    # ---- GET /api/memory/{agent_id}/timeline/chart --------------------------------------------------

    async def handle_chart(self, request) -> web.Response:
        """Return chart data for memory statistics (daily/weekly/monthly counts)."""
        try:
            agent_id = request.match_info.get("agent_id", "")
            if not agent_id or any(sep in agent_id for sep in ("/", "\\")):
                return self._json_response(400, "非法 agent_id", None, status=400)

            db_dir = request.query.get("db_dir") or self._db_dir
            store = self._get_store(agent_id, db_dir=db_dir)

            period = request.query.get("period", "daily")
            if period not in ("daily", "weekly", "monthly"):
                return self._json_response(400, "period 必须是 daily、weekly 或 monthly", None, status=400)

            from_date = _parse_iso_or_none(request.query.get("from_date"))
            to_date = _parse_iso_or_none(request.query.get("to_date"))

            result = store.get_chart_data(
                period=period,
                from_date=from_date,
                to_date=to_date,
            )
            return self._json_response(0, "success", result)
        except Exception as e:
            logger.error(f"Chart data error: {e}", exc_info=True)
            return self._json_response(500, f"图表数据错误: {str(e)}", None, status=500)
