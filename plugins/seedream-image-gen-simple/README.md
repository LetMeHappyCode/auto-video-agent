# seedream-image-gen-simple

轻量版 Claude Code 插件，接入火山方舟 Seedream 文生图/图生图 API。

与 [seedream-image-gen](../seedream-image-gen) 的区别：不启动常驻 MCP 进程，不记录调用日志，Claude 通过 Bash 直接运行脚本、拿到 JSON 结果。

## 安装依赖

```bash
pip install -r requirements.txt
```

## 配置 API Key

在插件根目录创建 `.env`：

```
ARK_API_KEY=你的方舟API Key
```

## 使用

Claude 会通过 `skills/generate-image/SKILL.md` 里的说明自动调用：

```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/generate_image.py" --prompt "一只猫在窗台看夕阳"
```

支持文生图/图生图、单图/组图，具体参数见 [SKILL.md](skills/generate-image/SKILL.md)。
