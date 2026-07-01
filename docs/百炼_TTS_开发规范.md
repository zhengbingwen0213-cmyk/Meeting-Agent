# 百炼 TTS 开发规范

更新时间：2026-05-17

## 官方依据

- 语音合成模型总览：https://help.aliyun.com/zh/model-studio/speech-synthesis/
- 千问 TTS API：https://help.aliyun.com/zh/model-studio/qwen-tts-api
- CosyVoice 非实时 HTTP API：https://help.aliyun.com/zh/model-studio/non-realtime-cosyvoice-api

## 本项目选型

当前链路是“录音上传 -> ASR -> DeepSeek 地址提取 -> 高德 MCP 推荐 -> TTS 播报”，前端需要等完整推荐结果生成后再播放，因此优先使用百炼 HTTP 非流式语音合成，不接 WebSocket 实时流。

默认模型：

- `qwen3-tts-flash`
- Endpoint：`https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation`
- 音色：`Cherry`
- 语言：`Chinese`

官方文档说明，Qwen 系列不带 `-realtime` 后缀的 TTS 模型走 HTTP 接入；`qwen3-tts-flash` 适合导航、通知、短文本高频播报。

## 调用规范

请求头：

```http
Authorization: Bearer ${BAILIAN_API_KEY}
Content-Type: application/json
Accept: application/json
```

请求体：

```json
{
  "model": "qwen3-tts-flash",
  "input": {
    "text": "推荐你们在某个地点附近见面，地址是某某路。",
    "voice": "Cherry",
    "language_type": "Chinese"
  }
}
```

非流式返回中需要读取：

- `request_id`：百炼请求 ID，用于排障。
- `output.audio.url`：完整音频文件 URL，有效期有限。
- `output.audio.data`：流式场景中的 Base64 音频数据，本项目只做兼容解析。
- `usage`：字符或 Token 消耗信息。

稳定性策略：后端优先下载 `output.audio.url`。如果本地网络访问临时 OSS URL 失败，自动切换到官方 SSE 流式 HTTP 调用，读取每个 `data:` 事件中的 `output.audio.data`，按顺序解码并拼接成本地 WAV 文件。

## Storage 落盘规范

后端每次请求必须保存：

- `Storage/<请求前缀>_tts.json`：TTS 调用状态、播报文本、请求摘要、百炼原始响应、下载后的本地音频路径；如果启用流式回退，则记录回退原因和流式事件摘要。
- `Storage/<请求前缀>_tts.wav`：从百炼临时 URL 下载后的音频文件；如果响应是其他音频格式，则按实际 MIME 保存扩展名。
- `Storage/<请求前缀>_pipeline.json`：完整链路输出中追加 `tts` 节点，记录播报文本、音频路径、音频 MIME。

注意：百炼返回的临时 URL 不作为前端长期播放地址使用，后端必须下载到本地 `Storage` 后，再把音频以 Base64 返回给前端播放。

## 配置项

```env
BAILIAN_TTS_ENABLED=true
BAILIAN_TTS_ENDPOINT=https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation
BAILIAN_TTS_MODEL=qwen3-tts-flash
BAILIAN_TTS_VOICE=Cherry
BAILIAN_TTS_LANGUAGE_TYPE=Chinese
BAILIAN_TTS_TIMEOUT_SECONDS=60
BAILIAN_TTS_MAX_TEXT_CHARS=500
```

安全要求：

- `BAILIAN_API_KEY` 只写入本地 `backend/.env`，不要提交到仓库或写入文档。
- Storage 中不得保存 Authorization Header。
- `request_payload_preview` 只记录模型、音色、语言和文本摘要，不记录密钥。

## 日志节点

后端日志需要能看到以下中文节点：

1. 开始百炼 TTS 语音合成。
2. TTS 完成，输出本地音频路径和字节大小。
3. TTS 失败，输出错误原因，并在 `Storage/<请求前缀>_tts.json` 中保存失败状态。

## 前端对接

接口返回：

```json
{
  "answer_text": "推荐你们在 ...",
  "audio_base64": "<base64>",
  "audio_mime": "audio/wav"
}
```

前端将 `audio_base64` 转为 `data:<audio_mime>;base64,...`，拿到结果后先尝试自动播放；如果浏览器拦截自动播放，点击“播放”按钮即可读出推荐结果。
