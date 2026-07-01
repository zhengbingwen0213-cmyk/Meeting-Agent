import base64
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
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
class AsrResult:
    transcript: str
    raw_response: dict[str, Any]
    request_payload_preview: dict[str, Any]


class BailianAsrError(Exception):
    pass


class BailianAsrClient:
    def __init__(self, settings: Settings):
        clear_proxy_environment_variables()
        self.settings = settings

    def transcribe_file(self, audio_path: Path, content_type: Optional[str]) -> AsrResult:
        if not self.settings.bailian_api_key:
            raise BailianAsrError("缺少 BAILIAN_API_KEY，请在 backend/.env 中配置百炼 API Key")

        audio_bytes = audio_path.read_bytes()
        data_uri = build_audio_data_uri(audio_bytes, content_type or "audio/webm")
        if len(data_uri.encode("utf-8")) > self.settings.bailian_asr_max_audio_base64_bytes:
            limit_mb = self.settings.bailian_asr_max_audio_base64_bytes // 1024 // 1024
            raise BailianAsrError(f"Base64 后音频超过百炼 ASR 输入限制，当前限制为 {limit_mb} MB")

        payload = self._build_payload(data_uri)
        response_json = self._post_json(payload)
        transcript = extract_transcript(response_json)

        return AsrResult(
            transcript=transcript,
            raw_response=response_json,
            request_payload_preview=preview_payload(payload, len(audio_bytes), content_type or ""),
        )

    def _build_payload(self, data_uri: str) -> dict[str, Any]:
        messages: list[dict[str, Any]] = []
        if self.settings.bailian_asr_system_prompt:
            messages.append({"role": "system", "content": self.settings.bailian_asr_system_prompt})

        asr_options: dict[str, Any] = {
            "enable_itn": self.settings.bailian_asr_enable_itn,
        }
        if self.settings.bailian_asr_language:
            asr_options["language"] = self.settings.bailian_asr_language

        messages.append(
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_audio",
                        "input_audio": {
                            "data": data_uri,
                        },
                    }
                ],
            }
        )

        return {
            "model": self.settings.bailian_asr_model,
            "messages": messages,
            "stream": False,
            "asr_options": asr_options,
        }

    def _post_json(self, payload: dict[str, Any]) -> dict[str, Any]:
        response_body = ""
        last_error: Optional[Exception] = None
        for attempt in range(3):
            try:
                with httpx.Client(timeout=self.settings.bailian_asr_timeout_seconds, trust_env=False) as client:
                    response = client.post(
                        self.settings.bailian_asr_endpoint,
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
                raise BailianAsrError(
                    f"百炼 ASR HTTP {error.response.status_code}: {error.response.text}"
                ) from error
            except httpx.HTTPError as error:
                last_error = error
                if attempt < 2:
                    time.sleep(0.5 * (attempt + 1))
                    continue
                raise BailianAsrError(f"百炼 ASR 网络请求失败: {last_error}") from error

        try:
            return json.loads(response_body)
        except json.JSONDecodeError as error:
            raise BailianAsrError(f"百炼 ASR 返回非 JSON 内容: {response_body[:500]}") from error


def clear_proxy_environment_variables() -> None:
    for key in PROXY_ENV_KEYS:
        os.environ.pop(key, None)


def build_audio_data_uri(audio_bytes: bytes, content_type: str) -> str:
    encoded_audio = base64.b64encode(audio_bytes).decode("ascii")
    return f"data:{content_type};base64,{encoded_audio}"


def extract_transcript(response_json: dict[str, Any]) -> str:
    choices = response_json.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""

    first_choice = choices[0] or {}
    message = first_choice.get("message") or {}
    content = message.get("content")

    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(extract_text_piece(item) for item in content).strip()

    delta = first_choice.get("delta") or {}
    delta_content = delta.get("content")
    return delta_content if isinstance(delta_content, str) else ""


def extract_text_piece(item: Any) -> str:
    if isinstance(item, str):
        return item
    if not isinstance(item, dict):
        return ""
    text = item.get("text") or item.get("content")
    return text if isinstance(text, str) else ""


def preview_payload(payload: dict[str, Any], audio_size_bytes: int, content_type: str) -> dict[str, Any]:
    return {
        "model": payload.get("model", ""),
        "stream": payload.get("stream", False),
        "asr_options": payload.get("asr_options", {}),
        "audio": {
            "content_type": content_type,
            "size_bytes": audio_size_bytes,
            "encoding": "base64_data_url",
        },
    }
