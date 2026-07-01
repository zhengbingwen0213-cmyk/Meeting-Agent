import asyncio
import base64
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status

from app.config import get_settings
from app.services.amap_mcp import AmapMcpClient, AmapMcpError, geocode_public_dict
from app.services.bailian_asr import BailianAsrClient, BailianAsrError
from app.services.bailian_tts import BailianTtsClient, BailianTtsError
from app.services.deepseek_extractor import DeepSeekAddressExtractor, DeepSeekExtractionError


router = APIRouter()
settings = get_settings()
logger = logging.getLogger("meeting-point")


@router.get("/client-config")
async def client_config() -> dict:
    return {
        "amap": {
            "js_api_key": settings.amap_js_api_key,
            "security_js_code": settings.amap_js_security_code,
            "allow_without_security_js_code": settings.amap_js_allow_without_security_code,
            "enabled": bool(settings.amap_js_api_key),
        },
    }


@router.get("/meeting-point/history")
async def list_meeting_history(limit: int = 20) -> dict:
    storage_dir = settings.storage_dir
    storage_dir.mkdir(parents=True, exist_ok=True)
    items = []

    for path in sorted(storage_dir.glob("*_pipeline.json"), key=lambda item: item.stat().st_mtime, reverse=True)[:limit]:
        payload = read_json_file(path)
        if not payload:
            continue
        items.append(build_history_summary(path, payload, storage_dir))

    return {"items": items}


@router.get("/meeting-point/history/{request_id}")
async def get_meeting_history_detail(request_id: str) -> dict:
    storage_dir = settings.storage_dir
    storage_dir.mkdir(parents=True, exist_ok=True)

    for path in storage_dir.glob("*_pipeline.json"):
        payload = read_json_file(path)
        if payload.get("request_id") == request_id:
            return build_history_detail(path, payload, storage_dir)

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="没有找到这条历史记录",
    )


@router.post("/meeting-point/recommend", status_code=status.HTTP_201_CREATED)
async def save_meeting_audio(
    audio: UploadFile = File(...),
    client_timezone: Optional[str] = Form(default=None),
    client_recorded_at: Optional[str] = Form(default=None),
) -> dict:
    request_id = uuid4().hex
    storage_dir = settings.storage_dir
    storage_dir.mkdir(parents=True, exist_ok=True)
    logger.info("请求 %s：收到录音，准备保存", short_request_id(request_id))

    original_name = Path(audio.filename or "meeting-description.webm").name
    extension = Path(original_name).suffix or extension_from_content_type(audio.content_type)
    saved_stem = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{request_id}"
    saved_name = f"{saved_stem}{extension}"
    saved_path = storage_dir / saved_name

    size_bytes = await save_upload_file(audio, saved_path, settings.max_upload_bytes)
    relative_path = saved_path.relative_to(storage_dir.parent)
    asr_result_path = storage_dir / f"{saved_stem}_asr.json"
    extraction_result_path = storage_dir / f"{saved_stem}_deepseek.json"
    mcp_trace_path = storage_dir / f"{saved_stem}_amap_mcp.json"
    tts_result_path = storage_dir / f"{saved_stem}_tts.json"
    pipeline_result_path = storage_dir / f"{saved_stem}_pipeline.json"
    logger.info("请求 %s：音频已保存 %s，大小 %s 字节", short_request_id(request_id), relative_path, size_bytes)

    try:
        logger.info("请求 %s：开始百炼 ASR 识别", short_request_id(request_id))
        asr_result = await asyncio.to_thread(
            BailianAsrClient(settings).transcribe_file,
            saved_path,
            audio.content_type,
        )
        logger.info("请求 %s：ASR 输出：%s", short_request_id(request_id), preview_text(asr_result.transcript))
    except BailianAsrError as error:
        write_json_file(
            asr_result_path,
            {
                "request_id": request_id,
                "status": "failed",
                "error": str(error),
                "audio": {
                    "file_name": saved_name,
                    "relative_path": str(relative_path),
                    "size_bytes": size_bytes,
                    "content_type": audio.content_type or "",
                },
                "client": {
                    "timezone": client_timezone or "",
                    "recorded_at": client_recorded_at or "",
                },
            },
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"音频已保存，但百炼 ASR 识别失败：{error}",
        ) from error

    write_json_file(
        asr_result_path,
        {
            "request_id": request_id,
            "status": "succeeded",
            "transcript": asr_result.transcript,
            "request_payload_preview": asr_result.request_payload_preview,
            "raw_response": asr_result.raw_response,
            "audio": {
                "file_name": saved_name,
                "relative_path": str(relative_path),
                "size_bytes": size_bytes,
                "content_type": audio.content_type or "",
            },
            "client": {
                "timezone": client_timezone or "",
                "recorded_at": client_recorded_at or "",
            },
        },
    )
    asr_relative_path = asr_result_path.relative_to(storage_dir.parent)

    try:
        logger.info("请求 %s：开始 DeepSeek 地址提取", short_request_id(request_id))
        extraction_result = await asyncio.to_thread(
            DeepSeekAddressExtractor(settings).extract_addresses,
            asr_result.transcript,
        )
        write_json_file(
            extraction_result_path,
            {
                "request_id": request_id,
                "status": "succeeded",
                "transcript": asr_result.transcript,
                "slots": {
                    "self_location": extraction_result.self_location,
                    "friend_location": extraction_result.friend_location,
                    "city": extraction_result.city,
                    "confidence": extraction_result.confidence,
                    "missing_fields": extraction_result.missing_fields,
                    "normalized_query": extraction_result.normalized_query,
                    "notes": extraction_result.notes,
                },
                "request_payload_preview": extraction_result.request_payload_preview,
                "raw_response": extraction_result.raw_response,
            },
        )
        logger.info(
            "请求 %s：DeepSeek 提取完成，你=%s，朋友=%s，城市=%s",
            short_request_id(request_id),
            extraction_result.self_location or "空",
            extraction_result.friend_location or "空",
            extraction_result.city or settings.amap_geocode_default_city or "空",
        )
        validate_extracted_locations(extraction_result)
    except DeepSeekExtractionError as error:
        write_json_file(
            extraction_result_path,
            {
                "request_id": request_id,
                "status": "failed",
                "transcript": asr_result.transcript,
                "error": str(error),
            },
        )
        logger.info("请求 %s：DeepSeek 提取失败：%s", short_request_id(request_id), error)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"ASR 已完成，但 DeepSeek 地址提取失败：{error}",
        ) from error

    try:
        logger.info("请求 %s：开始连接高德 MCP Server", short_request_id(request_id))
        amap_result = await AmapMcpClient(settings).recommend_meeting_point(
            request_id,
            extraction_result.self_location,
            extraction_result.friend_location,
            extraction_result.city,
        )
        write_json_file(mcp_trace_path, amap_result.mcp_trace)
        logger.info(
            "请求 %s：高德 MCP 完成，推荐=%s，地址=%s",
            short_request_id(request_id),
            amap_result.recommendation.get("title", ""),
            amap_result.recommendation.get("address", ""),
        )
    except AmapMcpError as error:
        if error.trace:
            error.trace["finished_at"] = datetime.now(timezone.utc).isoformat()
            write_json_file(mcp_trace_path, error.trace)
        logger.info("请求 %s：高德 MCP 失败：%s", short_request_id(request_id), error)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"DeepSeek 地址提取已完成，但高德 MCP 调用失败：{error}",
        ) from error

    answer_text = build_answer_text(amap_result.recommendation)
    try:
        logger.info("请求 %s：开始百炼 TTS 语音合成", short_request_id(request_id))
        tts_result = await asyncio.to_thread(
            BailianTtsClient(settings).synthesize_to_file,
            answer_text,
            storage_dir / f"{saved_stem}_tts",
        )
        tts_audio_relative_path = tts_result.audio_path.relative_to(storage_dir.parent)
        write_json_file(
            tts_result_path,
            {
                "request_id": request_id,
                "status": "succeeded",
                "answer_text": answer_text,
                "audio": {
                    "relative_path": str(tts_audio_relative_path),
                    "size_bytes": len(tts_result.audio_bytes),
                    "content_type": tts_result.audio_mime,
                    "remote_audio_url": tts_result.remote_audio_url,
                    "delivery_mode": tts_result.delivery_mode,
                },
                "request_payload_preview": tts_result.request_payload_preview,
                "raw_response": tts_result.raw_response,
            },
        )
        audio_base64 = base64.b64encode(tts_result.audio_bytes).decode("ascii")
        audio_mime = tts_result.audio_mime
        logger.info(
            "请求 %s：TTS 完成，音频=%s，大小 %s 字节",
            short_request_id(request_id),
            tts_audio_relative_path,
            len(tts_result.audio_bytes),
        )
    except BailianTtsError as error:
        write_json_file(
            tts_result_path,
            {
                "request_id": request_id,
                "status": "failed",
                "answer_text": answer_text,
                "error": str(error),
            },
        )
        logger.info("请求 %s：百炼 TTS 失败：%s", short_request_id(request_id), error)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"地点推荐已完成，但百炼 TTS 语音合成失败：{error}",
        ) from error

    pipeline_payload = {
        "request_id": request_id,
        "status": "succeeded",
        "transcript": asr_result.transcript,
        "slots": {
            "self_location": extraction_result.self_location,
            "friend_location": extraction_result.friend_location,
            "city": extraction_result.city,
        },
        "geocoding": {
            "origin_a": geocode_public_dict(amap_result.origin_a),
            "origin_b": geocode_public_dict(amap_result.origin_b),
        },
        "recommendation": amap_result.recommendation,
        "map": build_map_payload(amap_result),
        "tts": {
            "answer_text": answer_text,
            "audio_relative_path": str(tts_audio_relative_path),
            "audio_mime": audio_mime,
            "delivery_mode": tts_result.delivery_mode,
        },
        "storage": {
            "audio_relative_path": str(relative_path),
            "asr_relative_path": str(asr_relative_path),
            "deepseek_relative_path": str(extraction_result_path.relative_to(storage_dir.parent)),
            "amap_mcp_relative_path": str(mcp_trace_path.relative_to(storage_dir.parent)),
            "tts_relative_path": str(tts_result_path.relative_to(storage_dir.parent)),
            "tts_audio_relative_path": str(tts_audio_relative_path),
        },
    }
    write_json_file(pipeline_result_path, pipeline_payload)
    logger.info("请求 %s：完整链路完成", short_request_id(request_id))

    return {
        "request_id": request_id,
        "transcript": asr_result.transcript,
        "slots": {
            "self_location": extraction_result.self_location,
            "friend_location": extraction_result.friend_location,
            "city": extraction_result.city,
        },
        "answer_text": answer_text,
        "audio_url": "",
        "audio_base64": audio_base64,
        "audio_mime": audio_mime,
        "geocoding": {
            "origin_a": geocode_public_dict(amap_result.origin_a),
            "origin_b": geocode_public_dict(amap_result.origin_b),
        },
        "map": build_map_payload(amap_result),
        "recommendation": amap_result.recommendation,
        "storage": {
            "file_name": saved_name,
            "relative_path": str(relative_path),
            "asr_relative_path": str(asr_relative_path),
            "deepseek_relative_path": str(extraction_result_path.relative_to(storage_dir.parent)),
            "amap_mcp_relative_path": str(mcp_trace_path.relative_to(storage_dir.parent)),
            "tts_relative_path": str(tts_result_path.relative_to(storage_dir.parent)),
            "tts_audio_relative_path": str(tts_audio_relative_path),
            "pipeline_relative_path": str(pipeline_result_path.relative_to(storage_dir.parent)),
            "size_bytes": size_bytes,
            "content_type": audio.content_type or "",
            "client_timezone": client_timezone or "",
            "client_recorded_at": client_recorded_at or "",
        },
    }


async def save_upload_file(upload: UploadFile, destination: Path, max_bytes: int) -> int:
    size_bytes = 0

    try:
        with destination.open("wb") as output_file:
            while chunk := await upload.read(1024 * 1024):
                size_bytes += len(chunk)
                if size_bytes > max_bytes:
                    destination.unlink(missing_ok=True)
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"音频文件超过大小限制，当前限制为 {max_bytes // 1024 // 1024} MB",
                    )
                output_file.write(chunk)
    finally:
        await upload.close()

    if size_bytes == 0:
        destination.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="音频文件为空",
        )

    return size_bytes


def validate_extracted_locations(extraction_result) -> None:
    if extraction_result.self_location and extraction_result.friend_location:
        return

    missing_fields = set(getattr(extraction_result, "missing_fields", []) or [])
    if not extraction_result.self_location:
        missing_fields.add("self_location")
    if not extraction_result.friend_location:
        missing_fields.add("friend_location")

    if {"self_location", "friend_location"}.issubset(missing_fields):
        detail = "没有识别到两个地点，请重新录音并说清楚“我在...，朋友在...”"
    elif "self_location" in missing_fields:
        detail = "没有识别到你的位置，请重新录音并说清楚“我在...”"
    else:
        detail = "没有识别到朋友的位置，请重新录音并说清楚“朋友在...”"

    raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=detail)


def extension_from_content_type(content_type: Optional[str]) -> str:
    if not content_type:
        return ".webm"
    if "mp4" in content_type:
        return ".m4a"
    if "mpeg" in content_type:
        return ".mp3"
    if "ogg" in content_type:
        return ".ogg"
    if "wav" in content_type:
        return ".wav"
    return ".webm"


def write_json_file(path: Path, payload: dict) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def read_json_file(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def build_history_summary(path: Path, payload: dict, storage_dir: Path) -> dict:
    slots = payload.get("slots") if isinstance(payload.get("slots"), dict) else {}
    recommendation = payload.get("recommendation") if isinstance(payload.get("recommendation"), dict) else {}
    transcript = payload.get("transcript", "")
    return {
        "request_id": payload.get("request_id", ""),
        "created_at": created_at_from_pipeline_path(path),
        "title": recommendation.get("title", "") or "历史推荐",
        "address": recommendation.get("address", ""),
        "distance_text": recommendation.get("distance_text", ""),
        "transcript_preview": preview_text(transcript, 42),
        "self_location": slots.get("self_location", ""),
        "friend_location": slots.get("friend_location", ""),
        "pipeline_relative_path": str(path.relative_to(storage_dir.parent)),
    }


def build_history_detail(path: Path, payload: dict, storage_dir: Path) -> dict:
    recommendation = sanitize_recommendation(payload.get("recommendation") or {})
    tts = payload.get("tts") if isinstance(payload.get("tts"), dict) else {}
    storage = payload.get("storage") if isinstance(payload.get("storage"), dict) else {}
    audio_base64, audio_mime = read_history_audio(storage, tts, storage_dir)
    return {
        "request_id": payload.get("request_id", ""),
        "transcript": payload.get("transcript", ""),
        "slots": payload.get("slots", {}),
        "answer_text": tts.get("answer_text") or build_answer_text(recommendation),
        "audio_url": "",
        "audio_base64": audio_base64,
        "audio_mime": audio_mime,
        "geocoding": payload.get("geocoding", {}),
        "map": payload.get("map", {}),
        "recommendation": recommendation,
        "history": {
            "created_at": created_at_from_pipeline_path(path),
            "pipeline_relative_path": str(path.relative_to(storage_dir.parent)),
        },
        "storage": {
            **storage,
            "pipeline_relative_path": str(path.relative_to(storage_dir.parent)),
        },
    }


def sanitize_recommendation(recommendation: dict) -> dict:
    cleaned = dict(recommendation) if isinstance(recommendation, dict) else {}
    candidates = cleaned.get("candidates")
    if isinstance(candidates, list):
        cleaned["candidates"] = [
            {
                "name": item.get("name", ""),
                "address": item.get("address", ""),
                "distance": item.get("distance", ""),
                "location": item.get("location", ""),
            }
            for item in candidates
            if isinstance(item, dict)
        ]
    return cleaned


def read_history_audio(storage: dict, tts: dict, storage_dir: Path) -> tuple[str, str]:
    relative_path = storage.get("tts_audio_relative_path") or tts.get("audio_relative_path") or ""
    if not isinstance(relative_path, str) or not relative_path:
        return "", tts.get("audio_mime", "") if isinstance(tts.get("audio_mime"), str) else ""

    audio_path = resolve_storage_relative_path(relative_path, storage_dir)
    if not audio_path or not audio_path.exists() or not audio_path.is_file():
        return "", tts.get("audio_mime", "") if isinstance(tts.get("audio_mime"), str) else ""

    try:
        audio_bytes = audio_path.read_bytes()
    except OSError:
        return "", tts.get("audio_mime", "") if isinstance(tts.get("audio_mime"), str) else ""

    return base64.b64encode(audio_bytes).decode("ascii"), tts.get("audio_mime", "") or "audio/wav"


def resolve_storage_relative_path(relative_path: str, storage_dir: Path) -> Optional[Path]:
    storage_parent = storage_dir.parent.resolve()
    candidate = (storage_parent / relative_path).resolve()
    try:
        candidate.relative_to(storage_parent)
    except ValueError:
        return None
    return candidate


def created_at_from_pipeline_path(path: Path) -> str:
    timestamp = path.name.split("_", 1)[0]
    try:
        parsed = datetime.strptime(timestamp, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()
    return parsed.isoformat()


def preview_text(text: str, limit: int = 80) -> str:
    normalized = " ".join((text or "").split())
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[:limit]}..."


def short_request_id(request_id: str) -> str:
    return request_id[:8]


def build_answer_text(recommendation: dict) -> str:
    title = recommendation.get("title") or "推荐地点"
    address = recommendation.get("address") or "地址待确认"
    distance_text = recommendation.get("distance_text") or "距离待计算"
    return f"推荐你们在 {title} 附近见面，地址是 {address}。两地距离参考：{distance_text}。"


def build_map_payload(amap_result) -> dict:
    recommendation = amap_result.recommendation
    meeting_location = first_candidate_location(recommendation) or recommendation.get("midpoint") or {}
    return {
        "origin_a": geocode_public_dict(amap_result.origin_a),
        "origin_b": geocode_public_dict(amap_result.origin_b),
        "meeting_point": {
            "title": recommendation.get("title", ""),
            "address": recommendation.get("address", ""),
            "lng": meeting_location.get("lng"),
            "lat": meeting_location.get("lat"),
        },
    }


def first_candidate_location(recommendation: dict) -> dict:
    candidates = recommendation.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        return {}
    location = candidates[0].get("location") if isinstance(candidates[0], dict) else ""
    if not isinstance(location, str) or "," not in location:
        return {}
    lng, lat = location.split(",", 1)
    try:
        return {"lng": float(lng), "lat": float(lat)}
    except ValueError:
        return {}
