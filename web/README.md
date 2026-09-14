# 分镜管理系统

Web 前端管理系统，用于管理分镜提示词和编辑 shots.json。

## 功能

### 1. 分镜提示词管理
- 浏览所有分镜库项目
- 查看每个项目的分镜列表
- 预览已生成的分镜图片
- 一键生成单个分镜图片
- 编辑分镜的提示词和主角标记

### 2. shots.json 编辑器
- 选择项目编辑 shots.json
- JSON 实时编辑和格式化
- 保存和重新加载

## 启动

### Windows
双击 `start.bat` 或在命令行运行：
```bash
start.bat
```

### 手动启动
```bash
cd web
pip install -r requirements.txt
python app.py
```

启动后访问：http://localhost:5000

## 环境要求

- Python 3.8+
- 已配置 `.env` 文件中的 `ARK_API_KEY`

## 目录结构

```
web/
├── app.py              # Flask 后端 API
├── requirements.txt    # Python 依赖
├── start.bat          # Windows 启动脚本
├── static/
│   └── index.html     # 前端页面
└── README.md          # 说明文档
```
