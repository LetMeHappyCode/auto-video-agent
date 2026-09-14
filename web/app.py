#!/usr/bin/env python3
"""分镜管理系统后端 API"""

import json
import os
import subprocess
import sys
from pathlib import Path
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

REFERENCE_BASENAME = "reference"
ALLOWED_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}

# 项目根目录（web 的父目录）
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

app = Flask(__name__, static_folder='static', static_url_path='')
CORS(app)

# 文案分镜库目录
LIBRARY_ROOT = PROJECT_ROOT / "文案分镜库"

print(f"项目根目录: {PROJECT_ROOT}")
print(f"分镜库目录: {LIBRARY_ROOT}")
print(f"分镜库存在: {LIBRARY_ROOT.exists()}")
print()


@app.route('/')
def index():
    return send_from_directory('static', 'index.html')


def find_reference_image(project_dir: Path) -> Path | None:
    """在项目目录下查找已上传的参考图（reference.png / reference.jpg 等）"""
    for ext in ALLOWED_IMAGE_EXTS:
        candidate = project_dir / f"{REFERENCE_BASENAME}{ext}"
        if candidate.exists():
            return candidate
    return None


@app.route('/api/projects', methods=['GET'])
def list_projects():
    """列出所有分镜项目"""
    projects = []
    for item in LIBRARY_ROOT.iterdir():
        if item.is_dir() and not item.name.startswith('.'):
            shots_dir = item / "shots"
            shots_json = item / "shots.json"

            ref_image = find_reference_image(item)

            project = {
                "name": item.name,
                "path": str(item.relative_to(PROJECT_ROOT)),
                "has_shots_json": shots_json.exists(),
                "has_shots_dir": shots_dir.exists(),
                "shot_count": 0,
                "has_reference_image": ref_image is not None,
            }

            if shots_dir.exists():
                project["shot_count"] = len(list(shots_dir.glob("shot-*.prompt.json")))

            projects.append(project)

    return jsonify(projects)


@app.route('/api/projects/<path:project_name>/shots.json', methods=['GET'])
def get_shots_json(project_name):
    """获取 shots.json 内容"""
    project_dir = LIBRARY_ROOT / project_name
    shots_file = project_dir / "shots.json"

    if not shots_file.exists():
        return jsonify({"error": "shots.json 不存在"}), 404

    try:
        content = json.loads(shots_file.read_text(encoding='utf-8'))
        return jsonify(content)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/projects/<path:project_name>/shots.json', methods=['PUT'])
def update_shots_json(project_name):
    """更新 shots.json 内容"""
    project_dir = LIBRARY_ROOT / project_name
    shots_file = project_dir / "shots.json"

    try:
        content = request.json
        shots_file.write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding='utf-8')
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/projects/<path:project_name>/reference-image', methods=['GET'])
def get_reference_image(project_name):
    """获取项目的主角参考图"""
    project_dir = LIBRARY_ROOT / project_name
    ref_image = find_reference_image(project_dir)

    if not ref_image:
        return jsonify({"error": "参考图不存在"}), 404

    return send_from_directory(project_dir, ref_image.name)


@app.route('/api/projects/<path:project_name>/reference-image', methods=['POST'])
def upload_reference_image(project_name):
    """上传主角参考图，统一重命名为 reference.<ext> 方便脚本读取"""
    project_dir = LIBRARY_ROOT / project_name

    if not project_dir.is_dir():
        return jsonify({"error": "项目不存在"}), 404

    if 'file' not in request.files:
        return jsonify({"error": "未找到上传文件"}), 400

    file = request.files['file']
    if not file.filename:
        return jsonify({"error": "文件名为空"}), 400

    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_IMAGE_EXTS:
        return jsonify({"error": f"不支持的图片格式，仅支持 {', '.join(sorted(ALLOWED_IMAGE_EXTS))}"}), 400

    try:
        # 先清理旧的参考图（可能是不同扩展名），保证目录下只有一份
        existing = find_reference_image(project_dir)
        if existing:
            existing.unlink()

        dest = project_dir / f"{REFERENCE_BASENAME}{ext}"
        file.save(str(dest))
        return jsonify({"success": True, "filename": dest.name})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/projects/<path:project_name>/reference-image', methods=['DELETE'])
def delete_reference_image(project_name):
    """删除项目的主角参考图"""
    project_dir = LIBRARY_ROOT / project_name
    ref_image = find_reference_image(project_dir)

    if not ref_image:
        return jsonify({"error": "参考图不存在"}), 404

    try:
        ref_image.unlink()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/projects/<path:project_name>/shots', methods=['GET'])
def list_shots(project_name):
    """列出项目的所有分镜"""
    project_dir = LIBRARY_ROOT / project_name
    shots_dir = project_dir / "shots"
    images_dir = project_dir / "images"

    if not shots_dir.exists():
        return jsonify([])

    shots = []
    for prompt_file in sorted(shots_dir.glob("shot-*.prompt.json")):
        try:
            data = json.loads(prompt_file.read_text(encoding='utf-8'))
            shot_id = data.get("shot_id")

            image_file = images_dir / f"shot-{shot_id:04d}.png"

            shots.append({
                "shot_id": shot_id,
                "text": data.get("当前目标片段", ""),
                "prompt": data.get("prompt", ""),
                "has_protagonist": data.get("has_protagonist", True),
                "has_image": image_file.exists(),
                "image_path": f"shot-{shot_id:04d}.png" if image_file.exists() else None,
            })
        except Exception as e:
            print(f"读取 {prompt_file} 失败: {e}", file=sys.stderr)

    return jsonify(shots)


@app.route('/api/projects/<path:project_name>/shots/<int:shot_id>/image', methods=['GET'])
def get_shot_image(project_name, shot_id):
    """获取分镜图片"""
    project_dir = LIBRARY_ROOT / project_name
    images_dir = project_dir / "images"
    image_file = images_dir / f"shot-{shot_id:04d}.png"

    if not image_file.exists():
        return jsonify({"error": "图片不存在"}), 404

    return send_from_directory(images_dir, image_file.name)


@app.route('/api/projects/<path:project_name>/shots/<int:shot_id>/generate', methods=['POST'])
def generate_shot_image(project_name, shot_id):
    """生成单个分镜图片"""
    project_dir = LIBRARY_ROOT / project_name
    shots_dir = project_dir / "shots"

    if not shots_dir.exists():
        return jsonify({"error": "shots 目录不存在"}), 404

    script_path = PROJECT_ROOT / "scripts" / "generate_images.py"
    ref_image = request.json.get("ref_image") if request.json else None

    if not ref_image:
        auto_ref = find_reference_image(project_dir)
        if auto_ref:
            ref_image = str(auto_ref)

    try:
        cmd = [
            sys.executable,
            str(script_path),
            "--dir", str(shots_dir),
            "--shot-id", str(shot_id),
        ]

        if ref_image:
            cmd.extend(["--ref-image", ref_image])

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding='utf-8',
            timeout=120,
        )

        if result.returncode == 0:
            return jsonify({
                "success": True,
                "stdout": result.stdout,
                "stderr": result.stderr,
            })
        else:
            return jsonify({
                "success": False,
                "error": result.stderr or result.stdout,
            }), 500
    except subprocess.TimeoutExpired:
        return jsonify({"error": "生成超时"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/projects/<path:project_name>/shots/<int:shot_id>', methods=['PUT'])
def update_shot(project_name, shot_id):
    """更新分镜 prompt"""
    project_dir = LIBRARY_ROOT / project_name
    shots_dir = project_dir / "shots"
    prompt_file = shots_dir / f"shot-{shot_id:04d}.prompt.json"

    if not prompt_file.exists():
        return jsonify({"error": "分镜文件不存在"}), 404

    try:
        data = json.loads(prompt_file.read_text(encoding='utf-8'))

        if "prompt" in request.json:
            data["prompt"] = request.json["prompt"]
        if "has_protagonist" in request.json:
            data["has_protagonist"] = request.json["has_protagonist"]

        prompt_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
