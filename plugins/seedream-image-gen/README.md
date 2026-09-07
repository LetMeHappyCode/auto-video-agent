# seedream-image-gen

Claude Code 插件，接入火山方舟（Volcengine Ark）Seedream 文生图/图生图 API。

## 功能

- 文生图：单张图 / 组图
- 图生图：单图参考、多图参考，单张输出 / 组图输出
- 每次调用的输入参数和输出结果都会以 JSON Lines 格式记录到 `logs/image_gen.log`，用 `request_id` 关联同一次调用的请求和响应，方便排查问题

## 安装依赖

```bash
pip install -r requirements.txt
```

## 配置 API Key

在插件根目录创建 `.env` 文件（已在 `.gitignore` 中忽略）：

```
ARK_API_KEY=你的方舟API Key
```

也可以直接设置系统环境变量 `ARK_API_KEY`。

## 使用方式

插件通过 MCP 服务暴露一个工具 `generate_images`，Claude 会根据你的需求自动调用：

- 纯文生图：只传 `prompt`
- 图生图：传 `prompt` + `image`（单个 URL 或 URL 列表）
- 生成组图：传 `sequential=true` 并指定 `max_images`

## 目录结构

```
.claude-plugin/plugin.json   插件清单
.mcp.json                    MCP 服务器配置
scripts/ark_image_client.py  核心调用逻辑 + 日志记录
scripts/mcp_server.py        MCP 工具服务器
logs/image_gen.log           调用日志（自动轮转，最多 5 个 10MB 文件）
```

## 排查问题

日志中每条记录都是一行 JSON，包含 `request_id`、`event`（request/response/error）、耗时、完整的输入参数和输出结果（或错误详情）。按 `request_id` 搜索即可定位某一次调用的完整链路。
