# Meeting Agent

Meeting Agent 是一个移动端优先的 AI 见面地点推荐项目。当前代码库保留了一版可运行的 Demo v0，已经打通语音录制、ASR 识别、地点提取、高德推荐、地图展示、TTS 语音回复和历史记录查看等链路。

V1 的产品方向是「对话式 Agent 助手」：用户用自然语言描述双方位置和见面偏好，助手在对话中追问缺失信息，并在聊天框里推荐合适的见面地点。

## 当前版本

- `main`：Demo v0 基线版本。
- `v0-demo`：当前可运行 Demo 的标签。
- `feat/chat-agent-v1`：正在开发的对话式 Agent 版本分支。

## 功能概览

- 移动端优先的 React 界面。
- 浏览器录音并上传到后端。
- 使用百炼 ASR 完成语音转文字。
- 使用 DeepSeek 提取双方地点，并带有本地兜底逻辑。
- 使用高德 MCP / REST 能力完成地理编码和候选地点推荐。
- 前端集成高德 JS 地图展示推荐结果。
- 使用百炼 TTS 生成语音回复。
- 本地保存推荐历史，便于回看。
- `docs/` 下包含 V1 PRD、移动端原型和接口接入说明。

## 目录结构

```text
.
├── backend/                 # FastAPI 后端
│   ├── app/
│   │   ├── main.py          # FastAPI 应用和 CORS 配置
│   │   ├── routes.py        # API 路由和推荐链路编排
│   │   ├── config.py        # .env 解析和运行配置
│   │   └── services/        # 百炼、DeepSeek、高德服务封装
│   ├── tests/               # 后端单元测试
│   ├── requirements.txt
│   └── .env.example
├── frontend/                # React + Vite 前端
│   ├── src/
│   │   ├── App.jsx
│   │   ├── AmapPanel.jsx
│   │   ├── api.js
│   │   ├── mobileViewModel.js
│   │   └── styles.css
│   ├── package.json
│   └── .env.example
├── docs/                    # 接入文档、PRD 和原型
├── Storage/                 # 运行时音频、日志和链路产物，已被 Git 忽略
└── README.md
```

## 环境要求

- 推荐使用 Python 3.12。
- 推荐使用 Node.js 20+。
- 需要准备百炼、DeepSeek 和高德相关 API Key。
- 如走高德 MCP 链路，需要配置可用的高德 MCP Server URL。

## 后端启动

```bash
cd backend
python3 -m venv .venv-run312
source .venv-run312/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

编辑 `backend/.env`，填写必要密钥：

```text
BAILIAN_API_KEY=
DEEPSEEK_API_KEY=
AMAP_MAPS_API_KEY=
AMAP_WEB_SERVICE_KEY=
AMAP_JS_API_KEY=
AMAP_JS_SECURITY_CODE=
```

启动后端：

```bash
cd backend
source .venv-run312/bin/activate
PYTHONPATH=. uvicorn app.main:app --host 0.0.0.0 --port 8013 --reload
```

健康检查：

```bash
curl http://localhost:8013/health
```

预期返回：

```json
{"status":"ok"}
```

## 前端启动

```bash
cd frontend
npm install
cp .env.example .env.local
npm run dev
```

前端默认运行在：

```text
http://localhost:5177/
```

默认推荐接口：

```text
/api/meeting-point/recommend
```

如果前端没有通过代理访问后端，可以在 `frontend/.env.local` 中把 `VITE_RECOMMEND_ENDPOINT` 改成完整后端地址。

## API 概览

后端默认地址：

```text
http://localhost:8013
```

主要接口：

- `GET /health`：服务健康检查。
- `GET /api/client-config`：前端地图配置。
- `POST /api/meeting-point/recommend`：上传录音并执行推荐链路。
- `GET /api/meeting-point/history`：获取推荐历史列表。
- `GET /api/meeting-point/history/{request_id}`：获取单条推荐详情。

## 验证命令

运行后端测试：

```bash
source backend/.venv-run312/bin/activate
PYTHONPATH=backend python -m unittest backend/tests/test_routes_validation.py backend/tests/test_deepseek_extractor.py
```

运行前端 view model 测试：

```bash
cd frontend
node --test src/mobileViewModel.test.js
```

构建前端：

```bash
cd frontend
npm run build
```

## 文档和原型

- V1 PRD：`docs/superpowers/specs/2026-07-01-meetpoint-v1-prd.md`
- 移动端原型：`docs/prototypes/meetpoint-v1-mobile-prototype.html`
- 高德接入说明：`docs/高德MCP_接入说明.md`
- DeepSeek 接入说明：`docs/DeepSeek_开发规范.md`

可以直接在浏览器中打开原型：

```text
docs/prototypes/meetpoint-v1-mobile-prototype.html
```

## 运行时产物

后端会把运行时文件写入 `Storage/`，包括：

- 用户上传的录音文件；
- ASR 识别结果；
- DeepSeek 地点提取结果；
- 高德 MCP 调用链路；
- TTS 生成结果；
- pipeline 汇总结果；
- 后端日志。

`Storage/` 已被 Git 忽略，不应提交到仓库。

## 安全注意事项

- 不要提交 `backend/.env` 或任何真实 API Key。
- 仓库只应跟踪 `.env.example` 示例文件。
- 生成的音频、日志、本地虚拟环境、`node_modules` 和构建产物都已被 Git 忽略。

## 开发说明

当前可运行的 Demo v0 会保留作为基线。后续新产品形态在 `feat/chat-agent-v1` 分支继续开发，目标是把当前地图工具式 Demo 升级为「对话式见面地点决策 Agent」。
