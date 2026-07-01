from dataclasses import dataclass
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = BACKEND_ROOT / ".env"


def load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")

    return values


def parse_bool(value: str, default: bool = False) -> bool:
    if value == "":
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def parse_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def resolve_path(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = BACKEND_ROOT / path
    return path.resolve()


@dataclass(frozen=True)
class Settings:
    app_name: str
    app_host: str
    app_port: int
    app_reload: bool
    api_prefix: str
    storage_dir: Path
    max_upload_bytes: int
    allowed_origins: list[str]
    bailian_api_key: str
    bailian_asr_endpoint: str
    bailian_asr_model: str
    bailian_asr_timeout_seconds: int
    bailian_asr_enable_itn: bool
    bailian_asr_language: str
    bailian_asr_system_prompt: str
    bailian_asr_max_audio_base64_bytes: int
    bailian_tts_enabled: bool
    bailian_tts_endpoint: str
    bailian_tts_model: str
    bailian_tts_voice: str
    bailian_tts_language_type: str
    bailian_tts_timeout_seconds: int
    bailian_tts_max_text_chars: int
    deepseek_api_key: str
    deepseek_base_url: str
    deepseek_model: str
    deepseek_timeout_seconds: int
    deepseek_max_tokens: int
    deepseek_temperature: float
    deepseek_thinking: str
    amap_mcp_enabled: bool
    amap_mcp_url: str
    amap_maps_api_key: str
    amap_web_service_key: str
    amap_mcp_distance_type: str
    amap_http_geocode_fallback: bool
    amap_geocode_default_city: str
    amap_mcp_timeout_seconds: int
    amap_meeting_keywords: str
    amap_search_radius: int
    amap_js_api_key: str
    amap_js_security_code: str
    amap_js_allow_without_security_code: bool


def get_settings() -> Settings:
    env = load_env_file(ENV_FILE)
    max_upload_mb = int(env.get("MAX_UPLOAD_MB", "50"))
    max_asr_base64_mb = int(env.get("BAILIAN_ASR_MAX_AUDIO_BASE64_MB", "10"))

    return Settings(
        app_name=env.get("APP_NAME", "meeting-point-backend"),
        app_host=env.get("APP_HOST", "0.0.0.0"),
        app_port=int(env.get("APP_PORT", "8013")),
        app_reload=parse_bool(env.get("APP_RELOAD", "true"), default=True),
        api_prefix=env.get("API_PREFIX", "/api"),
        storage_dir=resolve_path(env.get("STORAGE_DIR", "../Storage")),
        max_upload_bytes=max_upload_mb * 1024 * 1024,
        allowed_origins=parse_csv(env.get("ALLOWED_ORIGINS", "http://localhost:5177")),
        bailian_api_key=env.get("BAILIAN_API_KEY", ""),
        bailian_asr_endpoint=env.get(
            "BAILIAN_ASR_ENDPOINT",
            "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
        ),
        bailian_asr_model=env.get("BAILIAN_ASR_MODEL", "qwen3-asr-flash"),
        bailian_asr_timeout_seconds=int(env.get("BAILIAN_ASR_TIMEOUT_SECONDS", "60")),
        bailian_asr_enable_itn=parse_bool(env.get("BAILIAN_ASR_ENABLE_ITN", "false")),
        bailian_asr_language=env.get("BAILIAN_ASR_LANGUAGE", ""),
        bailian_asr_system_prompt=env.get("BAILIAN_ASR_SYSTEM_PROMPT", ""),
        bailian_asr_max_audio_base64_bytes=max_asr_base64_mb * 1024 * 1024,
        bailian_tts_enabled=parse_bool(env.get("BAILIAN_TTS_ENABLED", "true"), default=True),
        bailian_tts_endpoint=env.get(
            "BAILIAN_TTS_ENDPOINT",
            "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation",
        ),
        bailian_tts_model=env.get("BAILIAN_TTS_MODEL", "qwen3-tts-flash"),
        bailian_tts_voice=env.get("BAILIAN_TTS_VOICE", "Cherry"),
        bailian_tts_language_type=env.get("BAILIAN_TTS_LANGUAGE_TYPE", "Chinese"),
        bailian_tts_timeout_seconds=int(env.get("BAILIAN_TTS_TIMEOUT_SECONDS", "60")),
        bailian_tts_max_text_chars=int(env.get("BAILIAN_TTS_MAX_TEXT_CHARS", "500")),
        deepseek_api_key=env.get("DEEPSEEK_API_KEY", ""),
        deepseek_base_url=env.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        deepseek_model=env.get("DEEPSEEK_MODEL", "deepseek-v4-flash"),
        deepseek_timeout_seconds=int(env.get("DEEPSEEK_TIMEOUT_SECONDS", "60")),
        deepseek_max_tokens=int(env.get("DEEPSEEK_MAX_TOKENS", "512")),
        deepseek_temperature=float(env.get("DEEPSEEK_TEMPERATURE", "0.1")),
        deepseek_thinking=env.get("DEEPSEEK_THINKING", "disabled"),
        amap_mcp_enabled=parse_bool(env.get("AMAP_MCP_ENABLED", "true"), default=True),
        amap_mcp_url=env.get("AMAP_MCP_URL", ""),
        amap_maps_api_key=env.get("AMAP_MAPS_API_KEY", ""),
        amap_web_service_key=env.get("AMAP_WEB_SERVICE_KEY", ""),
        amap_mcp_distance_type=env.get("AMAP_MCP_DISTANCE_TYPE", "0"),
        amap_http_geocode_fallback=parse_bool(env.get("AMAP_HTTP_GEOCODE_FALLBACK", "true"), default=True),
        amap_geocode_default_city=env.get("AMAP_GEOCODE_DEFAULT_CITY", ""),
        amap_mcp_timeout_seconds=int(env.get("AMAP_MCP_TIMEOUT_SECONDS", "30")),
        amap_meeting_keywords=env.get("AMAP_MEETING_KEYWORDS", "咖啡厅"),
        amap_search_radius=int(env.get("AMAP_SEARCH_RADIUS", "3000")),
        amap_js_api_key=env.get("AMAP_JS_API_KEY") or env.get("AMAP_MAPS_API_KEY", ""),
        amap_js_security_code=env.get("AMAP_JS_SECURITY_CODE", ""),
        amap_js_allow_without_security_code=parse_bool(
            env.get("AMAP_JS_ALLOW_WITHOUT_SECURITY_CODE", "false"),
            default=False,
        ),
    )
