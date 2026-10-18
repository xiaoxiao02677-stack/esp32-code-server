"""Entity graph API for holographic memory.

POST /api/memory/{agent_id}/entities/extract - Extract entities from text via LLM
GET  /api/memory/{agent_id}/entities - List entities for an agent
GET  /api/memory/{agent_id}/entities/graph - Get entity graph data
"""
import json
import logging
import hmac
from aiohttp import web
from core.api.base_handler import BaseHandler

TAG = __name__
logger = logging.getLogger(TAG)

# Max text length for extraction (prevent abuse)
MAX_TEXT_LEN = 2000
MAX_ENTITY_NAME_LEN = 100


def _json_response(code: int, msg: str, data=None, status: int = 200) -> web.Response:
    body = json.dumps({"code": code, "msg": msg, "data": data}, ensure_ascii=False, separators=(",", ":"))
    response = web.Response(text=body, content_type="application/json", status=status)
    return response


class EntityHandler(BaseHandler):
    def __init__(self, config: dict):
        super().__init__(config)
        self._auth_key = (config.get("server", {}) or {}).get("auth_key") or ""

    def _verify_auth(self, request) -> bool:
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return False
        token = auth_header[7:]
        return bool(self._auth_key) and hmac.compare_digest(token, self._auth_key)

    async def handle_extract_entities(self, request) -> web.Response:
        """Extract entities from conversation text using LLM."""
        if not self._verify_auth(request):
            return _json_response(401, "未授权")

        agent_id = request.match_info.get("agent_id", "")
        # agent_id validated by caller (no server-side restriction)

        try:
            body = await request.json()
            if not body or "text" not in body:
                return _json_response(400, "text 必填")

            text = body.get("text", "").strip()
            if len(text) > MAX_TEXT_LEN:
                return _json_response(400, f"文本超长（>{MAX_TEXT_LEN}字）")

            # Use LLM to extract entities and relations
            llm_config = body.get("llm_config", {})
            system_prompt = body.get("system_prompt", "请从对话中提取实体和关系，返回JSON格式")

            # Call LLM provider
            result = await self._extract_via_llm(text, system_prompt, llm_config)

            # Store entities in the store
            from core.providers.memory.mem_holographic.mem_holographic import get_store
            store = get_store(agent_id)
            entities = result.get("entities", [])
            relations = result.get("relations", [])

            for entity in entities:
                name = entity.get("name", "")[:MAX_ENTITY_NAME_LEN]
                entity_type = entity.get("type", "person")
                if name:
                    store._resolve_entity(name, entity_type)

            # Link entities to recent facts
            recent_facts = store.search_facts(keyword="", page=1, size=10)
            for fact in recent_facts.get("items", []):
                fact_id = fact.get("fact_id")
                content = fact.get("content", "")
                # Simple entity linking based on name matching
                for entity in entities:
                    name = entity.get("name", "")
                    if name and name in content:
                        entity_id = store._resolve_entity(name)
                        if entity_id:
                            store._conn.execute(
                                "INSERT OR REPLACE INTO fact_entities (fact_id, entity_id) VALUES (?, ?)",
                                (fact_id, entity_id)
                            )
            store._conn.commit()

            return _json_response(0, "success", result)

        except Exception as e:
            logger.error(f"Extract entities failed: {e}")
            return _json_response(500, f"提取失败: {str(e)}")

    async def handle_list_entities(self, request) -> web.Response:
        """List all entities for an agent."""
        if not self._verify_auth(request):
            return _json_response(401, "未授权")

        agent_id = request.match_info.get("agent_id", "")
        # agent_id validated by caller (no server-side restriction)

        try:
            from core.providers.memory.mem_holographic.mem_holographic import get_store
            store = get_store(agent_id)

            # Query entities with counts
            rows = []
            try:
                rows = store._conn.execute("""
                    SELECT e.name, e.entity_type, COUNT(fe.fact_id) as fact_count
                    FROM entities e
                    LEFT JOIN fact_entities fe ON e.entity_id = fe.entity_id
                    GROUP BY e.entity_id
                    ORDER BY fact_count DESC
                    LIMIT 200
                """).fetchall()
            except Exception as e:
                logger.error(f"DB error: {e}")

            entities = []
            for row in rows:
                if not row or len(row) < 2:
                    continue
                entities.append({
                    "name": row[0],
                    "type": row[1],
                    "fact_count": row[2] if len(row) > 2 else 0
                })

            return _json_response(0, "success", {"entities": entities, "total": len(entities)})

        except Exception as e:
            logger.error(f"List entities failed: {e}")
            return _json_response(500, f"查询失败: {str(e)}")

    async def handle_get_entity_graph(self, request) -> web.Response:
        """Get entity graph data for visualization."""
        if not self._verify_auth(request):
            return _json_response(401, "未授权")

        agent_id = request.match_info.get("agent_id", "")
        # agent_id validated by caller (no server-side restriction)

        try:
            from core.providers.memory.mem_holographic.mem_holographic import get_store
            store = get_store(agent_id)

            # Get nodes (entities)
            entities_rows = store._conn.execute("""
                SELECT e.entity_id, e.name, e.entity_type, COUNT(DISTINCT fe.fact_id) as importance
                FROM entities e
                LEFT JOIN fact_entities fe ON e.entity_id = fe.entity_id
                GROUP BY e.entity_id
                ORDER BY importance DESC
                LIMIT 100
            """).fetchall()

            nodes = []
            for row in entities_rows:
                nodes.append({
                    "id": str(row[0]),
                    "name": row[1],
                    "type": row[2],
                    "importance": row[3]
                })

            # Get edges (co-occurrence in facts)
            edges_rows = store._conn.execute("""
                SELECT e1.name as source, e2.name as target, COUNT(*) as weight
                FROM fact_entities fe1
                JOIN fact_entities fe2 ON fe1.fact_id = fe2.fact_id AND fe1.entity_id < fe2.entity_id
                JOIN entities e1 ON fe1.entity_id = e1.entity_id
                JOIN entities e2 ON fe2.entity_id = e2.entity_id
                GROUP BY fe1.entity_id, fe2.entity_id
                ORDER BY weight DESC
                LIMIT 200
            """).fetchall()

            edges = []
            for row in edges_rows:
                edges.append({
                    "source": row[0],
                    "target": row[1],
                    "weight": row[2]
                })

            return _json_response(0, "success", {"nodes": nodes, "edges": edges, "stats": {
                "entity_count": len(nodes),
                "relation_count": len(edges)
            }})

        except Exception as e:
            logger.error(f"Get entity graph failed: {e}")
            return _json_response(500, f"查询失败: {str(e)}")

    async def _extract_via_llm(self, text: str, system_prompt: str, llm_config: dict) -> dict:
        """Call LLM to extract entities and relations."""
        # Use existing LLM preview infrastructure
        from core.llm import LLMProviderFactory

        if not llm_config:
            # Return simple regex-based extraction as fallback
            return await self._extract_simple(text)

        try:
            provider = LLMProviderFactory.create(llm_config)
            user_prompt = f"""请从以下对话文本中提取实体和关系。
输出格式为JSON：
{{
  "entities": [{{"name": "实体名", "type": "类型(person/org/location/thing)"}}],
  "relations": [{{"subject": "主语", "predicate": "关系", "object": "宾语"}}]
}}

文本内容：
{text}"""

            response = await provider.complete(user_prompt, system_prompt=system_prompt, temperature=0.1)
            # Parse JSON response
            import re
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                return json.loads(json_match.group())

        except Exception as e:
            logger.warning(f"LLM extraction failed, using simple extraction: {e}")

        # Fallback to simple extraction
        return await self._extract_simple(text)

    async def _extract_simple(self, text: str) -> dict:
        """Simple regex-based entity extraction as fallback."""
        import re
        entities = []
        seen = set()

        # Person names (Chinese names: 2-3 characters, common surnames)
        surname_pattern = re.compile(r'[张王李陈杨黄周吴徐孙马朱胡郭何罗高梁郑谢唐许韩冯邓曹彭曾卢宋]')
        for match in surname_pattern.finditer(text):
            start = match.start()
            # Try to get 1-2 characters after surname
            end = min(start + 3, len(text))
            candidate = text[start:end].strip()
            if len(candidate) >= 2 and candidate not in seen and not any(c in candidate for c in '，。！？、'):
                entities.append({"name": candidate, "type": "person"})
                seen.add(candidate)

        # Locations (after 在/到/去 etc.)
        location_pattern = re.compile(r'(?:在|到|去|从)[\s：:]*([^\s，。！？、]{2,10})(?=[\s，。！？、])')
        for match in location_pattern.finditer(text):
            loc = match.group(1).strip()
            if loc not in seen and len(loc) >= 2:
                entities.append({"name": loc, "type": "location"})
                seen.add(loc)

        # Organizations (ends with 公司/学校/店 etc.)
        org_pattern = re.compile(r'([^\s，。！？、]+(?:公司|学校|店|局|院|厂))')
        for match in org_pattern.finditer(text):
            org = match.group(1).strip()
            if org not in seen:
                entities.append({"name": org, "type": "organization"})
                seen.add(org)

        return {
            "entities": entities[:20],  # Limit to 20 entities
            "relations": []
        }
