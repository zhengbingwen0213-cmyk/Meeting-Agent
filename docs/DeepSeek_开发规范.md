# DeepSeek 开发规范

整理时间：2026-05-17

本文档记录本项目后端接入 DeepSeek 的最小开发规范。当前用途是：在百炼 ASR 得到中文文本后，调用 DeepSeek 模型提取用户 Query 中的两个地址，再把两个地址交给高德 MCP 服务做地理编码和推荐。

## 官方依据

- DeepSeek 首次调用 API：<https://api-docs.deepseek.com/>
- Chat Completions API：<https://api-docs.deepseek.com/api/create-chat-completion>
- JSON Output：<https://api-docs.deepseek.com/zh-cn/guides/json_mode>
- Function Calling / Tool Calls：<https://api-docs.deepseek.com/guides/function_calling/>
- 错误码：<https://api-docs.deepseek.com/zh-cn/quick_start/error_codes>
- 限速说明：<https://api-docs.deepseek.com/quick_start/rate_limit/>

## 接入方式

DeepSeek API 兼容 OpenAI / Anthropic API 格式。本项目使用 OpenAI 兼容的 HTTP 接口，不引入额外 SDK。

```text
POST https://api.deepseek.com/chat/completions
```

请求头：

```http
Authorization: Bearer <DEEPSEEK_API_KEY>
Content-Type: application/json
Accept: application/json
```

密钥只允许从 `backend/.env` 读取，不允许写死在代码、日志或文档中。

## 模型选择

默认使用：

```text
deepseek-v4-flash
```

官方文档当前列出的模型包括 `deepseek-v4-flash` 和 `deepseek-v4-pro`。`deepseek-chat` 与 `deepseek-reasoner` 将在 2026-07-24 弃用，因此本项目默认不再使用旧模型名。

地址槽位提取是低复杂度结构化任务，优先使用 `deepseek-v4-flash`，并关闭 thinking：

```json
{
  "thinking": {
    "type": "disabled"
  }
}
```

如果后续需要更强推理，可把 `.env` 中的 `DEEPSEEK_MODEL` 改为 `deepseek-v4-pro`，或把 `DEEPSEEK_THINKING` 改为 `enabled`。

## JSON Output 规范

本项目使用 JSON Output，要求：

1. 请求体设置 `response_format={"type":"json_object"}`。
2. system 或 user prompt 中必须包含 `json` 字样。
3. prompt 中必须给出目标 JSON 示例。
4. `max_tokens` 要留足，避免 JSON 被截断。
5. 如果 DeepSeek 返回空 content 或非法 JSON，本次请求必须失败并写入 Storage。

## 地址提取输出

DeepSeek 必须输出以下 JSON：

```json
{
  "self_location": "北京市海淀区中关村",
  "friend_location": "北京市朝阳区三里屯",
  "city": "北京",
  "confidence": 0.9,
  "missing_fields": [],
  "normalized_query": "我在中关村，朋友在三里屯，推荐一个见面地点",
  "notes": []
}
```

字段说明：

- `self_location`：用户自己、我、本人所在地址。
- `friend_location`：朋友、对方、他、她所在地址。
- `city`：文本明确出现或能稳定推断时填写，否则留空。
- `confidence`：0 到 1 的置信度。
- `missing_fields`：未识别到的字段名。
- `normalized_query`：清洗后的用户意图。
- `notes`：提取时的简短备注。

禁止行为：

- 不允许编造地址。
- 不允许把景点、城市、商圈强行补全为详细地址。
- 不允许输出 Markdown、解释文字或代码块。

## 错误处理

DeepSeek 官方错误码需要按场景处理：

- `400`：请求体格式错误，检查 JSON 结构。
- `401`：API Key 错误或缺失。
- `402`：账号余额不足。
- `422`：参数错误，检查模型名、thinking、response_format 等参数。
- `429`：请求速率达到上限，需要降低并发或稍后重试。
- `500`：服务端故障，可稍后重试。
- `503`：服务繁忙，可稍后重试。

本项目当前不做自动重试，先把失败响应写入 Storage，方便人工查看。

## 本项目配置

配置文件：

```text
backend/.env
```

配置项：

```env
DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash
DEEPSEEK_TIMEOUT_SECONDS=60
DEEPSEEK_MAX_TOKENS=512
DEEPSEEK_TEMPERATURE=0.1
DEEPSEEK_THINKING=disabled
```

## 留档要求

每次 DeepSeek 地址提取都要在 `Storage` 下写入：

```text
<timestamp>_<request_id>_deepseek.json
```

内容至少包含：

- `request_id`
- ASR transcript
- 提取出的 slots
- 请求参数预览
- DeepSeek 原始响应
- 成功或失败状态

日志只打印简洁中文摘要，例如：

```text
请求 abcd1234：开始 DeepSeek 地址提取
请求 abcd1234：DeepSeek 提取完成，你=中关村，朋友=三里屯，城市=北京
```

完整排查信息以 Storage JSON 为准。
