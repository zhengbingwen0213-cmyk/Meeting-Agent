# 高德 MCP 接入说明

整理时间：2026-05-17

本文档记录本项目后端接入高德远端 MCP Server 的约定。当前后端必须创建本地 MCP Client，连接远端 MCP Server，再通过 MCP 工具调用完成地址解析、距离计算和候选地点搜索。

## 远端 MCP Server

默认使用高德远端 Streamable HTTP MCP：

```text
https://mcp.amap.com/mcp?key=<AMAP_MAPS_API_KEY>
```

如果 `.env` 配置了 `AMAP_MCP_URL`，则优先使用完整 URL。

## 本项目配置

```env
AMAP_MCP_ENABLED=true
AMAP_MCP_URL=
AMAP_MAPS_API_KEY=
AMAP_WEB_SERVICE_KEY=
AMAP_MCP_DISTANCE_TYPE=0
AMAP_HTTP_GEOCODE_FALLBACK=true
AMAP_GEOCODE_DEFAULT_CITY=
AMAP_MCP_TIMEOUT_SECONDS=30
AMAP_MEETING_KEYWORDS=咖啡厅
AMAP_SEARCH_RADIUS=3000
```

说明：

- `AMAP_MAPS_API_KEY`：用于拼接高德远端 MCP URL。
- `AMAP_MCP_URL`：完整 MCP Server URL，存在时优先使用。
- `AMAP_WEB_SERVICE_KEY`：仅用于 MCP 地理编码失败时的 REST 回退。
- `AMAP_GEOCODE_DEFAULT_CITY`：短地址或重名地址时用于限制城市。

## 调用流程

后端执行顺序：

```text
读取配置
  → 建立本地 MCP Client
  → 连接远端 MCP Server
  → initialize()
  → list_tools()
  → 根据真实工具列表选择工具
  → call_tool(maps_geo)
  → call_tool(maps_distance)
  → call_tool(maps_around_search 或 maps_text_search)
  → 解析并归一化结果
  → 写入 Storage 留档
  → 返回前端
```

禁止跳过 `list_tools()` 直接假设工具存在。

## 日志留档

每次调用都写入：

```text
Storage/<timestamp>_<request_id>_amap_mcp.json
```

留档内容包含：

- `initialize` 状态
- `list_tools` 原始返回
- 每次 `call_tool` 的工具名和参数
- MCP Server 返回的原始结果
- 归一化后的坐标、推荐地点、候选地点
- 是否使用 REST 回退
- 失败阶段与错误信息

日志中不会保存完整 Key；MCP URL 只保存协议、host 和 path。

## 当前调用工具

工具必须以 `list_tools()` 真实返回为准。当前代码优先选择：

- `maps_geo`：地址转经纬度。
- `maps_distance`：计算两地距离。
- `maps_around_search`：在中间点附近搜索会面地点。
- `maps_text_search`：周边搜索不可用时作为候选搜索。

如果 `maps_geo` 不存在，且 `AMAP_HTTP_GEOCODE_FALLBACK=true` 且配置了 `AMAP_WEB_SERVICE_KEY`，后端会明确记录 REST 回退原因。

## 中文运行日志

后端会输出简洁中文状态：

```text
请求 abcd1234：开始连接高德 MCP Server
请求 abcd1234：高德 MCP 完成，推荐=某咖啡厅，地址=某路某号
```

详细输入输出以 Storage 中的 MCP JSON 文件为准。
