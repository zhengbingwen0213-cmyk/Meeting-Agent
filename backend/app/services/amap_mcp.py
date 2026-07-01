import json
import os
import math
import urllib.parse
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from app.config import Settings


PROXY_ENV_KEYS = {
    "http_proxy",
    "https_proxy",
    "all_proxy",
    "no_proxy",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "NO_PROXY",
}


@dataclass(frozen=True)
class GeoPoint:
    address: str
    lng: float
    lat: float
    formatted_address: str
    city: str
    level: str
    raw: dict[str, Any]
    via_mcp: bool
    fallback_reason: str


@dataclass(frozen=True)
class AmapRecommendationResult:
    recommendation: dict[str, Any]
    origin_a: GeoPoint
    origin_b: GeoPoint
    mcp_trace: dict[str, Any]


class AmapMcpError(Exception):
    def __init__(self, message: str, trace: Optional[dict[str, Any]] = None):
        super().__init__(message)
        self.trace = trace or {}


class AmapMcpClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def recommend_meeting_point(
        self,
        request_id: str,
        self_location: str,
        friend_location: str,
        city: str,
    ) -> AmapRecommendationResult:
        mcp_url = build_mcp_url(self.settings)
        resolved_city = city or self.settings.amap_geocode_default_city
        trace = build_trace(request_id, mcp_url, self.settings.amap_mcp_enabled, resolved_city)

        if not self.settings.amap_mcp_enabled:
            raise AmapMcpError("AMAP_MCP_ENABLED=false，已禁止高德 MCP 调用", trace)
        if not mcp_url:
            raise AmapMcpError("缺少高德 MCP 配置，请设置 AMAP_MCP_URL 或 AMAP_MAPS_API_KEY", trace)

        try:
            from mcp import ClientSession
            from mcp.client.streamable_http import streamable_http_client
        except ImportError as error:
            trace["steps"].append(failed_step("import_mcp_sdk", "本地缺少 mcp Python SDK"))
            raise AmapMcpError("本地缺少 mcp Python SDK，请安装 requirements.txt", trace) from error

        selected_tools: dict[str, str] = {}
        try:
            async with httpx.AsyncClient(timeout=self.settings.amap_mcp_timeout_seconds, trust_env=False) as http_client:
                async with streamable_http_client(mcp_url, http_client=http_client) as streams:
                    read_stream, write_stream, *_ = streams
                    async with ClientSession(read_stream, write_stream) as session:
                        await self._initialize(session, trace)
                        tools = await self._list_tools(session, trace)
                        selected_tools = select_tools(tools)
                        trace["selected_tools"] = selected_tools

                        origin_a = await self._geocode(
                            session,
                            trace,
                            selected_tools.get("geo", ""),
                            self_location,
                            resolved_city,
                        )
                        origin_b = await self._geocode(
                            session,
                            trace,
                            selected_tools.get("geo", ""),
                            friend_location,
                            resolved_city,
                        )

                        distance = await self._distance(
                            session,
                            trace,
                            selected_tools.get("distance", ""),
                            origin_a,
                            origin_b,
                        )
                        candidates = await self._search_candidates(
                            session,
                            trace,
                            selected_tools.get("around_search", ""),
                            selected_tools.get("text_search", ""),
                            origin_a,
                            origin_b,
                            resolved_city,
                        )
        except AmapMcpError:
            raise
        except Exception as error:
            trace["steps"].append(failed_step("mcp_connection", str(error)))
            if self.settings.amap_http_geocode_fallback and self.settings.amap_web_service_key:
                return self._recommend_with_rest_fallback(
                    trace,
                    self_location,
                    friend_location,
                    resolved_city,
                    f"高德 MCP 调用失败：{error}",
                )
            raise AmapMcpError(f"高德 MCP 调用失败：{error}", trace) from error

        recommendation = build_recommendation(origin_a, origin_b, distance, candidates)
        trace["normalized_result"] = {
            "origin_a": geocode_public_dict(origin_a),
            "origin_b": geocode_public_dict(origin_b),
            "distance": distance,
            "candidate_count": len(candidates),
            "recommendation": recommendation,
        }
        trace["finished_at"] = now_iso()
        trace["fallback_used"] = not origin_a.via_mcp or not origin_b.via_mcp
        trace["fallback_reason"] = "; ".join(
            reason for reason in [origin_a.fallback_reason, origin_b.fallback_reason] if reason
        )

        return AmapRecommendationResult(
            recommendation=recommendation,
            origin_a=origin_a,
            origin_b=origin_b,
            mcp_trace=trace,
        )

    async def _initialize(self, session: Any, trace: dict[str, Any]) -> None:
        step = started_step("initialize")
        try:
            await session.initialize()
            step["success"] = True
        except Exception as error:
            step["success"] = False
            step["error"] = str(error)
            trace["steps"].append(step)
            raise
        trace["steps"].append(step)

    async def _list_tools(self, session: Any, trace: dict[str, Any]) -> list[dict[str, Any]]:
        step = started_step("list_tools")
        try:
            result = await session.list_tools()
            raw = to_jsonable(result)
            tools = extract_tools(raw)
            step["success"] = True
            step["tools"] = [tool.get("name", "") for tool in tools]
            step["raw_response"] = raw
            step["raw_preview"] = preview_value(raw)
            trace["steps"].append(step)
            return tools
        except Exception as error:
            step["success"] = False
            step["error"] = str(error)
            trace["steps"].append(step)
            raise

    async def _geocode(
        self,
        session: Any,
        trace: dict[str, Any],
        tool_name: str,
        address: str,
        city: str,
    ) -> GeoPoint:
        if not address:
            raise AmapMcpError("DeepSeek 未提取到完整地址，无法调用高德地理编码", trace)

        if tool_name:
            arguments = {"address": address}
            if city:
                arguments["city"] = city
            raw = await call_tool_logged(session, trace, tool_name, arguments, self.settings.amap_mcp_timeout_seconds)
            point = normalize_geocode(raw, address, city, via_mcp=True, fallback_reason="")
            if point:
                return point

            trace["steps"].append(
                failed_step(
                    "parse_maps_geo",
                    "MCP 地理编码返回体未解析出经纬度",
                    {"address": address, "top_level_keys": top_level_keys(raw)},
                )
            )
            if not self.settings.amap_http_geocode_fallback:
                raise AmapMcpError("高德 MCP 地理编码结果解析失败，且未启用 REST 回退", trace)
            return self._geocode_with_rest(trace, address, city, "MCP 地理编码结果解析失败")

        if self.settings.amap_http_geocode_fallback:
            return self._geocode_with_rest(trace, address, city, "MCP 工具列表中未发现 maps_geo")

        raise AmapMcpError("MCP 工具列表中未发现 maps_geo，且未启用 REST 回退", trace)

    def _geocode_with_rest(self, trace: dict[str, Any], address: str, city: str, reason: str) -> GeoPoint:
        step = started_step("rest_geocode_fallback")
        step["fallback_reason"] = reason
        step["arguments_preview"] = {"address": address, "city": city}

        if not self.settings.amap_web_service_key:
            step["success"] = False
            step["error"] = "缺少 AMAP_WEB_SERVICE_KEY"
            trace["steps"].append(step)
            raise AmapMcpError("高德 REST 回退失败：缺少 AMAP_WEB_SERVICE_KEY", trace)

        params = {
            "key": self.settings.amap_web_service_key,
            "address": address,
        }
        if city:
            params["city"] = city
        step["server_receive_preview"] = {
            "method": "GET",
            "url_host": "http://restapi.amap.com/v3/geocode/geo",
            "params": {"address": address, "city": city},
        }

        try:
            raw = rest_get_json(
                "http://restapi.amap.com/v3/geocode/geo",
                params,
                self.settings.amap_mcp_timeout_seconds,
            )
        except httpx.HTTPStatusError as error:
            body = error.response.text
            step["success"] = False
            step["error"] = f"HTTP {error.response.status_code}: {body}"
            trace["steps"].append(step)
            raise AmapMcpError(f"高德 REST 地理编码 HTTP {error.response.status_code}", trace) from error
        except Exception as error:
            step["success"] = False
            step["error"] = str(error)
            trace["steps"].append(step)
            raise AmapMcpError(f"高德 REST 地理编码失败：{error}", trace) from error

        step["success"] = True
        step["raw_response"] = raw
        step["server_return_preview"] = preview_value(raw)
        trace["steps"].append(step)

        point = normalize_geocode(raw, address, city, via_mcp=False, fallback_reason=reason)
        if not point:
            raise AmapMcpError("高德 REST 地理编码未解析出经纬度", trace)
        return point

    def _recommend_with_rest_fallback(
        self,
        trace: dict[str, Any],
        self_location: str,
        friend_location: str,
        city: str,
        reason: str,
    ) -> AmapRecommendationResult:
        trace["fallback_used"] = True
        trace["fallback_reason"] = reason
        origin_a = self._geocode_with_rest(trace, self_location, city, reason)
        origin_b = self._geocode_with_rest(trace, friend_location, city, reason)
        distance = {
            "distance_text": format_distance_text(haversine_meters(origin_a.lng, origin_a.lat, origin_b.lng, origin_b.lat)),
            "duration_text": "",
            "raw": {},
            "via_mcp": False,
        }
        candidates = self._search_candidates_with_rest(trace, origin_a, origin_b)
        recommendation = build_recommendation(origin_a, origin_b, distance, candidates)
        trace["normalized_result"] = {
            "origin_a": geocode_public_dict(origin_a),
            "origin_b": geocode_public_dict(origin_b),
            "distance": distance,
            "candidate_count": len(candidates),
            "recommendation": recommendation,
        }
        trace["finished_at"] = now_iso()
        return AmapRecommendationResult(
            recommendation=recommendation,
            origin_a=origin_a,
            origin_b=origin_b,
            mcp_trace=trace,
        )

    def _search_candidates_with_rest(self, trace: dict[str, Any], origin_a: GeoPoint, origin_b: GeoPoint) -> list[dict[str, Any]]:
        step = started_step("rest_around_search_fallback")
        midpoint = midpoint_lng_lat(origin_a, origin_b)
        params = {
            "key": self.settings.amap_web_service_key,
            "keywords": self.settings.amap_meeting_keywords,
            "location": f"{midpoint[0]},{midpoint[1]}",
            "radius": str(self.settings.amap_search_radius),
        }
        step["arguments_preview"] = {
            "keywords": self.settings.amap_meeting_keywords,
            "location": params["location"],
            "radius": params["radius"],
        }
        step["server_receive_preview"] = {
            "method": "GET",
            "url_host": "http://restapi.amap.com/v3/place/around",
            "params": step["arguments_preview"],
        }
        try:
            raw = rest_get_json(
                "http://restapi.amap.com/v3/place/around",
                params,
                self.settings.amap_mcp_timeout_seconds,
            )
        except Exception as error:
            step["success"] = False
            step["error"] = str(error)
            trace["steps"].append(step)
            return []

        step["success"] = True
        step["raw_response"] = raw
        step["server_return_preview"] = preview_value(raw)
        trace["steps"].append(step)
        return normalize_pois(raw)

    async def _distance(
        self,
        session: Any,
        trace: dict[str, Any],
        tool_name: str,
        origin_a: GeoPoint,
        origin_b: GeoPoint,
    ) -> dict[str, Any]:
        if not tool_name:
            return {"distance_text": "待计算", "duration_text": "", "raw": {}, "via_mcp": False}

        arguments = {
            "origins": f"{origin_a.lng},{origin_a.lat}",
            "destination": f"{origin_b.lng},{origin_b.lat}",
            "type": self.settings.amap_mcp_distance_type,
        }
        raw = await call_tool_logged(session, trace, tool_name, arguments, self.settings.amap_mcp_timeout_seconds)
        return normalize_distance(raw)

    async def _search_candidates(
        self,
        session: Any,
        trace: dict[str, Any],
        around_tool: str,
        text_tool: str,
        origin_a: GeoPoint,
        origin_b: GeoPoint,
        city: str,
    ) -> list[dict[str, Any]]:
        midpoint = midpoint_lng_lat(origin_a, origin_b)
        if around_tool:
            arguments = {
                "location": f"{midpoint[0]},{midpoint[1]}",
                "keywords": self.settings.amap_meeting_keywords,
                "radius": str(self.settings.amap_search_radius),
            }
            raw = await call_tool_logged(session, trace, around_tool, arguments, self.settings.amap_mcp_timeout_seconds)
            candidates = normalize_pois(raw)
            if candidates:
                return candidates

        if text_tool:
            arguments = {"keywords": self.settings.amap_meeting_keywords}
            if city:
                arguments["city"] = city
            raw = await call_tool_logged(session, trace, text_tool, arguments, self.settings.amap_mcp_timeout_seconds)
            return normalize_pois(raw)

        return []


async def call_tool_logged(
    session: Any,
    trace: dict[str, Any],
    tool_name: str,
    arguments: dict[str, Any],
    timeout_seconds: int,
) -> dict[str, Any]:
    step = started_step("call_tool")
    step["tool"] = tool_name
    step["arguments_preview"] = arguments
    step["server_receive_preview"] = {"tool": tool_name, "arguments": arguments}

    try:
        result = await session.call_tool(tool_name, arguments=arguments)
        raw = to_jsonable(result)
        step["success"] = True
        step["raw_response"] = raw
        step["server_return_preview"] = preview_value(raw)
        trace["steps"].append(step)
        return raw
    except Exception as error:
        step["success"] = False
        step["error"] = str(error)
        trace["steps"].append(step)
        raise


def rest_get_json(url: str, params: dict[str, Any], timeout_seconds: int) -> dict[str, Any]:
    last_error: Optional[Exception] = None
    for attempt in range(3):
        try:
            with httpx.Client(timeout=timeout_seconds, trust_env=False) as client:
                response = client.get(url, params=params)
                response.raise_for_status()
                return response.json()
        except (httpx.ConnectError, httpx.RemoteProtocolError, httpx.ReadTimeout) as error:
            last_error = error
            if attempt < 2:
                time.sleep(0.5 * (attempt + 1))
                continue
            raise
    raise RuntimeError(f"高德 REST 请求失败：{last_error}")


def build_mcp_url(settings: Settings) -> str:
    if settings.amap_mcp_url:
        return settings.amap_mcp_url
    if settings.amap_maps_api_key:
        return f"https://mcp.amap.com/mcp?key={settings.amap_maps_api_key}"
    return ""


def build_trace(request_id: str, mcp_url: str, mcp_enabled: bool, city: str) -> dict[str, Any]:
    return {
        "request_id": request_id,
        "mcp_url_host": sanitize_mcp_url(mcp_url),
        "mcp_enabled": mcp_enabled,
        "city": city,
        "started_at": now_iso(),
        "steps": [],
        "selected_tools": {},
        "normalized_result": {},
        "fallback_used": False,
        "fallback_reason": "",
        "finished_at": "",
    }


def sanitize_mcp_url(url: str) -> str:
    if not url:
        return ""
    parsed = urllib.parse.urlparse(url)
    return urllib.parse.urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))


def select_tools(tools: list[dict[str, Any]]) -> dict[str, str]:
    names = [tool.get("name", "") for tool in tools]
    return {
        "geo": pick_tool(names, ["maps_geo"], include=["geo"], exclude=["regeo", "regeocode"]),
        "distance": pick_tool(names, ["maps_distance"], include=["distance"]),
        "around_search": pick_tool(names, ["maps_around_search"], include=["around", "search"]),
        "text_search": pick_tool(names, ["maps_text_search"], include=["text", "search"]),
    }


def pick_tool(names: list[str], preferred: list[str], include: list[str], exclude: Optional[list[str]] = None) -> str:
    exclude = exclude or []
    for name in preferred:
        if name in names:
            return name
    for name in names:
        lowered = name.lower()
        if all(item in lowered for item in include) and not any(item in lowered for item in exclude):
            return name
    return ""


def extract_tools(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, dict):
        tools = raw.get("tools")
        if isinstance(tools, list):
            return [tool for tool in tools if isinstance(tool, dict)]
    return []


def normalize_geocode(raw: dict[str, Any], address: str, city: str, via_mcp: bool, fallback_reason: str) -> Optional[GeoPoint]:
    payloads = extract_payloads(raw)
    candidates: list[dict[str, Any]] = []
    for payload in payloads:
        candidates.extend(extract_candidate_list(payload, ["geocodes", "results", "pois"]))

    if not candidates:
        candidates = [payload for payload in payloads if isinstance(payload, dict)]

    if city and len(candidates) > 1:
        city_match = [candidate for candidate in candidates if city in stringify(candidate.get("city", ""))]
        if city_match:
            candidates = city_match

    for candidate in candidates:
        location = candidate.get("location") or candidate.get("lnglat") or candidate.get("point")
        parsed = parse_lng_lat(location)
        if not parsed:
            parsed = parse_lng_lat(candidate)
        if parsed:
            return GeoPoint(
                address=address,
                lng=parsed[0],
                lat=parsed[1],
                formatted_address=first_string(
                    candidate,
                    ["formatted_address", "formattedAddress", "address", "name"],
                )
                or address,
                city=first_string(candidate, ["city", "adname", "province"]),
                level=first_string(candidate, ["level", "type"]),
                raw=candidate,
                via_mcp=via_mcp,
                fallback_reason=fallback_reason,
            )
    return None


def normalize_distance(raw: dict[str, Any]) -> dict[str, Any]:
    payloads = extract_payloads(raw)
    candidates: list[dict[str, Any]] = []
    for payload in payloads:
        candidates.extend(extract_candidate_list(payload, ["results", "route", "paths"]))

    candidate = candidates[0] if candidates else {}
    distance = first_string(candidate, ["distance"])
    duration = first_string(candidate, ["duration"])

    distance_text = ""
    if distance:
        try:
            meters = float(distance)
            distance_text = f"{meters / 1000:.1f} 公里" if meters >= 1000 else f"{int(meters)} 米"
        except ValueError:
            distance_text = distance

    duration_text = ""
    if duration:
        try:
            seconds = int(float(duration))
            duration_text = f"{seconds // 60} 分钟" if seconds >= 60 else f"{seconds} 秒"
        except ValueError:
            duration_text = duration

    return {
        "distance_text": distance_text or "已调用距离计算",
        "duration_text": duration_text,
        "raw": raw,
        "via_mcp": True,
    }


def normalize_pois(raw: dict[str, Any]) -> list[dict[str, Any]]:
    payloads = extract_payloads(raw)
    pois: list[dict[str, Any]] = []
    for payload in payloads:
        pois.extend(extract_candidate_list(payload, ["pois", "results", "data"]))

    candidates = []
    for poi in pois[:6]:
        if not isinstance(poi, dict):
            continue
        name = first_string(poi, ["name", "title", "poi_name"])
        if not name:
            continue
        candidates.append(
            {
                "name": name,
                "address": first_string(poi, ["address", "formatted_address", "pname"]),
                "distance": first_string(poi, ["distance"]),
                "location": first_string(poi, ["location"]),
                "raw": poi,
            }
        )
    return candidates


def build_recommendation(
    origin_a: GeoPoint,
    origin_b: GeoPoint,
    distance: dict[str, Any],
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    midpoint = midpoint_lng_lat(origin_a, origin_b)
    selected = candidates[0] if candidates else {}
    title = selected.get("name") or "两地中间位置"
    address = selected.get("address") or f"{midpoint[0]:.6f},{midpoint[1]:.6f}"

    geocode_source = "高德 MCP" if origin_a.via_mcp and origin_b.via_mcp else "高德 Web 服务回退"
    reasons = [
        f"已用{geocode_source}将两个地址解析为经纬度",
        "按两个坐标的中间位置计算会面范围",
    ]
    if candidates:
        reasons.append("已在中间位置附近搜索可会面地点")
    if distance.get("via_mcp"):
        reasons.append("已调用高德 MCP 计算两地距离")
    else:
        reasons.append("已用坐标计算两地直线距离")

    return {
        "title": title,
        "address": address,
        "summary": f"推荐在 {title} 附近会面。",
        "distance_text": distance.get("distance_text", "") or "待计算",
        "duration_text": distance.get("duration_text", "") or "",
        "reasons": reasons,
        "candidates": candidates,
        "midpoint": {"lng": midpoint[0], "lat": midpoint[1]},
    }


def extract_payloads(raw: Any) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    if isinstance(raw, dict):
        payloads.append(raw)
        structured = raw.get("structuredContent") or raw.get("structured_content")
        if isinstance(structured, dict):
            payloads.append(structured)
        content = raw.get("content")
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict):
                    text = item.get("text")
                    if isinstance(text, str):
                        parsed = parse_possible_json(text)
                        if isinstance(parsed, dict):
                            payloads.append(parsed)
    return payloads


def parse_possible_json(text: str) -> Any:
    cleaned = text.strip()
    if not cleaned:
        return None
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return None


def extract_candidate_list(payload: dict[str, Any], keys: list[str]) -> list[dict[str, Any]]:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            nested = extract_candidate_list(value, keys)
            if nested:
                return nested
    return []


def parse_lng_lat(value: Any) -> Optional[tuple[float, float]]:
    if isinstance(value, str) and "," in value:
        left, right = value.split(",", 1)
        try:
            return float(left), float(right)
        except ValueError:
            return None
    if isinstance(value, dict):
        lng = value.get("lng") or value.get("lon") or value.get("longitude")
        lat = value.get("lat") or value.get("latitude")
        if lng is not None and lat is not None:
            try:
                return float(lng), float(lat)
            except (TypeError, ValueError):
                return None
    return None


def midpoint_lng_lat(origin_a: GeoPoint, origin_b: GeoPoint) -> tuple[float, float]:
    return (origin_a.lng + origin_b.lng) / 2, (origin_a.lat + origin_b.lat) / 2


def haversine_meters(lng_a: float, lat_a: float, lng_b: float, lat_b: float) -> float:
    earth_radius = 6371000
    phi_a = math.radians(lat_a)
    phi_b = math.radians(lat_b)
    delta_phi = math.radians(lat_b - lat_a)
    delta_lambda = math.radians(lng_b - lng_a)
    value = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi_a) * math.cos(phi_b) * math.sin(delta_lambda / 2) ** 2
    )
    return earth_radius * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value))


def format_distance_text(meters: float) -> str:
    if meters >= 1000:
        return f"{meters / 1000:.1f} 公里"
    return f"{int(meters)} 米"


def geocode_public_dict(point: GeoPoint) -> dict[str, Any]:
    return {
        "address": point.address,
        "lng": point.lng,
        "lat": point.lat,
        "formatted_address": point.formatted_address,
        "city": point.city,
        "level": point.level,
        "via_mcp": point.via_mcp,
        "fallback_reason": point.fallback_reason,
    }


def to_jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [to_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [to_jsonable(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if hasattr(value, "__dict__"):
        return to_jsonable(value.__dict__)
    return str(value)


def preview_value(value: Any, max_text: int = 800) -> Any:
    text = json.dumps(to_jsonable(value), ensure_ascii=False, default=str)
    if len(text) <= max_text:
        return to_jsonable(value)
    return {"truncated": True, "text": text[:max_text]}


def started_step(name: str) -> dict[str, Any]:
    return {
        "name": name,
        "started_at": now_iso(),
        "success": False,
        "error": None,
    }


def failed_step(name: str, error: str, extra: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    step = started_step(name)
    step["success"] = False
    step["error"] = error
    if extra:
        step.update(extra)
    return step


def first_string(payload: dict[str, Any], keys: list[str]) -> str:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, (int, float)):
            return str(value)
    return ""


def stringify(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return ",".join(stringify(item) for item in value)
    return str(value)


def top_level_keys(value: Any) -> list[str]:
    if isinstance(value, dict):
        return list(value.keys())
    return []


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def clear_proxy_environment_variables() -> None:
    for key in PROXY_ENV_KEYS:
        os.environ.pop(key, None)
