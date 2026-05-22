from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_from_directory
from werkzeug.utils import secure_filename

from processor import create_mosaic, cleanup_old_files

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
GENERATED_DIR = BASE_DIR / "generated"
ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "bmp", "tif", "tiff"}
MAX_IMAGES = int(os.getenv("MAX_IMAGES", "120"))

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = int(os.getenv("MAX_CONTENT_LENGTH_MB", "150")) * 1024 * 1024
UPLOAD_DIR.mkdir(exist_ok=True)
GENERATED_DIR.mkdir(exist_ok=True)
cleanup_old_files(GENERATED_DIR, max_age_minutes=int(os.getenv("CLEANUP_MINUTES", "120")))


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def save_uploads(files, target_folder: Path) -> list[Path]:
    saved = []
    for file in files:
        if not file or not file.filename or not allowed_file(file.filename):
            continue
        filename = secure_filename(file.filename)
        if not filename:
            continue
        unique_name = f"{uuid.uuid4().hex}_{filename}"
        path = target_folder / unique_name
        file.save(path)
        saved.append(path)
    return saved


@app.get("/")
def index():
    return render_template("index.html")


@app.post("/generate")
def generate():
    job_upload_dir = UPLOAD_DIR / uuid.uuid4().hex
    job_upload_dir.mkdir(parents=True, exist_ok=True)

    try:
        tile_files = request.files.getlist("tiles")
        if len(tile_files) > MAX_IMAGES:
            return jsonify({"ok": False, "error": f"Maximum {MAX_IMAGES} tile images allowed."}), 400

        tile_paths = save_uploads(tile_files, job_upload_dir)
        if not tile_paths:
            return jsonify({"ok": False, "error": "Upload at least one valid tile image."}), 400

        target_path = None
        target_file = request.files.get("target")
        if target_file and target_file.filename and allowed_file(target_file.filename):
            target_paths = save_uploads([target_file], job_upload_dir)
            target_path = target_paths[0] if target_paths else None

        result = create_mosaic(
            tile_paths=tile_paths,
            target_path=target_path,
            output_dir=GENERATED_DIR,
            tile_res=int(request.form.get("tile_res", 32)),
            density=int(request.form.get("density", 100)),
            target_sharpness=int(request.form.get("target_sharpness", 150)),
            random_k=int(request.form.get("random_k", 2)),
            blend_mode=request.form.get("blend_mode", "Luminosity Multiply (Sharp)"),
            alpha_mix=float(request.form.get("alpha_mix", 0.15)),
            export_fmt=request.form.get("export_fmt", "JPEG"),
            add_footer=request.form.get("add_footer", "true") == "true",
        )

        shutil.rmtree(job_upload_dir, ignore_errors=True)
        return jsonify({
            "ok": True,
            "job_id": result.job_id,
            "preview_url": f"/generated/{result.preview_file}",
            "crop_url": f"/generated/{result.crop_file}",
            "download_url": f"/download/{result.job_id}",
            "download_name": result.download_name,
            "width": result.width,
            "height": result.height,
            "tile_count": result.tile_count,
            "target_source": result.target_source,
        })

    except Exception as exc:
        shutil.rmtree(job_upload_dir, ignore_errors=True)
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.get("/download/<job_id>")
def download(job_id):
    matches = list(GENERATED_DIR.glob(f"{job_id}.*"))
    matches = [m for m in matches if not m.name.endswith("_preview.jpg") and not m.name.endswith("_crop.jpg")]
    if not matches:
        return "File not found", 404
    return send_from_directory(GENERATED_DIR, matches[0].name, as_attachment=True)


@app.get("/generated/<path:filename>")
def generated(filename):
    return send_from_directory(GENERATED_DIR, filename)


@app.get("/healthz")
def healthz():
    return {"ok": True}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=os.getenv("FLASK_DEBUG", "0") == "1")
