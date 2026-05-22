from __future__ import annotations

import csv
import hashlib
import os
import random
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path
from typing import Iterable, Optional

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageOps, ImageStat

try:
    from scipy.spatial import KDTree
except Exception:  # fallback if scipy is not installed
    KDTree = None

Image.MAX_IMAGE_PIXELS = None

MOSAIC_QUOTES = [
    "A thousand tiny squares, a thousand different days, one single masterpiece.",
    "Up close, it’s a collection of our favorite moments; from afar, it’s the shape of our lives.",
    "Every little photo is a puzzle piece; you need every single one to see the real picture.",
    "Look closely: the details hold the memories; step back: the whole holds the beauty.",
    "We are a mosaic of everywhere we’ve been and every tiny moment we’ve captured along the way.",
    "No single snapshot defines the whole story; we are the sum of a thousand little frames.",
    "A single beautiful image, built entirely out of a thousand reasons to smile.",
    "It’s not just one big picture on the wall; it’s an entire gallery of joy hiding in plain sight.",
    "The bigger picture is stunning, but the tiny hidden moments it’s made of are what matter most.",
    "Every pixel is a story, every grid is a timeline, and every mosaic is a lifetime.",
    "A macro view of who we are right now, built from the micro moments of exactly how we got here.",
    "It takes hundreds of snapshots to make one perfect memory; zoom in to remember, zoom out to appreciate.",
    "Small flashes of time, gathered together to form one brilliant image.",
    "Every tiny square is a second of joy, stacked beautifully side by side.",
    "We don’t just capture time; we weave it all together into a single view.",
    "Alone, they are just fragments; together, they are a masterpiece.",
    "The beauty of a mosaic isn’t just the final picture, but the patience of putting the pieces together.",
    "Like stained glass, our memories shine brightest when they are placed right next to each other.",
    "The grand design is always made of tiny, seemingly ordinary moments.",
    "Step close to remember the day; step back to see the journey.",
    "It’s an illusion made of truth: one giant photograph woven from hundreds of real memories.",
    "A mosaic is proof that the little things always add up to something magnificent.",
    "Look at the whole to see where we are; look at the pieces to see exactly how we got here.",
    "Hundreds of little memories, held tightly together by one big feeling.",
    "Infinite tiny stories hidden within one beautiful frame.",
    "We are all just mosaics — a beautiful collection of every little moment we’ve ever lived.",
]


@dataclass
class MosaicResult:
    job_id: str
    output_file: str
    preview_file: str
    crop_file: str
    download_name: str
    mime_type: str
    width: int
    height: int
    tile_count: int
    target_source: str


def get_font(size: int, style: str = "serif", bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    font_dirs = [Path("assets/fonts"), Path("fonts"), Path("."), Path("C:/Windows/Fonts"), Path("/usr/share/fonts/truetype/dejavu")]

    if style == "script":
        possible_fonts = [
            "GreatVibes-Regular.ttf", "Allura-Regular.ttf", "DancingScript-Regular.ttf", "Parisienne-Regular.ttf",
            "Pacifico-Regular.ttf", "Sacramento-Regular.ttf", "Segoe Script.ttf", "segoesc.ttf",
            "Brush Script MT.ttf", "BRUSHSCI.TTF", "DejaVuSerif-Italic.ttf",
        ]
    elif style == "serif":
        possible_fonts = ["Georgia.ttf", "georgia.ttf", "Times New Roman.ttf", "times.ttf", "DejaVuSerif.ttf"]
    else:
        possible_fonts = ["arialbd.ttf" if bold else "arial.ttf", "Arial Bold.ttf" if bold else "Arial.ttf", "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"]

    for folder in font_dirs:
        for font_name in possible_fonts:
            font_path = folder / font_name
            try:
                if font_path.exists():
                    return ImageFont.truetype(str(font_path), size)
            except Exception:
                pass

    for font_name in possible_fonts:
        try:
            return ImageFont.truetype(font_name, size)
        except Exception:
            continue

    return ImageFont.load_default()


def draw_text_with_tracking(draw: ImageDraw.ImageDraw, position: tuple[int, int], text: str, font, fill, tracking: int = 0) -> None:
    x, y = position
    for char in text:
        draw.text((x, y), char, font=font, fill=fill)
        bbox = draw.textbbox((0, 0), char, font=font)
        x += (bbox[2] - bbox[0]) + tracking


def text_width_with_tracking(draw: ImageDraw.ImageDraw, text: str, font, tracking: int = 0) -> int:
    width = 0
    for char in text:
        bbox = draw.textbbox((0, 0), char, font=font)
        width += (bbox[2] - bbox[0]) + tracking
    return max(0, width - tracking)


def get_dynamic_footer_colors(reference_image: Image.Image):
    try:
        img = reference_image.convert("RGB")
        img.thumbnail((180, 180), Image.Resampling.LANCZOS)
        arr = np.asarray(img).reshape(-1, 3).astype(np.float32)
        brightness = arr.mean(axis=1)
        useful = arr[(brightness > 35) & (brightness < 235)]
        if len(useful) < 50:
            useful = arr

        max_c = useful.max(axis=1)
        min_c = useful.min(axis=1)
        saturation = max_c - min_c
        weights = 1.0 + (saturation / 255.0) * 2.5
        avg = np.average(useful, axis=0, weights=weights)
        r, g, b = avg
        total = r + g + b + 1e-6
        r_ratio, g_ratio, b_ratio = r / total, g / total, b / total

        tint_strength = 0.20
        white_base = np.array([255, 255, 255], dtype=np.float32)
        footer_bg_arr = white_base * (1 - tint_strength) + avg * tint_strength

        if r_ratio > 0.42 and r > g * 1.10 and r > b * 1.10:
            footer_bg = (255, 226, 226)
        elif g_ratio > 0.40 and g > r * 1.08 and g > b * 1.08:
            footer_bg = (226, 248, 229)
        elif b_ratio > 0.40 and b > r * 1.08 and b > g * 1.08:
            footer_bg = (226, 235, 255)
        else:
            footer_bg = tuple(np.clip(footer_bg_arr, 224, 255).astype(int))

        quote_color = (0, 0, 0)
        soft_color = (70, 64, 58)
        signature_color = (0, 0, 0)
        divider_color = tuple(int(max(170, c * 0.84)) for c in footer_bg)
        return footer_bg, quote_color, soft_color, signature_color, divider_color
    except Exception:
        return (250, 248, 243), (50, 47, 42), (92, 84, 74), (31, 27, 24), (214, 205, 190)


def add_mosaic_footer(image: Image.Image, reference_image: Optional[Image.Image] = None) -> Image.Image:
    img = image.convert("RGB")
    width, height = img.size
    footer_height = max(180, int(height * 0.08))
    padding_x = max(52, int(width * 0.045))
    inner_top = max(22, int(footer_height * 0.18))
    inner_bottom = max(20, int(footer_height * 0.16))

    color_source = reference_image if reference_image is not None else img
    footer_bg, quote_color, soft_color, signature_color, divider_color = get_dynamic_footer_colors(color_source)

    final_with_footer = Image.new("RGB", (width, height + footer_height), footer_bg)
    final_with_footer.paste(img, (0, 0))
    draw = ImageDraw.Draw(final_with_footer)

    line_y = height + max(12, int(footer_height * 0.10))
    draw.line((padding_x, line_y, width - padding_x, line_y), fill=divider_color, width=max(1, int(width * 0.00055)))

    quote = random.choice(MOSAIC_QUOTES).replace("\n", " ").strip()
    left_width = int(width * 0.80)
    quote_area_x = padding_x
    quote_area_right = left_width - max(18, int(width * 0.012))
    quote_max_width = max(80, quote_area_right - quote_area_x)

    base_quote_font_size = max(20, int(width * 0.0135))
    min_quote_font_size = max(12, int(base_quote_font_size * 0.62))
    regards_font_size = max(17, int(width * 0.0105))
    signature_font_size = max(30, int(width * 0.0205))

    quote_font_size = base_quote_font_size
    quote_font = get_font(quote_font_size, style="serif")
    quote_bbox = draw.textbbox((0, 0), quote, font=quote_font)
    quote_w = quote_bbox[2] - quote_bbox[0]

    while quote_w > quote_max_width and quote_font_size > min_quote_font_size:
        quote_font_size -= 1
        quote_font = get_font(quote_font_size, style="serif")
        quote_bbox = draw.textbbox((0, 0), quote, font=quote_font)
        quote_w = quote_bbox[2] - quote_bbox[0]

    if quote_w > quote_max_width:
        ellipsis = "…"
        trimmed_quote = quote
        while trimmed_quote and draw.textbbox((0, 0), trimmed_quote + ellipsis, font=quote_font)[2] > quote_max_width:
            trimmed_quote = trimmed_quote[:-1].rstrip()
        quote = trimmed_quote + ellipsis
        quote_bbox = draw.textbbox((0, 0), quote, font=quote_font)

    regards_font = get_font(regards_font_size, style="sans", bold=False)
    signature_font = get_font(signature_font_size, style="script")
    signature_gap = max(3, int(signature_font_size * 0.08))

    usable_h_start = height + inner_top
    usable_h_end = height + footer_height - inner_bottom
    usable_h = usable_h_end - usable_h_start

    quote_h = quote_bbox[3] - quote_bbox[1]
    quote_y = usable_h_start + max(0, (usable_h - quote_h) // 2)
    draw.text((quote_area_x, quote_y), quote, fill=quote_color, font=quote_font)

    regards_line = "Regards,"
    signature_line = "Team Aviv"
    tracking = max(1, int(regards_font_size * 0.07))

    regards_w = text_width_with_tracking(draw, regards_line, regards_font, tracking)
    regards_bbox = draw.textbbox((0, 0), regards_line, font=regards_font)
    regards_h = regards_bbox[3] - regards_bbox[1]
    sig_bbox = draw.textbbox((0, 0), signature_line, font=signature_font)
    sig_w = sig_bbox[2] - sig_bbox[0]
    sig_h = sig_bbox[3] - sig_bbox[1]

    block_h = regards_h + signature_gap + sig_h
    block_y = usable_h_start + max(0, (usable_h - block_h) // 2)
    right_area_x = left_width
    right_area_right = width - padding_x
    right_center_x = right_area_x + max(0, (right_area_right - right_area_x) // 2)

    regards_x = max(right_area_x, min(right_center_x - (regards_w // 2), right_area_right - regards_w))
    signature_x = max(right_area_x, min(right_center_x - (sig_w // 2), right_area_right - sig_w))

    draw_text_with_tracking(draw, (regards_x, block_y), regards_line, regards_font, soft_color, tracking=tracking)
    draw.text((signature_x, block_y + regards_h + signature_gap), signature_line, fill=signature_color, font=signature_font)
    return final_with_footer


def process_tile_library(file_paths: Iterable[str | Path], tile_size: int):
    """Load only small tile previews into RAM.

    This is important for Render Free because keeping every original uploaded
    photo in memory can crash the worker. The original file path is stored only
    so the sharpest image can be reopened if no main portrait is provided.
    """
    processed_tiles = {}
    for file_path in file_paths:
        try:
            file_path = Path(file_path)
            sample_bytes = file_path.read_bytes()[:8192]
            file_hash_prefix = hashlib.md5(sample_bytes).hexdigest()
            file_id = f"{file_path.name}_{file_path.stat().st_size}_{file_hash_prefix}"
            if file_id in processed_tiles:
                continue

            with Image.open(file_path) as opened:
                img = opened.convert("RGB")
                tile = ImageOps.fit(img, (tile_size, tile_size), Image.Resampling.LANCZOS)
            avg_color = np.array(tile).mean(axis=(0, 1))
            stddev = ImageStat.Stat(tile.convert("L")).stddev[0]
            processed_tiles[file_id] = {"img": tile, "color": avg_color, "stddev": stddev, "source": str(file_path)}
        except Exception:
            continue
    return list(processed_tiles.values())


def query_nearest(color_array: np.ndarray, tree, query_color: np.ndarray, k: int) -> np.ndarray:
    if tree is not None:
        _, idxs = tree.query(query_color, k=k)
        return np.atleast_1d(idxs)
    distances = np.linalg.norm(color_array - query_color, axis=1)
    return np.argsort(distances)[:k]


def apply_luminosity_blend(mosaic_img: Image.Image, target_img: Image.Image) -> Image.Image:
    mosaic_rgb = mosaic_img.convert("RGB")
    target_rgb = target_img.convert("RGB")
    multiplied = ImageChops.multiply(mosaic_rgb, target_rgb)
    return Image.blend(mosaic_rgb, multiplied, alpha=0.6)


def save_lead(name: str, email: str, file_name: str, storage_path: str | Path = "leads.csv") -> None:
    storage_path = Path(storage_path)
    storage_path.parent.mkdir(parents=True, exist_ok=True)
    file_exists = storage_path.exists()
    with storage_path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["Name", "Email", "File", "Time"])
        if not file_exists:
            writer.writeheader()
        writer.writerow({"Name": name.strip(), "Email": email.strip(), "File": file_name, "Time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})


def cleanup_old_files(folder: str | Path, max_age_minutes: int = 120) -> None:
    """Delete old generated files so free hosting disk does not fill up."""
    folder = Path(folder)
    if not folder.exists():
        return
    cutoff = datetime.now().timestamp() - (max_age_minutes * 60)
    for path in folder.glob("*"):
        try:
            if path.is_file() and path.name != ".gitkeep" and path.stat().st_mtime < cutoff:
                path.unlink(missing_ok=True)
        except Exception:
            pass


def load_target_safely(path: str | Path, max_side: int = 2400) -> Image.Image:
    """Open a target photo and shrink very large uploads before processing."""
    img = Image.open(path).convert("RGB")
    if max(img.size) > max_side:
        img.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    return img


def create_mosaic(
    tile_paths: list[str | Path],
    output_dir: str | Path,
    target_path: Optional[str | Path] = None,
    tile_res: int = 64,
    density: int = 120,
    target_sharpness: int = 150,
    random_k: int = 2,
    blend_mode: str = "Luminosity Multiply (Sharp)",
    alpha_mix: float = 0.15,
    export_fmt: str = "JPEG",
    add_footer: bool = True,
) -> MosaicResult:
    if not tile_paths:
        raise ValueError("Upload at least one tile image.")
    if tile_res not in [16, 32, 64]:
        raise ValueError("Tile resolution must be 16, 32, or 64 for the Render Free version.")
    density = int(max(30, min(160, density)))
    random_k = int(max(1, min(10, random_k)))
    alpha_mix = float(max(0.0, min(1.0, alpha_mix)))
    export_fmt = export_fmt.upper()
    if export_fmt not in {"JPEG", "PNG", "TIFF"}:
        export_fmt = "JPEG"

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    job_id = uuid.uuid4().hex

    tiles = process_tile_library(tile_paths, tile_res)
    if not tiles:
        raise ValueError("No valid tile images were found.")

    tile_colors = np.array([t["color"] for t in tiles])
    tree = KDTree(tile_colors) if KDTree is not None else None

    if target_path:
        target = load_target_safely(target_path)
        target_source = "uploaded main photo"
    else:
        target_pick = max(tiles, key=lambda x: x["stddev"])
        target = load_target_safely(target_pick["source"])
        target_source = "auto-selected sharpest tile photo"

    w, h = target.size
    grid_h = max(1, int(density * (h / w)))

    max_output_pixels = int(os.getenv("MAX_OUTPUT_PIXELS", "18000000"))
    while (density * tile_res) * (grid_h * tile_res) > max_output_pixels and density > 30:
        density -= 5
        grid_h = max(1, int(density * (h / w)))

    full_w = density * tile_res
    full_h = grid_h * tile_res

    target_res = target.resize((full_w, full_h), Image.Resampling.LANCZOS)
    if target_sharpness > 0:
        target_res = target_res.filter(ImageFilter.UnsharpMask(radius=2, percent=int(target_sharpness), threshold=3))

    target_rgb = np.array(target_res)
    target_blocks = target_rgb.reshape(grid_h, tile_res, density, tile_res, 3).mean(axis=(1, 3))
    placed_indices = np.zeros((grid_h, density), dtype=int)

    memmap_path = os.path.join(tempfile.gettempdir(), f"mosaic_engine_cache_{job_id}.dat")
    canvas_mem = np.memmap(memmap_path, dtype="uint8", mode="w+", shape=(full_h, full_w, 3))

    try:
        for y in range(grid_h):
            for x in range(density):
                region_color = target_blocks[y, x]
                idxs = query_nearest(tile_colors, tree, region_color, k=min(random_k + 4, len(tiles)))

                target_box = (x * tile_res, y * tile_res, (x + 1) * tile_res, (y + 1) * tile_res)
                target_crop = target_res.crop(target_box)

                neighbors = set()
                for dy, dx in [(0, -1), (-1, -1), (-1, 0), (-1, 1)]:
                    ny = y + dy
                    nx = x + dx
                    if 0 <= ny < grid_h and 0 <= nx < density:
                        neighbors.add(placed_indices[ny, nx])

                candidates = [int(i) for i in idxs if int(i) not in neighbors]
                if not candidates:
                    candidates = [int(idxs[0])]

                best_idx = int(random.choice(candidates[:random_k]))
                placed_indices[y, x] = best_idx
                raw_tile = tiles[best_idx]["img"]

                if blend_mode == "Luminosity Multiply (Sharp)":
                    blended = apply_luminosity_blend(raw_tile, target_crop)
                    final_tile = Image.blend(blended, target_crop, alpha=alpha_mix) if alpha_mix > 0 else blended
                else:
                    final_tile = Image.blend(raw_tile, target_crop, alpha=alpha_mix)

                canvas_mem[y * tile_res:(y + 1) * tile_res, x * tile_res:(x + 1) * tile_res] = np.array(final_tile)

        canvas_mem.flush()
        final_output = Image.fromarray(np.array(canvas_mem).copy())
    finally:
        try:
            del canvas_mem
            os.remove(memmap_path)
        except Exception:
            pass

    if add_footer:
        final_output = add_mosaic_footer(final_output, reference_image=target)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    ext = export_fmt.lower()
    if export_fmt == "JPEG":
        final_output = final_output.convert("RGB")
        ext = "jpg"
    download_name = f"mosaic_{ts}.{ext}"
    output_file = output_dir / f"{job_id}.{ext}"

    save_kwargs = {"format": export_fmt}
    if export_fmt == "JPEG":
        save_kwargs.update({"quality": int(os.getenv("JPEG_QUALITY", "92")), "optimize": True})
    final_output.save(output_file, **save_kwargs)

    preview_image = final_output.copy()
    preview_max_width = 1400
    if preview_image.width > preview_max_width:
        preview_image = preview_image.resize((preview_max_width, int(preview_image.height * preview_max_width / preview_image.width)), Image.Resampling.LANCZOS)
    preview_file = output_dir / f"{job_id}_preview.jpg"
    preview_image.convert("RGB").save(preview_file, "JPEG", quality=88)

    cx = final_output.width // 2
    cy = final_output.height // 2
    sz = min(400, final_output.width // 2, final_output.height // 2)
    crop_img = final_output.crop((cx - sz, cy - sz, cx + sz, cy + sz))
    crop_file = output_dir / f"{job_id}_crop.jpg"
    crop_img.convert("RGB").save(crop_file, "JPEG", quality=92)

    mime_ext = "jpeg" if ext == "jpg" else ext
    return MosaicResult(
        job_id=job_id,
        output_file=output_file.name,
        preview_file=preview_file.name,
        crop_file=crop_file.name,
        download_name=download_name,
        mime_type=f"image/{mime_ext}",
        width=final_output.width,
        height=final_output.height,
        tile_count=len(tiles),
        target_source=target_source,
    )
