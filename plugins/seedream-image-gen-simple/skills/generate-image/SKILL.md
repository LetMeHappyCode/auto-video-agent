---
name: generate-image
description: 使用火山方舟 Seedream 模型生成图片。当用户要求根据文字描述生成图片，或基于参考图做图生图/风格迁移/生成组图时使用。
---

调用 `${CLAUDE_PLUGIN_ROOT}/scripts/generate_image.py` 生成图片。脚本直接输出 JSON 结果到 stdout，不写日志文件。

运行前确保 `ARK_API_KEY` 环境变量已设置，或在插件根目录放一个 `.env` 文件（`ARK_API_KEY=xxx`），脚本会自动读取。

## 用法

纯文生图，单张：
```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/generate_image.py" --prompt "一只猫在窗台看夕阳"
```

文生图，组图（生成 4 张连贯图片）：
```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/generate_image.py" --prompt "生成4张连贯插画，展示同一庭院四季变迁" --sequential --max-images 4
```

图生图，单图参考：
```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/generate_image.py" --prompt "生成狗狗趴在草地上的近景画面" --image https://example.com/ref.png
```

图生图，多图参考：
```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/generate_image.py" --prompt "将图1的服装换为图2的服装" --image https://example.com/ref1.png https://example.com/ref2.png
```

图生图 + 组图：
```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/generate_image.py" --prompt "生成3张女孩和奶牛玩偶坐过山车的图片，早中晚各一张" --image https://example.com/ref1.png https://example.com/ref2.png --sequential --max-images 3
```

## 参数说明

- `--prompt`（必填）：生成提示词
- `--image`：参考图 URL，一个或多个（空格分隔）。不传则是纯文生图
- `--sequential`：生成组图，不传则只生成一张
- `--max-images`：组图模式下最多生成的数量
- `--size`：图片尺寸，默认 `2K`，可选 `1K`/`2K`/`4K` 或 `宽x高`
- `--no-watermark`：不加水印（默认会加水印）

## 输出

脚本把结果作为一行 JSON 打印到 stdout：`{"images": [{"url": "..."}], "usage": {...}, "errors": []}`。失败时输出 `{"error": "..."}` 并以非零状态退出。把 stdout 解析为 JSON 后，提取 `images` 里的 `url` 展示给用户即可。
