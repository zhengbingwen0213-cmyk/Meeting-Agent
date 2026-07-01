import json
import os
import re
import time
from dataclasses import dataclass
from typing import Any

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
class AddressExtractionResult:
    self_location: str
    friend_location: str
    city: str
    confidence: float
    missing_fields: list[str]
    normalized_query: str
    notes: list[str]
    raw_response: dict[str, Any]
    request_payload_preview: dict[str, Any]


class DeepSeekExtractionError(Exception):
    pass


class DeepSeekAddressExtractor:
    def __init__(self, settings: Settings):
        clear_proxy_environment_variables()
        self.settings = settings

    def extract_addresses(self, transcript: str) -> AddressExtractionResult:
        if not transcript.strip():
            raise DeepSeekExtractionError("ASR 文本为空，无法提取地址")

        payload = self._build_payload(transcript)
        if not self.settings.deepseek_api_key:
            fallback = extract_addresses_locally(transcript)
            if fallback:
                return build_fallback_result(
                    fallback,
                    payload,
                    "缺少 DEEPSEEK_API_KEY，已使用本地规则提取地址",
                )
            raise DeepSeekExtractionError("缺少 DEEPSEEK_API_KEY，请在 backend/.env 中配置 DeepSeek API Key")

        try:
            response_json = self._post_json(payload)
            content = extract_message_content(response_json)
            extracted = parse_json_content(content)
        except DeepSeekExtractionError as error:
            fallback = extract_addresses_locally(transcript)
            if fallback:
                return build_fallback_result(fallback, payload, friendly_deepseek_error(error))
            raise DeepSeekExtractionError(friendly_deepseek_error(error)) from error

        normalized = normalize_extraction(extracted)

        return AddressExtractionResult(
            self_location=normalized["self_location"],
            friend_location=normalized["friend_location"],
            city=normalized["city"],
            confidence=normalized["confidence"],
            missing_fields=normalized["missing_fields"],
            normalized_query=normalized["normalized_query"],
            notes=normalized["notes"],
            raw_response=response_json,
            request_payload_preview=preview_payload(payload),
        )

    def _build_payload(self, transcript: str) -> dict[str, Any]:
        system_prompt = """你是一个中文地址槽位提取器。请从用户 ASR 文本中提取两个会面出发地址，并且只输出合法 json。

EXAMPLE JSON OUTPUT:
{
  "self_location": "北京市海淀区中关村",
  "friend_location": "北京市朝阳区三里屯",
  "city": "北京",
  "confidence": 0.9,
  "missing_fields": [],
  "normalized_query": "我在中关村，朋友在三里屯，推荐一个见面地点",
  "notes": []
}

规则：
1. self_location 表示用户自己/我/本人所在地址。
2. friend_location 表示朋友/对方/他/她所在地址。
3. city 在文本明确出现或能从两个地标稳定推断为同一城市时填写，例如“人民广场”和“静安寺”应推断为“上海”；否则留空。
4. 没识别到的字段填空字符串，并把字段名放入 missing_fields。
5. 不要编造地址，不要输出解释文字。"""

        payload: dict[str, Any] = {
            "model": self.settings.deepseek_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"请从以下 ASR 文本中提取地址槽位，并输出 json：\n{transcript}"},
            ],
            "response_format": {"type": "json_object"},
            "stream": False,
            "temperature": self.settings.deepseek_temperature,
            "max_tokens": self.settings.deepseek_max_tokens,
        }

        if self.settings.deepseek_thinking in {"enabled", "disabled"}:
            payload["thinking"] = {"type": self.settings.deepseek_thinking}

        return payload

    def _post_json(self, payload: dict[str, Any]) -> dict[str, Any]:
        response_body = ""
        last_error: httpx.HTTPError | None = None
        for attempt in range(3):
            try:
                with httpx.Client(timeout=self.settings.deepseek_timeout_seconds, trust_env=False) as client:
                    response = client.post(
                        build_chat_completions_url(self.settings.deepseek_base_url),
                        headers={
                            "Authorization": f"Bearer {self.settings.deepseek_api_key}",
                            "Content-Type": "application/json",
                            "Accept": "application/json",
                        },
                        json=payload,
                    )
                    response_body = response.text
                    response.raise_for_status()
                    break
            except httpx.HTTPStatusError as error:
                raise DeepSeekExtractionError(
                    f"DeepSeek HTTP {error.response.status_code}: {error.response.text}"
                ) from error
            except httpx.HTTPError as error:
                last_error = error
                if attempt < 2:
                    time.sleep(0.5 * (attempt + 1))
                    continue
                raise DeepSeekExtractionError(f"DeepSeek 网络请求失败: {last_error}") from error

        try:
            return json.loads(response_body)
        except json.JSONDecodeError as error:
            raise DeepSeekExtractionError(f"DeepSeek 返回非 JSON 内容: {response_body[:500]}") from error


def clear_proxy_environment_variables() -> None:
    for key in PROXY_ENV_KEYS:
        os.environ.pop(key, None)


def build_chat_completions_url(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    if normalized.endswith("/chat/completions"):
        return normalized
    return f"{normalized}/chat/completions"


def extract_message_content(response_json: dict[str, Any]) -> str:
    choices = response_json.get("choices")
    if not isinstance(choices, list) or not choices:
        raise DeepSeekExtractionError("DeepSeek 响应缺少 choices")

    first_choice = choices[0] or {}
    message = first_choice.get("message") or {}
    content = message.get("content")
    if isinstance(content, str) and content.strip():
        return content.strip()

    raise DeepSeekExtractionError("DeepSeek 响应没有可解析的 message.content")


def parse_json_content(content: str) -> dict[str, Any]:
    cleaned = content.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`").strip()
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as error:
        raise DeepSeekExtractionError(f"DeepSeek JSON Output 解析失败: {content[:500]}") from error

    if not isinstance(parsed, dict):
        raise DeepSeekExtractionError("DeepSeek JSON Output 顶层不是对象")
    return parsed


def extract_addresses_locally(transcript: str) -> dict[str, Any] | None:
    self_location = extract_location_by_patterns(
        transcript,
        [
            r"(?:我|本人|自己)(?:现在|目前)?在(?P<location>[^，,。；;！!？?\n]+)",
            r"(?:我的位置|我这边)(?:是|在|位于)?(?P<location>[^，,。；;！!？?\n]+)",
        ],
    )
    friend_location = extract_location_by_patterns(
        transcript,
        [
            r"(?:我的朋友|我朋友|朋友|对方|他|她)(?:现在|目前)?在(?P<location>[^，,。；;！!？?\n]+)",
            r"(?:朋友的位置|对方的位置)(?:是|在|位于)?(?P<location>[^，,。；;！!？?\n]+)",
        ],
    )

    if not self_location or not friend_location:
        return None

    city = infer_city(transcript, self_location, friend_location)
    return {
        "self_location": self_location,
        "friend_location": friend_location,
        "city": city,
        "confidence": 0.62,
        "missing_fields": [],
        "normalized_query": transcript.strip(),
        "notes": ["local_rule_fallback"],
    }


def extract_location_by_patterns(transcript: str, patterns: list[str]) -> str:
    for pattern in patterns:
        match = re.search(pattern, transcript)
        if match:
            location = clean_local_location(match.group("location"))
            if location:
                return location
    return ""


def clean_local_location(location: str) -> str:
    cleaned = location.strip(" ，,。；;！!？?\n\t")
    cleaned = re.sub(r"^(是|在|位于)", "", cleaned)
    cleaned = re.split(r"(我们|咱们|然后|想|看一下|去哪里|在哪里|该去哪里|推荐)", cleaned, maxsplit=1)[0]
    return cleaned.strip(" ，,。；;！!？?\n\t")


def infer_city(transcript: str, self_location: str, friend_location: str) -> str:
    known_cities = [
        "北京",
        "上海",
        "广州",
        "深圳",
        "杭州",
        "南京",
        "苏州",
        "成都",
        "武汉",
        "西安",
        "重庆",
        "天津",
    ]
    for city in known_cities:
        if city in transcript or (city in self_location and city in friend_location):
            return city
    return ""


def build_fallback_result(
    normalized: dict[str, Any],
    payload: dict[str, Any],
    fallback_reason: str,
) -> AddressExtractionResult:
    notes = list(normalized.get("notes", []))
    if fallback_reason:
        notes.append(f"deepseek_unavailable: {fallback_reason}")

    return AddressExtractionResult(
        self_location=normalized["self_location"],
        friend_location=normalized["friend_location"],
        city=normalized["city"],
        confidence=normalized["confidence"],
        missing_fields=normalized["missing_fields"],
        normalized_query=normalized["normalized_query"],
        notes=notes,
        raw_response={
            "fallback_used": True,
            "fallback_provider": "local_rule",
            "fallback_reason": fallback_reason,
        },
        request_payload_preview=preview_payload(payload),
    )


def friendly_deepseek_error(error: DeepSeekExtractionError) -> str:
    message = str(error)
    if "Insufficient Balance" in message or "HTTP 402" in message:
        return "DeepSeek 账户余额不足，请充值或更换 DEEPSEEK_API_KEY"
    if "DEEPSEEK_API_KEY" in message:
        return message
    if "网络请求失败" in message:
        return "DeepSeek 网络请求失败，请稍后重试或检查网络连接"
    return message


def normalize_extraction(payload: dict[str, Any]) -> dict[str, Any]:
    self_location = first_string(payload, ["self_location", "user_location", "my_location", "origin_a"])
    friend_location = first_string(payload, ["friend_location", "target_location", "other_location", "origin_b"])
    city = first_string(payload, ["city", "default_city"])
    confidence = payload.get("confidence", 0)
    if not isinstance(confidence, (int, float)):
        confidence = 0

    missing_fields = payload.get("missing_fields")
    if not isinstance(missing_fields, list):
        missing_fields = []
    missing_fields = [item for item in missing_fields if isinstance(item, str)]
    if not self_location and "self_location" not in missing_fields:
        missing_fields.append("self_location")
    if not friend_location and "friend_location" not in missing_fields:
        missing_fields.append("friend_location")

    notes = payload.get("notes")
    if not isinstance(notes, list):
        notes = []
    notes = [item for item in notes if isinstance(item, str)]

    return {
        "self_location": self_location,
        "friend_location": friend_location,
        "city": city,
        "confidence": float(confidence),
        "missing_fields": missing_fields,
        "normalized_query": first_string(payload, ["normalized_query", "query"]),
        "notes": notes,
    }


def first_string(payload: dict[str, Any], keys: list[str]) -> str:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str):
            return value.strip()
    return ""


def preview_payload(payload: dict[str, Any]) -> dict[str, Any]:
    messages = payload.get("messages", [])
    return {
        "model": payload.get("model", ""),
        "stream": payload.get("stream", False),
        "response_format": payload.get("response_format", {}),
        "temperature": payload.get("temperature"),
        "max_tokens": payload.get("max_tokens"),
        "thinking": payload.get("thinking", {}),
        "message_count": len(messages) if isinstance(messages, list) else 0,
    }
