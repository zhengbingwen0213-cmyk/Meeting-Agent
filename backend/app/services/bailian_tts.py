import base64
import json
import mimetypes
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

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
class TtsResult:
    audio_path: Path
    audio_bytes: bytes
    audio_mime: str
    raw_response: dict[str, Any]
    request_payload_preview: dict[str, Any]
    remote_audio_url: str
    delivery_mode: str


class BailianTtsError(Exception):
    pass


class BailianTtsClient:
    def __init__(self, settings: Settings):
        clear_proxy_environment_variables()
        self.settings = settings

    def synthesize_to_file(self, text: str, destination_stem: Path) -> TtsResult:
        clean_text = " ".join((text or "").split())
        if not self.settings.bailian_tts_enabled:
            raise BailianTtsError("百炼 TTS 当前已关闭，请检查 BAILIAN_TTS_ENABLED")
        if not self.settings.bailian_api_key:
            raise BailianTtsError("缺少 BAILIAN_API_KEY，请在 backend/.env 中配置百炼 API Key")
        if not clean_text:
            raise BailianTtsError("TTS 文本为空，无法合成语音")
        if len(clean_text) > self.settings.bailian_tts_max_text_chars:
            clean_text = clean_text[: self.settings.bailian_tts_max_text_chars]

        payload = self._build_payload(clean_text)
        response_json = self._post_json(payload)
        audio_url, audio_data = extract_audio_output(response_json)
        raw_response = response_json
        delivery_mode = "non_stream"

        if audio_data:
            audio_bytes, audio_mime = decode_audio_data(audio_data)
            remote_audio_url = ""
        elif audio_url:
            try:
                audio_bytes, audio_mime = self._download_audio(audio_url)
                remote_audio_url = audio_url
            except BailianTtsError as download_error:
                audio_bytes, audio_mime, stream_summary = self._stream_audio(payload)
                raw_response = {
                    "non_stream_response": response_json,
                    "non_stream_audio_download_error": str(download_error),
                    "stream_response_summary": stream_summary,
                }
                remote_audio_url = audio_url
                delivery_mode = "stream_fallback"
        else:
            raise BailianTtsError(f"百炼 TTS 响应中没有音频 URL 或音频数据: {json.dumps(response_json, ensure_ascii=False)[:500]}")

        audio_mime = audio_mime or guess_mime_from_url(audio_url) or "audio/wav"
        audio_path = resolve_audio_path(destination_stem, audio_mime, audio_url)
        audio_path.write_bytes(audio_bytes)

        return TtsResult(
            audio_path=audio_path,
            audio_bytes=audio_bytes,
            audio_mime=audio_mime,
            raw_response=raw_response,
            request_payload_preview=preview_payload(payload),
            remote_audio_url=remote_audio_url,
            delivery_mode=delivery_mode,
        )

    def _build_payload(self, text: str) -> dict[str, Any]:
        return {
            "model": self.settings.bailian_tts_model,
            "input": {
                "text": text,
                "voice": self.settings.bailian_tts_voice,
                "language_type": self.settings.bailian_tts_language_type,
            },
        }

    def _post_json(self, payload: dict[str, Any]) -> dict[str, Any]:
        response_body = ""
        last_error: Optional[Exception] = None
        for attempt in range(3):
            try:
                with httpx.Client(timeout=self.settings.bailian_tts_timeout_seconds, trust_env=False) as client:
                    response = client.post(
                        self.settings.bailian_tts_endpoint,
                        headers={
                            "Authorization": f"Bearer {self.settings.bailian_api_key}",
                            "Content-Type": "application/json",
                            "Accept": "application/json",
                        },
                        json=payload,
                    )
                    response_body = response.text
                    response.raise_for_status()
                    break
            except httpx.HTTPStatusError as error:
                raise BailianTtsError(
                    f"百炼 TTS HTTP {error.response.status_code}: {error.response.text}"
                ) from error
            except httpx.HTTPError as error:
                last_error = error
                if attempt < 2:
                    time.sleep(0.5 * (attempt + 1))
                    continue
                raise BailianTtsError(f"百炼 TTS 网络请求失败: {last_error}") from error

        try:
            response_json = json.loads(response_body)
        except json.JSONDecodeError as error:
            raise BailianTtsError(f"百炼 TTS 返回非 JSON 内容: {response_body[:500]}") from error

        if response_json.get("code") or response_json.get("message") and not response_json.get("output"):
            raise BailianTtsError(f"百炼 TTS 返回错误: {json.dumps(response_json, ensure_ascii=False)[:500]}")

        return response_json

    def _download_audio(self, url: str) -> tuple[bytes, str]:
        last_error: Optional[Exception] = None
        for attempt in range(3):
            try:
                with httpx.Client(timeout=self.settings.bailian_tts_timeout_seconds, trust_env=False, follow_redirects=True) as client:
                    response = client.get(url)
                    response.raise_for_status()
                    return response.content, normalize_mime(response.headers.get("content-type", ""))
            except httpx.HTTPError as error:
                last_error = error
                if attempt < 2:
                    time.sleep(0.5 * (attempt + 1))
                    continue
                raise BailianTtsError(f"百炼 TTS 音频下载失败: {last_error}") from error

        raise BailianTtsError("百炼 TTS 音频下载失败")

    def _stream_audio(self, payload: dict[str, Any]) -> tuple[bytes, str, dict[str, Any]]:
        audio_chunks: list[bytes] = []
        event_count = 0
        audio_chunk_count = 0
        request_id = ""
        final_event: dict[str, Any] = {}
        usage: dict[str, Any] = {}
        last_error: Optional[Exception] = None

        for attempt in range(3):
            try:
                with httpx.Client(timeout=self.settings.bailian_tts_timeout_seconds, trust_env=False) as client:
                    with client.stream(
                        "POST",
                        self.settings.bailian_tts_endpoint,
                        headers={
                            "Authorization": f"Bearer {self.settings.bailian_api_key}",
                            "Content-Type": "application/json",
                            "Accept": "text/event-stream",
                            "X-DashScope-SSE": "enable",
                        },
                        json=payload,
                    ) as response:
                        response.raise_for_status()
                        for line in response.iter_lines():
                            if not line or not line.startswith("data:"):
                                continue
                            data_line = line.removeprefix("data:").strip()
                            if not data_line or data_line == "[DONE]":
                                continue

                            event_count += 1
                            event_payload = json.loads(data_line)
                            request_id = string_value(event_payload.get("request_id")) or request_id
                            output = event_payload.get("output") if isinstance(event_payload, dict) else {}
                            if isinstance(event_payload.get("usage"), dict):
                                usage = event_payload["usage"]
                            if isinstance(output, dict):
                                final_event = strip_audio_data(event_payload)
                                audio = output.get("audio")
                                if isinstance(audio, dict):
                                    audio_data = string_value(audio.get("data"))
                                    if audio_data:
                                        audio_chunks.append(base64.b64decode(audio_data))
                                        audio_chunk_count += 1
                        break
            except (httpx.HTTPError, json.JSONDecodeError, ValueError) as error:
                last_error = error
                audio_chunks = []
                event_count = 0
                audio_chunk_count = 0
                final_event = {}
                usage = {}
                if attempt < 2:
                    time.sleep(0.5 * (attempt + 1))
                    continue
                raise BailianTtsError(f"百炼 TTS 流式合成失败: {last_error}") from error

        if not audio_chunks:
            raise BailianTtsError("百炼 TTS 流式合成没有返回音频数据")

        audio_bytes = b"".join(audio_chunks)
        return audio_bytes, "audio/wav", {
            "request_id": request_id,
            "event_count": event_count,
            "audio_chunk_count": audio_chunk_count,
            "audio_size_bytes": len(audio_bytes),
            "usage": usage,
            "final_event_without_audio_data": final_event,
        }


def clear_proxy_environment_variables() -> None:
    for key in PROXY_ENV_KEYS:
        os.environ.pop(key, None)


def extract_audio_output(response_json: dict[str, Any]) -> tuple[str, str]:
    output = response_json.get("output")
    if isinstance(output, dict):
        audio = output.get("audio")
        if isinstance(audio, dict):
            return string_value(audio.get("url")), string_value(audio.get("data"))

    return find_first_string(response_json, {"url", "audio_url"}), find_first_string(response_json, {"data", "audio_data"})


def find_first_string(payload: Any, keys: set[str]) -> str:
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key in keys and isinstance(value, str) and value.strip():
                return value.strip()
        for value in payload.values():
            found = find_first_string(value, keys)
            if found:
                return found
    elif isinstance(payload, list):
        for item in payload:
            found = find_first_string(item, keys)
            if found:
                return found
    return ""


def string_value(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def decode_audio_data(data: str) -> tuple[bytes, str]:
    audio_mime = ""
    encoded = data
    if data.startswith("data:") and "," in data:
        header, encoded = data.split(",", 1)
        audio_mime = header.removeprefix("data:").split(";", 1)[0]
    return base64.b64decode(encoded), audio_mime


def resolve_audio_path(destination_stem: Path, audio_mime: str, audio_url: str) -> Path:
    if destination_stem.suffix:
        return destination_stem

    extension = mimetypes.guess_extension(audio_mime.split(";", 1)[0]) if audio_mime else ""
    if extension in {".x-wav", ".wave"}:
        extension = ".wav"
    if not extension:
        extension = Path(urlparse(audio_url).path).suffix or ".wav"
    return destination_stem.with_suffix(extension)


def normalize_mime(content_type: str) -> str:
    normalized = content_type.split(";", 1)[0].strip().lower()
    if normalized in {"audio/x-wav", "audio/wave"}:
        return "audio/wav"
    return normalized


def guess_mime_from_url(url: str) -> str:
    if not url:
        return ""
    mime, _ = mimetypes.guess_type(urlparse(url).path)
    return mime or ""


def strip_audio_data(payload: dict[str, Any]) -> dict[str, Any]:
    cleaned = json.loads(json.dumps(payload, ensure_ascii=False))
    output = cleaned.get("output")
    if isinstance(output, dict):
        audio = output.get("audio")
        if isinstance(audio, dict) and isinstance(audio.get("data"), str):
            audio["data"] = f"<base64 audio chunk omitted, chars={len(audio['data'])}>"
    return cleaned


def preview_payload(payload: dict[str, Any]) -> dict[str, Any]:
    input_payload = payload.get("input", {})
    text = input_payload.get("text", "") if isinstance(input_payload, dict) else ""
    return {
        "model": payload.get("model", ""),
        "input": {
            "text_preview": text[:120] if isinstance(text, str) else "",
            "text_chars": len(text) if isinstance(text, str) else 0,
            "voice": input_payload.get("voice", "") if isinstance(input_payload, dict) else "",
            "language_type": input_payload.get("language_type", "") if isinstance(input_payload, dict) else "",
        },
    }
