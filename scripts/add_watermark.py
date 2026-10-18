#!/usr/bin/env python3
"""Add a translucent artistic brand watermark to product images."""

from __future__ import annotations

import argparse
import hashlib
import os
import random
from pathlib import Path
from typing import Any, Iterable

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps, ImageStat

SKILL_DIR = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = SKILL_DIR / "config.local.env"
DEFAULT_FONT = SKILL_DIR / "assets" / "fonts" / "GreatVibes-Regular.ttf"
DEFAULT_TEXT = "Stone Art Sculpture"
DEFAULT_SUBTITLE = ""
DEFAULT_COLORS = ("#f2b45b", "#e06c75", "#8f8dff", "#5cc9c0")
POSITION_CHOICES = (
    "random",
    "top-left",
    "top-right",
    "bottom-left",
    "bottom-right",
    "middle-left",
    "middle-right",
)


def _load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key] = value
    for key in values:
        if key in os.environ:
            values[key] = os.environ[key]
    return values


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _parse_colors(value: str | Iterable[str] | None) -> list[tuple[int, int, int]]:
    if not value:
        values = DEFAULT_COLORS
    elif isinstance(value, str):
        values = [part.strip() for part in value.split(",") if part.strip()]
    else:
        values = list(value)
    colors: list[tuple[int, int, int]] = []
    for raw in values:
        color = str(raw).strip()
        if color.startswith("#"):
            color = color[1:]
        if len(color) != 6:
            raise ValueError(f"watermark color must use #RRGGBB: {raw}")
        try:
            colors.append(tuple(int(color[index:index + 2], 16) for index in (0, 2, 4)))
        except ValueError as exc:
            raise ValueError(f"invalid watermark color: {raw}") from exc
    return colors or [tuple(int(value[index:index + 2], 16) for index in (0, 2, 4)) for value in DEFAULT_COLORS]


def _fit_font(
    text: str,
    font_path: Path,
    target_width: int,
    max_size: int,
) -> ImageFont.FreeTypeFont:
    if not text.strip():
        raise ValueError("watermark text cannot be empty")
    if not font_path.exists():
        raise FileNotFoundError(f"watermark font not found: {font_path}")
    low = 12
    high = max(low + 1, max_size)
    best = low
    while low <= high:
        size = (low + high) // 2
        font = ImageFont.truetype(str(font_path), size)
        bbox = font.getbbox(text)
        width = bbox[2] - bbox[0]
        if width <= target_width:
            best = size
            low = size + 1
        else:
            high = size - 1
    return ImageFont.truetype(str(font_path), best)


def _gradient(width: int, height: int, colors: list[tuple[int, int, int]]) -> Image.Image:
    gradient = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(gradient)
    for x in range(width):
        position = x / max(1, width - 1) * (len(colors) - 1)
        index = min(int(position), len(colors) - 1)
        next_index = min(index + 1, len(colors) - 1)
        fraction = position - index
        color = tuple(
            round(colors[index][channel] * (1 - fraction) + colors[next_index][channel] * fraction)
            for channel in range(3)
        )
        draw.line([(x, 0), (x, height)], fill=color + (255,))
    return gradient


def _render_text(
    text: str,
    font_path: Path,
    target_width: int,
    colors: list[tuple[int, int, int]],
    opacity: float,
) -> Image.Image:
    max_font_size = max(16, target_width)
    font = _fit_font(text, font_path, target_width, max_font_size)
    bbox = font.getbbox(text)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    padding = max(8, int(font.size * 0.20))
    size = (text_width + padding * 2, text_height + padding * 2)
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).text(
        (padding - bbox[0], padding - bbox[1]),
        text,
        font=font,
        fill=255,
    )

    colored = _gradient(size[0], size[1], colors)
    colored.putalpha(mask.point(lambda value: round(value * opacity)))

    shadow = Image.new("RGBA", size, (12, 22, 36, 0))
    shadow.putalpha(mask.point(lambda value: round(value * opacity * 0.36)))
    shadow = shadow.filter(ImageFilter.GaussianBlur(max(1.0, font.size * 0.018)))

    highlight = Image.new("RGBA", size, (255, 255, 255, 0))
    highlight.putalpha(mask.point(lambda value: round(value * opacity * 0.10)))
    highlight = highlight.filter(ImageFilter.GaussianBlur(max(0.8, font.size * 0.008)))

    layer = Image.new("RGBA", (size[0] + 8, size[1] + 8), (0, 0, 0, 0))
    layer.alpha_composite(highlight, (2, 3))
    layer.alpha_composite(shadow, (6, 6))
    layer.alpha_composite(colored, (4, 4))
    return layer


def _compose_wordmark(
    text: str,
    subtitle: str,
    font_path: Path,
    target_width: int,
    colors: list[tuple[int, int, int]],
    opacity: float,
) -> Image.Image:
    main = _render_text(text, font_path, target_width, colors, opacity)
    if not subtitle.strip():
        return main
    subtitle_width = max(160, round(target_width * 0.56))
    sub = _render_text(
        subtitle,
        font_path,
        subtitle_width,
        colors,
        max(0.20, opacity * 0.78),
    )
    gap = max(2, round(main.height * 0.015))
    width = max(main.width, sub.width)
    height = main.height + gap + sub.height
    result = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    result.alpha_composite(main, ((width - main.width) // 2, 0))
    result.alpha_composite(sub, ((width - sub.width) // 2, main.height + gap))
    return result


def _candidate_positions(
    image_size: tuple[int, int],
    watermark_size: tuple[int, int],
    margin: int,
) -> list[tuple[str, tuple[int, int]]]:
    width, height = image_size
    mark_width, mark_height = watermark_size
    left = margin
    right = max(margin, width - mark_width - margin)
    top = margin
    bottom = max(margin, height - mark_height - margin)
    middle_y = max(margin, (height - mark_height) // 2)
    return [
        ("top-left", (left, top)),
        ("top-right", (right, top)),
        ("bottom-left", (left, bottom)),
        ("bottom-right", (right, bottom)),
        ("middle-left", (left, middle_y)),
        ("middle-right", (right, middle_y)),
    ]


def _edge_score(
    edges: Image.Image,
    image_size: tuple[int, int],
    position: tuple[int, int],
    watermark_size: tuple[int, int],
) -> float:
    image_width, image_height = image_size
    x, y = position
    mark_width, mark_height = watermark_size
    sx = edges.width / image_width
    sy = edges.height / image_height
    box = (
        max(0, round(x * sx)),
        max(0, round(y * sy)),
        min(edges.width, round((x + mark_width) * sx)),
        min(edges.height, round((y + mark_height) * sy)),
    )
    if box[2] <= box[0] or box[3] <= box[1]:
        return 0.0
    return float(ImageStat.Stat(edges.crop(box)).mean[0])


def _choose_position(
    image: Image.Image,
    watermark_size: tuple[int, int],
    position: str,
    margin: int,
    rng: random.Random,
) -> tuple[str, tuple[int, int]]:
    candidates = _candidate_positions(image.size, watermark_size, margin)
    if position != "random":
        for name, point in candidates:
            if name == position:
                return name, point
        raise ValueError(f"unsupported watermark position: {position}")

    if image.height >= image.width * 1.15:
        candidates = [
            item for item in candidates if item[0] in {"top-left", "top-right"}
        ]

    preview = image.convert("L")
    preview.thumbnail((360, 360), Image.Resampling.LANCZOS)
    edges = preview.filter(ImageFilter.FIND_EDGES)
    ranked = sorted(
        (
            (_edge_score(edges, image.size, point, watermark_size), name, point)
            for name, point in candidates
        ),
        key=lambda item: item[0],
    )
    quietest = ranked[:3]
    _, name, point = rng.choice(quietest)
    return name, point


def _seed_for(path: Path, text: str, seed: str | int | None) -> int:
    if seed is not None and str(seed).strip():
        return int(hashlib.sha256(f"{seed}:{path.name}:{text}".encode("utf-8")).hexdigest()[:16], 16)
    digest = hashlib.sha256(path.read_bytes() + text.encode("utf-8")).hexdigest()
    return int(digest[:16], 16)


def add_watermark(
    input_path: Path,
    output_path: Path | None = None,
    *,
    text: str = DEFAULT_TEXT,
    subtitle: str = DEFAULT_SUBTITLE,
    font_path: Path = DEFAULT_FONT,
    colors: str | Iterable[str] | None = None,
    opacity: float = 0.50,
    width_ratio: float = 0.42,
    position: str = "random",
    seed: str | int | None = None,
    margin_ratio: float = 0.045,
    rotation_degrees: float = 9.0,
    jpeg_quality: int = 94,
) -> dict[str, Any]:
    """Create a new watermarked image and return processing details."""
    input_path = input_path.expanduser().resolve()
    if not input_path.exists():
        raise FileNotFoundError(f"image not found: {input_path}")
    if position not in POSITION_CHOICES:
        raise ValueError(f"position must be one of: {', '.join(POSITION_CHOICES)}")
    opacity = max(0.05, min(0.95, float(opacity)))
    width_ratio = max(0.12, min(0.90, float(width_ratio)))
    jpeg_quality = max(60, min(98, int(jpeg_quality)))

    with Image.open(input_path) as source:
        image = ImageOps.exif_transpose(source).convert("RGBA")
        icc_profile = source.info.get("icc_profile")

    rng = random.Random(_seed_for(input_path, text, seed))
    target_width = max(120, round(image.width * width_ratio))
    wordmark = _compose_wordmark(
        text,
        subtitle,
        font_path.expanduser().resolve(),
        target_width,
        _parse_colors(colors),
        opacity,
    )
    angle = rng.uniform(-rotation_degrees, rotation_degrees)
    wordmark = wordmark.rotate(angle, expand=True, resample=Image.Resampling.BICUBIC)
    margin = round(min(image.size) * margin_ratio)
    position_name, point = _choose_position(image, wordmark.size, position, margin, rng)
    jitter = round(min(image.size) * 0.012)
    x = max(0, min(image.width - wordmark.width, point[0] + rng.randint(-jitter, jitter)))
    y = max(0, min(image.height - wordmark.height, point[1] + rng.randint(-jitter, jitter)))
    image.alpha_composite(wordmark, (x, y))

    if output_path is None:
        output_path = input_path.with_name(f"{input_path.stem}-watermarked.jpg")
    output_path = output_path.expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    is_png = output_path.suffix.lower() == ".png"
    result = image if is_png else image.convert("RGB")
    save_options: dict[str, Any] = {"optimize": True}
    if icc_profile:
        save_options["icc_profile"] = icc_profile
    if is_png:
        result.save(output_path, format="PNG", **save_options)
    else:
        result.save(output_path, format="JPEG", quality=jpeg_quality, progressive=True, **save_options)

    return {
        "ok": True,
        "input": str(input_path),
        "output": str(output_path),
        "text": text,
        "subtitle": subtitle,
        "position": position_name,
        "rotation": round(angle, 2),
        "opacity": opacity,
        "width_ratio": width_ratio,
        "seed": _seed_for(input_path, text, seed),
        "size": list(result.size),
        "bytes": output_path.stat().st_size,
        "font": str(font_path.expanduser().resolve()),
    }


def add_watermarks(
    input_paths: list[Path],
    output_dir: Path,
    **options: Any,
) -> list[dict[str, Any]]:
    output_dir = output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for input_path in input_paths:
        input_path = input_path.expanduser()
        suffix = ".png" if input_path.suffix.lower() == ".png" else ".jpg"
        output_path = output_dir / f"{input_path.stem}-watermarked{suffix}"
        results.append(add_watermark(input_path, output_path, **options))
    return results


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument("--config", default=str(DEFAULT_CONFIG))
    root.add_argument("--image", action="append", required=True, help="Input image; repeat for multiple images")
    root.add_argument("--output-dir", default="")
    root.add_argument("--text", default="")
    root.add_argument("--subtitle", default="")
    root.add_argument("--font", default="")
    root.add_argument("--colors", default="")
    root.add_argument("--opacity", type=float, default=0.0)
    root.add_argument("--width-ratio", type=float, default=0.0)
    root.add_argument("--position", choices=POSITION_CHOICES, default="")
    root.add_argument("--seed", default="")
    root.add_argument("--margin-ratio", type=float, default=0.0)
    root.add_argument("--rotation", type=float, default=-1.0)
    root.add_argument("--jpeg-quality", type=int, default=0)
    return root


def main() -> int:
    args = parser().parse_args()
    config = _load_env(Path(args.config).expanduser())
    input_paths = [Path(value).expanduser() for value in args.image]
    output_dir = Path(
        args.output_dir
        or Path.cwd() / "work" / "processed" / "watermarked"
    )
    font_path = Path(
        args.font
        or config.get("PRODUCT_WATERMARK_FONT_PATH", "")
        or DEFAULT_FONT
    )
    if not font_path.is_absolute():
        font_path = SKILL_DIR / font_path
    options = {
        "text": args.text or config.get("PRODUCT_WATERMARK_TEXT", DEFAULT_TEXT),
        "subtitle": args.subtitle or config.get("PRODUCT_WATERMARK_SUBTITLE", DEFAULT_SUBTITLE),
        "font_path": font_path,
        "colors": args.colors or config.get("PRODUCT_WATERMARK_COLORS", ""),
        "opacity": args.opacity or float(config.get("PRODUCT_WATERMARK_OPACITY", "0.50")),
        "width_ratio": args.width_ratio or float(config.get("PRODUCT_WATERMARK_WIDTH_RATIO", "0.42")),
        "position": args.position or config.get("PRODUCT_WATERMARK_POSITION", "random"),
        "seed": args.seed or config.get("PRODUCT_WATERMARK_SEED", ""),
        "margin_ratio": args.margin_ratio or float(config.get("PRODUCT_WATERMARK_MARGIN_RATIO", "0.045")),
        "rotation_degrees": (
            args.rotation
            if args.rotation >= 0
            else float(config.get("PRODUCT_WATERMARK_ROTATION_DEGREES", "9"))
        ),
        "jpeg_quality": args.jpeg_quality or int(config.get("PRODUCT_WATERMARK_JPEG_QUALITY", "94")),
    }
    results = add_watermarks(input_paths, output_dir, **options)
    print(json_dumps({"ok": True, "items": results}))
    return 0


def json_dumps(value: Any) -> str:
    import json

    return json.dumps(value, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    raise SystemExit(main())
