#!/usr/bin/env python3
"""Create and manage Stone Art Sculpture products from product images."""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import io
import json
import mimetypes
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import requests

SKILL_DIR = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = SKILL_DIR / "config.local.env"
PRODUCT_REFERENCE = SKILL_DIR / "references" / "product-editor.md"
DEFAULT_COVER_PROMPT = (
    "请移除所有水印和覆盖文字；保留雕塑主体，不得变形或重绘。"
    "无论原图已有天空、树木、阳光、草地或其他户外背景，都必须完全替换为"
    "一个全新、独特、与雕塑材质和风格匹配的户外展示环境。"
    "大理石人物可使用优雅欧洲庭院或艺术展馆花园；喷泉、花盆、长椅可使用"
    "高级园林庭院或酒店花园；动物、抽象和金属雕塑可使用现代景观公园或"
    "极简建筑庭院。保持真实光影、地面接触和柔和投影，不添加文字、Logo、"
    "人物或无关物体，不改变图片尺寸。"
)

PRODUCT_FIELDS = [
    "sku",
    "title",
    "slug",
    "excerpt",
    "body_html",
    "body_markdown",
    "size",
    "material",
    "price",
    "cover_image",
    "seo_title",
    "seo_description",
    "status",
    "sort_order",
    "images",
    "category_ids",
]

PRIVATE_FIELDS = {
    "category_slugs",
    "category_paths",
    "image_alts",
    "missing_information",
    "claims_to_verify",
    "generated_by",
    "notes",
}


def watermark_enabled(
    config: dict[str, str],
    *,
    requested: bool = False,
    disabled: bool = False,
) -> bool:
    if disabled:
        return False
    if requested:
        return True
    return str(config.get("PRODUCT_WATERMARK_ENABLED", "false")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def watermark_options(config: dict[str, str]) -> dict[str, Any]:
    font_value = config.get(
        "PRODUCT_WATERMARK_FONT_PATH",
        "assets/fonts/GreatVibes-Regular.ttf",
    ).strip()
    font_path = Path(font_value).expanduser()
    if not font_path.is_absolute():
        font_path = SKILL_DIR / font_path
    return {
        "text": config.get("PRODUCT_WATERMARK_TEXT", "Stone Art Sculpture"),
        "subtitle": config.get("PRODUCT_WATERMARK_SUBTITLE", ""),
        "font_path": font_path,
        "colors": config.get(
            "PRODUCT_WATERMARK_COLORS",
            "#f2b45b,#e06c75,#8f8dff,#5cc9c0",
        ),
        "opacity": float(config.get("PRODUCT_WATERMARK_OPACITY", "0.50")),
        "width_ratio": float(
            config.get("PRODUCT_WATERMARK_WIDTH_RATIO", "0.42")
        ),
        "position": config.get("PRODUCT_WATERMARK_POSITION", "random"),
        "seed": config.get("PRODUCT_WATERMARK_SEED", ""),
        "margin_ratio": float(
            config.get("PRODUCT_WATERMARK_MARGIN_RATIO", "0.045")
        ),
        "rotation_degrees": float(
            config.get("PRODUCT_WATERMARK_ROTATION_DEGREES", "9")
        ),
        "jpeg_quality": int(
            config.get("PRODUCT_WATERMARK_JPEG_QUALITY", "94")
        ),
    }


def load_env(path: Path) -> dict[str, str]:
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
    return values


def load_config(path: Path = DEFAULT_CONFIG) -> dict[str, str]:
    values = load_env(path)
    for key in values:
        if key in os.environ:
            values[key] = os.environ[key]
    for key, value in os.environ.items():
        if key.startswith(("STONEART_", "DEEPSEEK_", "PRODUCT_", "FEISHU_")):
            values[key] = value
    return values


class ApiError(RuntimeError):
    def __init__(self, status: int, message: str, payload: Any = None):
        super().__init__(message)
        self.status = status
        self.payload = payload


class StoneArtClient:
    def __init__(self, config: dict[str, str]):
        self.base_url = config["STONEART_BASE_URL"].rstrip("/")
        self.username = config["STONEART_ADMIN_USER"]
        self.password = config["STONEART_ADMIN_PASSWORD"]
        self.session = requests.Session()
        self.token = ""

    def login(self) -> None:
        payload = {"username": self.username, "password": self.password}
        response = self.session.post(
            f"{self.base_url}/api/admin/session", json=payload, timeout=30
        )
        body = safe_json(response)
        if response.status_code == 401 and body.get("captcha_required"):
            captcha = self.session.get(
                f"{self.base_url}/api/admin/captcha", timeout=30
            )
            challenge = safe_json(captcha)
            match = re.search(r"(\d+)\s*\+\s*(\d+)", challenge.get("question", ""))
            if not match:
                raise ApiError(401, "captcha required but could not be parsed", challenge)
            payload["captcha_answer"] = str(int(match.group(1)) + int(match.group(2)))
            payload["captcha_token"] = challenge.get("token", "")
            response = self.session.post(
                f"{self.base_url}/api/admin/session", json=payload, timeout=30
            )
            body = safe_json(response)
        if response.status_code >= 400 or not body.get("token"):
            raise ApiError(response.status_code, body.get("error", "login failed"), body)
        self.token = body["token"]

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: Any = None,
        files: dict[str, Any] | None = None,
        timeout: int = 90,
    ) -> Any:
        if not self.token:
            self.login()
        headers = {"Authorization": f"Bearer {self.token}"}
        url = f"{self.base_url}{path}"
        for attempt in range(2):
            response = self.session.request(
                method,
                url,
                params=params,
                json=json_body,
                files=files,
                headers=headers,
                timeout=timeout,
            )
            body = safe_json(response)
            if response.status_code == 401 and attempt == 0:
                self.login()
                headers["Authorization"] = f"Bearer {self.token}"
                continue
            if response.status_code >= 400:
                raise ApiError(
                    response.status_code,
                    body.get("error", f"request failed ({response.status_code})"),
                    body,
                )
            return body
        raise ApiError(401, "authentication failed")

    def categories(self) -> list[dict[str, Any]]:
        return self.request("GET", "/api/admin/categories").get("items", [])

    def list_products(
        self,
        query: str = "",
        status: str = "",
        category_id: int = 0,
        page: int = 1,
        page_size: int = 100,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"page": page, "page_size": page_size}
        if query:
            params["q"] = query
        if status:
            params["status"] = status
        if category_id:
            params["category_id"] = category_id
        return self.request("GET", "/api/admin/products", params=params)

    def all_products(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for page in range(1, 100):
            data = self.list_products(page=page, page_size=100)
            items.extend(data.get("items", []))
            if page >= int(data.get("total_pages", 0)):
                break
        return items

    def get_product(self, product_id: int) -> dict[str, Any]:
        return self.request("GET", f"/api/admin/products/{product_id}")

    def find_product(self, slug: str = "", title: str = "") -> dict[str, Any]:
        needle = (slug or title).strip()
        if not needle:
            raise ValueError("find-product requires --slug or --title")
        for page in range(1, 100):
            data = self.list_products(query=needle, page=page, page_size=100)
            for item in data.get("items", []):
                if slug and item.get("slug") == slug:
                    return self.get_product(int(item["id"]))
                if title and str(item.get("title", "")).lower() == title.lower():
                    return self.get_product(int(item["id"]))
            if page >= int(data.get("total_pages", 0)):
                break
        raise ApiError(404, "product not found")

    def save_product(
        self, payload: dict[str, Any], product_id: int | None = None
    ) -> dict[str, Any]:
        method = "PUT" if product_id else "POST"
        path = f"/api/admin/products/{product_id}" if product_id else "/api/admin/products"
        return self.request(method, path, json_body=payload)

    def upload_media(self, file_path: Path, filename: str = "") -> dict[str, Any]:
        if not file_path.exists():
            raise FileNotFoundError(file_path)
        content_type = (
            mimetypes.guess_type(filename or file_path.name)[0]
            or "application/octet-stream"
        )
        with file_path.open("rb") as handle:
            return self.request(
                "POST",
                "/api/admin/media",
                files={"file": (filename or file_path.name, handle, content_type)},
                timeout=180,
            )

    def media_references(self, media_id: int) -> dict[str, Any]:
        return self.request("GET", f"/api/admin/media/{media_id}/references")


def safe_json(response: requests.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return {}


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def output_json(payload: Any, path: str = "") -> None:
    if path:
        write_json(Path(path).expanduser(), payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def slugify(value: str) -> str:
    value = value.lower().replace("&", " and ")
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")[:180]


def strip_markdown(value: str) -> str:
    value = re.sub(r"!\[[^\]]*\]\([^)]+\)", " ", value)
    value = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", value)
    value = re.sub(r"[*_`>#-]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def truncate(value: str, limit: int) -> str:
    value = re.sub(r"\s+", " ", value).strip()
    if len(value) <= limit:
        return value
    cut = value[: limit - 1].rsplit(" ", 1)[0].strip()
    return (cut or value[: limit - 1]).rstrip(".,;:") + "…"


def sanitize_body_markdown(body: str) -> tuple[str, list[str]]:
    warnings: list[str] = []
    lines = body.splitlines()
    first_content = next((i for i, line in enumerate(lines) if line.strip()), None)
    if first_content is not None and re.match(r"^\s*#\s+", lines[first_content]):
        warnings.append("Removed an H1 from body_markdown; the product title is the page H1.")
        lines.pop(first_content)
    remaining = "\n".join(lines)
    if re.search(r"(?m)^\s*#\s+", remaining):
        raise ValueError("body_markdown may contain only H2 and lower headings")
    return remaining.strip(), warnings


def category_index(categories: list[dict[str, Any]]) -> tuple[dict[int, dict[str, Any]], dict[str, dict[str, Any]]]:
    by_id = {int(item["id"]): item for item in categories}
    by_slug = {str(item.get("slug", "")): item for item in categories}

    def path_for(item: dict[str, Any]) -> str:
        names = [str(item.get("name") or "")]
        current = item
        seen: set[int] = set()
        while current.get("parent_id"):
            parent_id = int(current["parent_id"])
            if parent_id in seen or parent_id not in by_id:
                break
            seen.add(parent_id)
            current = by_id[parent_id]
            names.append(str(current.get("name") or ""))
        return " > ".join(reversed(names))

    for item in categories:
        item["_path"] = path_for(item)
    by_path = {str(item["_path"]).lower(): item for item in categories}
    return by_id, {**by_slug, **by_path}


def resolve_category_ids(
    payload: dict[str, Any], categories: list[dict[str, Any]]
) -> list[int]:
    by_id, by_name = category_index(categories)
    ids: list[int] = []
    for value in payload.get("category_ids") or []:
        try:
            ids.append(int(value))
        except (TypeError, ValueError):
            raise ValueError(f"invalid category id: {value}")
    for key in ("category_slugs", "category_paths", "categories"):
        raw_values = payload.get(key) or []
        if isinstance(raw_values, str):
            raw_values = [raw_values]
        for value in raw_values:
            key_name = str(value).strip().lower()
            item = by_name.get(key_name)
            if not item:
                raise ValueError(f"category not found: {value}")
            ids.append(int(item["id"]))
    result: list[int] = []
    for category_id in ids:
        item = by_id.get(category_id)
        if not item:
            raise ValueError(f"category not found: {category_id}")
        if not item.get("is_enabled", False):
            raise ValueError(f"category is disabled: {item.get('name')}")
        if category_id not in result:
            result.append(category_id)
    return result


def merge_defaults(payload: dict[str, Any], config: dict[str, str]) -> tuple[dict[str, Any], list[str]]:
    result = {key: value for key, value in payload.items() if key in PRODUCT_FIELDS}
    warnings: list[str] = []
    if result.get("body_markdown"):
        result["body_markdown"], body_warnings = sanitize_body_markdown(
            str(result["body_markdown"])
        )
        warnings.extend(body_warnings)
        result.pop("body_html", None)
    if not str(result.get("title") or "").strip():
        raise ValueError("title is required")
    if not str(result.get("slug") or "").strip():
        result["slug"] = slugify(str(result["title"]))
    result["slug"] = slugify(str(result["slug"]))
    result.setdefault("status", config.get("PRODUCT_DEFAULT_STATUS", "draft"))
    if result["status"] not in {"draft", "published"}:
        raise ValueError("status must be draft or published")
    result.setdefault(
        "sort_order", int(config.get("PRODUCT_DEFAULT_SORT_ORDER", "0") or 0)
    )
    result.setdefault("category_ids", [])
    result.setdefault("images", [])
    excerpt_source = strip_markdown(
        str(result.get("body_markdown") or result.get("body_html") or "")
    )
    if not str(result.get("excerpt") or "").strip() and excerpt_source:
        result["excerpt"] = truncate(excerpt_source, 200)
    if not str(result.get("seo_title") or "").strip():
        result["seo_title"] = truncate(str(result["title"]), 60)
    if not str(result.get("seo_description") or "").strip():
        result["seo_description"] = truncate(
            str(result.get("excerpt") or excerpt_source or result["title"]), 160
        )
    default_price = config.get("PRODUCT_DEFAULT_PRICE", "").strip()
    if default_price and not str(result.get("price") or "").strip():
        result["price"] = default_price
    return result, warnings


def validate_product(
    payload: dict[str, Any],
    *,
    category_ids: list[int],
    has_image: bool,
    allow_legacy_h1: bool = False,
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    title = str(payload.get("title") or "").strip()
    slug = str(payload.get("slug") or "").strip()
    body_html = str(payload.get("body_html") or "")
    body_markdown = str(payload.get("body_markdown") or "")
    if not title:
        errors.append("title is required")
    if not slug:
        errors.append("slug is required")
    elif not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug):
        errors.append("slug must contain lowercase letters, numbers, and hyphens")
    if not body_html and not body_markdown:
        errors.append("body_markdown or body_html is required")
    if not allow_legacy_h1 and re.search(r"<h1\b", body_html, re.I):
        errors.append("body_html must not contain H1")
    if len(title) > 180:
        errors.append("title is too long")
    public_copy = " ".join(
        str(payload.get(key) or "")
        for key in ("title", "excerpt", "body_markdown", "body_html", "seo_title", "seo_description")
    )
    if re.search(r"[\u0400-\u04ff\u4e00-\u9fff]", public_copy):
        errors.append(
            "public English product fields contain non-English script; remove it or request a translated product explicitly"
        )
    if payload.get("status") == "published":
        if not category_ids:
            errors.append("published products require at least one category")
        if not has_image:
            errors.append("published products require a cover image")
        if not str(payload.get("seo_title") or "").strip():
            warnings.append("SEO title is empty")
        if not str(payload.get("seo_description") or "").strip():
            warnings.append("SEO description is empty")
    if not payload.get("sku"):
        warnings.append("SKU is empty")
    if not payload.get("size"):
        warnings.append("Size is empty; do not invent dimensions")
    if not payload.get("material"):
        warnings.append("Material is empty; confirm it before making a material claim")
    return errors, warnings


def image_info(path: Path) -> dict[str, Any]:
    try:
        from PIL import Image, ImageOps
    except ImportError as exc:
        raise RuntimeError("Pillow is required; install requirements.txt") from exc
    with Image.open(path) as image:
        image = ImageOps.exif_transpose(image)
        width, height = image.size
        image_format = image.format or path.suffix.lstrip(".").upper()
    if width < 600 or height < 600:
        warning = "low resolution; inspect before publishing"
    else:
        warning = ""
    return {
        "path": str(path.resolve()),
        "width": width,
        "height": height,
        "format": image_format,
        "bytes": path.stat().st_size,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "warning": warning,
    }


def upload_images(
    client: StoneArtClient,
    paths: list[Path],
    alts: list[str],
    fallback_alt: str,
    *,
    watermark: bool = False,
    watermark_options_override: dict[str, Any] | None = None,
    max_bytes: int = 1 << 20,
    quality_start: int = 90,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    gallery: list[dict[str, Any]] = []
    asset_info: list[dict[str, Any]] = []
    warnings: list[str] = []
    for index, path in enumerate(paths):
        source_path = path
        watermark_info = None
        upload_path = path
        if watermark:
            from add_watermark import add_watermark

            digest = hashlib.sha256(path.read_bytes()).hexdigest()[:12]
            watermarked_path = (
                Path.cwd()
                / "work"
                / "processed"
                / "watermarked"
                / f"{path.stem}-{digest}-watermarked.jpg"
            )
            watermark_info = add_watermark(
                path,
                watermarked_path,
                **(watermark_options_override or {}),
            )
            upload_path = Path(watermark_info["output"])
            if upload_path.stat().st_size > max_bytes:
                compression = compress_image(
                    upload_path,
                    max_bytes=max_bytes,
                    quality_start=quality_start,
                )
                upload_path = Path(compression["path"])
                watermark_info["compression"] = compression
        info = image_info(upload_path)
        response = client.upload_media(upload_path)
        deduplicated = bool(response.get("deduplicated"))
        asset = response.get("asset") if deduplicated else response
        url = str(asset.get("url") or "")
        if not url:
            raise RuntimeError(f"media upload returned no URL for {upload_path.name}")
        alt = alts[index] if index < len(alts) else ""
        if not alt:
            alt = fallback_alt if index == 0 else f"{fallback_alt}, view {index + 1}"
        gallery.append({"url": url, "alt": alt, "sort_order": index + 1})
        asset_info.append(
            {
                **info,
                "source_path": str(source_path.resolve()),
                "watermark": watermark_info,
                "media_id": asset.get("id"),
                "url": url,
                "deduplicated": deduplicated,
                "original_name": asset.get("original_name"),
            }
        )
        if deduplicated:
            warnings.append(
                f"{upload_path.name} already existed in the media library; review its references"
            )
        if info.get("warning"):
            warnings.append(f"{upload_path.name}: {info['warning']}")
    return gallery, asset_info, warnings


def merge_gallery(
    payload: dict[str, Any],
    uploaded: list[dict[str, Any]],
    *,
    replace_gallery: bool = False,
) -> list[dict[str, Any]]:
    existing = []
    for item in payload.get("images") or []:
        if isinstance(item, dict) and str(item.get("url") or "").startswith("/uploads/"):
            existing.append(
                {
                    "url": item["url"],
                    "alt": str(item.get("alt") or payload.get("title") or ""),
                    "sort_order": int(item.get("sort_order") or len(existing) + 1),
                }
            )
    result = uploaded if replace_gallery else existing + uploaded
    for index, item in enumerate(result):
        item["sort_order"] = index + 1
    return result


def exact_duplicate_check(client: StoneArtClient, payload: dict[str, Any]) -> dict[str, Any]:
    slug = str(payload.get("slug") or "")
    title = str(payload.get("title") or "")
    sku = str(payload.get("sku") or "")
    for query in (slug, title, sku):
        if not query:
            continue
        matches = client.list_products(query=query, page=1, page_size=100).get("items", [])
        for item in matches:
            if item.get("slug") == slug:
                raise ValueError(f"product slug already exists: {slug}")
            if str(item.get("title", "")).lower() == title.lower():
                raise ValueError(f"product title already exists: {title}")
            if sku and str(item.get("sku") or "").lower() == sku.lower():
                raise ValueError(f"product SKU already exists: {sku}")
    return {"checked": True, "slug": slug}


def next_sku_for_series(
    client: StoneArtClient, series: str
) -> dict[str, Any]:
    series = series.strip()
    if not series:
        raise ValueError("SKU series is required")
    numbers: list[int] = []
    seen_skus: set[str] = set()
    for page in range(1, 100):
        data = client.list_products(query=series, page=page, page_size=100)
        for item in data.get("items", []):
            sku = str(item.get("sku") or "")
            if sku in seen_skus:
                continue
            seen_skus.add(sku)
            match = re.fullmatch(re.escape(series) + r"(\d+)", sku)
            if match:
                numbers.append(int(match.group(1)))
        if page >= int(data.get("total_pages", 0)):
            break
    next_number = max(numbers, default=0) + 1
    return {
        "series": series,
        "existing_match_count": len(numbers),
        "current_max_suffix": max(numbers, default=None),
        "suggested_sku": f"{series}{next_number}",
    }


def product_public_url(config: dict[str, str], slug: str) -> str:
    return config["STONEART_BASE_URL"].rstrip("/") + f"/products/{slug}/"


def product_admin_url(config: dict[str, str]) -> str:
    return config["STONEART_BASE_URL"].rstrip("/") + "/admin/#products"


def verify_public_product(config: dict[str, str], slug: str) -> dict[str, Any]:
    url = product_public_url(config, slug)
    try:
        response = requests.get(url, timeout=30, allow_redirects=True)
        return {"url": url, "status": response.status_code, "ok": response.status_code < 400}
    except Exception as exc:
        return {"url": url, "status": None, "ok": False, "error": str(exc)}


def call_deepseek(
    config: dict[str, str],
    messages: list[dict[str, Any]],
    *,
    response_format: dict[str, str] | None = None,
    temperature: float = 0.25,
    max_tokens: int = 16000,
    timeout: int = 240,
) -> str:
    if not config.get("DEEPSEEK_API_KEY"):
        raise RuntimeError("DEEPSEEK_API_KEY is not configured")
    base = config["DEEPSEEK_BASE_URL"].rstrip("/")
    headers = {
        "Authorization": f"Bearer {config['DEEPSEEK_API_KEY']}",
        "Content-Type": "application/json",
    }
    body: dict[str, Any] = {
        "model": config.get("DEEPSEEK_MODEL", "deepseek-flash"),
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if response_format:
        body["response_format"] = response_format
    response = requests.post(
        f"{base}/chat/completions", headers=headers, json=body, timeout=timeout
    )
    payload = safe_json(response)
    if response.status_code >= 400:
        raise ApiError(
            response.status_code,
            payload.get("error", "DeepSeek request failed"),
            payload,
        )
    choices = payload.get("choices") or []
    if not choices:
        raise ApiError(500, "DeepSeek returned no choices", payload)
    content = choices[0].get("message", {}).get("content", "")
    if isinstance(content, list):
        return "".join(
            item.get("text", "") for item in content if isinstance(item, dict)
        )
    return str(content)


def parse_json_model_output(value: str) -> Any:
    cleaned = value.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start >= 0 and end > start:
            return json.loads(cleaned[start : end + 1])
        raise


def image_data_url(path: Path) -> str:
    mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def compress_image(
    input_path: Path,
    max_bytes: int,
    quality_start: int = 90,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    try:
        from PIL import Image, ImageOps
    except ImportError as exc:
        raise RuntimeError("Pillow is required; install requirements.txt") from exc

    source_bytes = input_path.stat().st_size
    if source_bytes <= max_bytes:
        return {
            "path": str(input_path.resolve()),
            "source_bytes": source_bytes,
            "output_bytes": source_bytes,
            "compressed": False,
            "quality": None,
            "size": None,
        }

    output_dir = output_dir or (Path.cwd() / "work" / "processed")
    output_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(input_path.read_bytes()).hexdigest()[:12]
    output_path = output_dir / f"{digest}-{input_path.stem[:50]}-compressed.jpg"
    quality_start = max(70, min(95, int(quality_start)))
    qualities = sorted(
        {quality_start, 88, 84, 80, 76, 72, 68, 64},
        reverse=True,
    )
    scales = [1.0, 0.92, 0.84, 0.76, 0.68, 0.6]
    best: tuple[bytes, int, tuple[int, int], int] | None = None

    with Image.open(input_path) as source:
        image = ImageOps.exif_transpose(source).convert("RGB")
        original_size = image.size
        for scale in scales:
            width = max(1, round(original_size[0] * scale))
            height = max(1, round(original_size[1] * scale))
            if scale < 1 and max(width, height) < 1200:
                break
            resized = image if scale == 1 else image.resize(
                (width, height), Image.Resampling.LANCZOS
            )
            for quality in qualities:
                buffer = io.BytesIO()
                resized.save(
                    buffer,
                    format="JPEG",
                    quality=quality,
                    optimize=True,
                    progressive=True,
                )
                data = buffer.getvalue()
                if best is None or len(data) < len(best[0]):
                    best = (data, quality, resized.size, round(scale * 100))
                if len(data) <= max_bytes:
                    output_path.write_bytes(data)
                    return {
                        "path": str(output_path.resolve()),
                        "source_bytes": source_bytes,
                        "output_bytes": len(data),
                        "compressed": True,
                        "quality": quality,
                        "size": list(resized.size),
                        "original_size": list(original_size),
                        "scale_percent": round(scale * 100),
                    }

    if best is None:
        raise RuntimeError(f"could not compress image: {input_path}")
    output_path.write_bytes(best[0])
    if len(best[0]) > max_bytes:
        raise RuntimeError(
            f"could not reduce {input_path.name} below {max_bytes} bytes without excessive quality loss"
        )
    return {
        "path": str(output_path.resolve()),
        "source_bytes": source_bytes,
        "output_bytes": len(best[0]),
        "compressed": True,
        "quality": best[1],
        "size": list(best[2]),
        "original_size": list(original_size),
        "scale_percent": best[3],
    }


def get_wan_result_urls(response: Any) -> list[str]:
    output = getattr(response, "output", None)
    if not output:
        return []
    urls: list[str] = []
    for item in getattr(output, "results", None) or []:
        url = getattr(item, "url", None)
        if url:
            urls.append(url)
    for choice in getattr(output, "choices", None) or []:
        content = getattr(getattr(choice, "message", None), "content", None)
        if not isinstance(content, list):
            continue
        for item in content:
            if isinstance(item, dict) and item.get("image"):
                urls.append(item["image"])
    return urls


def collect_image_urls(value: Any) -> list[str]:
    urls: list[str] = []
    if isinstance(value, str):
        if value.startswith(("http://", "https://")):
            urls.append(value)
    elif isinstance(value, list):
        for item in value:
            urls.extend(collect_image_urls(item))
    elif isinstance(value, dict):
        for key, item in value.items():
            if key in {"url", "image", "image_url"} and isinstance(item, str):
                urls.extend(collect_image_urls(item))
            elif isinstance(item, (dict, list)):
                urls.extend(collect_image_urls(item))
    return urls


def call_wan_compatible(
    config: dict[str, str], input_path: Path, prompt: str, size: str
) -> str:
    base = config.get("ALIYUN_WAN_COMPATIBLE_BASE_URL", "").rstrip("/")
    api_key = config.get("ALIYUN_DASHSCOPE_API_KEY", "")
    if not base or not api_key:
        raise RuntimeError("Aliyun Wan compatible endpoint or API key is missing")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": config.get("WAN_IMAGE_MODEL", "wan2.7-image"),
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": image_data_url(input_path)},
                    {"type": "text", "text": prompt},
                ],
            }
        ],
        "n": 1,
        "size": size,
    }
    response = requests.post(
        f"{base}/chat/completions", headers=headers, json=payload, timeout=300
    )
    body = safe_json(response)
    if response.status_code >= 400:
        raise ApiError(
            response.status_code,
            body.get("error", "Wan2.7 compatible request failed"),
            body,
        )
    urls = collect_image_urls(body)
    if not urls:
        raise ApiError(500, "Wan2.7 response contained no image URL", body)
    return urls[0]


def edit_product_cover(
    config: dict[str, str],
    input_path: Path,
    output_path: Path | None = None,
    prompt: str = "",
    size: str = "",
) -> dict[str, Any]:
    try:
        from PIL import Image, ImageOps
    except ImportError as exc:
        raise RuntimeError("Pillow is required; install requirements.txt") from exc

    prompt = prompt.strip() or config.get("PRODUCT_COVER_AI_PROMPT", "").strip()
    prompt = prompt or DEFAULT_COVER_PROMPT
    size = size.strip() or config.get("PRODUCT_COVER_AI_SIZE", "2K")
    output_path = output_path or (
        Path.cwd()
        / "work"
        / "generated"
        / f"{hashlib.sha256(input_path.read_bytes()).hexdigest()[:12]}-ai-cover.jpg"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with Image.open(input_path) as source:
        original = ImageOps.exif_transpose(source).convert("RGB")
        original_size = original.size

    engine = "compatible"
    try:
        remote_url = call_wan_compatible(config, input_path, prompt, size)
    except Exception as compatible_error:
        try:
            import dashscope
            from dashscope.aigc.image_generation import ImageGeneration
            from dashscope.api_entities.dashscope_response import Message
        except ImportError:
            raise compatible_error
        base_url = config.get("ALIYUN_WAN_DASHSCOPE_BASE_URL", "").rstrip("/")
        if not base_url:
            raise compatible_error
        dashscope.base_http_api_url = base_url
        response = ImageGeneration.call(
            model=config.get("WAN_IMAGE_MODEL", "wan2.7-image"),
            api_key=config["ALIYUN_DASHSCOPE_API_KEY"],
            messages=[
                Message(
                    role="user",
                    content=[{"image": image_data_url(input_path)}, {"text": prompt}],
                )
            ],
            n=1,
            size=size,
        )
        if getattr(response, "status_code", 500) != 200:
            raise RuntimeError(
                f"Wan2.7 failed: status={getattr(response, 'status_code', '')} "
                f"code={getattr(response, 'code', '')} "
                f"message={getattr(response, 'message', '')}"
            )
        urls = get_wan_result_urls(response)
        if not urls:
            raise RuntimeError("Wan2.7 returned no image URL")
        remote_url = urls[0]
        engine = "dashscope"

    remote = requests.get(remote_url, timeout=180)
    remote.raise_for_status()
    output_path.write_bytes(remote.content)
    with Image.open(output_path) as result:
        image = ImageOps.exif_transpose(result).convert("RGB")
        if image.size != original_size:
            image = ImageOps.fit(
                image,
                original_size,
                method=Image.Resampling.LANCZOS,
                centering=(0.5, 0.5),
            )
        image.save(output_path, format="JPEG", quality=95, optimize=True)

    compression = compress_image(
        output_path,
        int(config.get("PRODUCT_IMAGE_MAX_BYTES", str(1 << 20))),
        int(config.get("PRODUCT_IMAGE_JPEG_QUALITY", "90")),
    )
    return {
        "input": str(input_path.resolve()),
        "output": compression["path"],
        "remote_url": remote_url,
        "model": config.get("WAN_IMAGE_MODEL", "wan2.7-image"),
        "engine": engine,
        "size": list(original_size),
        "prompt": prompt,
        "compression": compression,
    }


def vision_product(config: dict[str, str], path: Path, prompt: str = "") -> dict[str, Any]:
    prompt = prompt or (
        "Inspect this product image for a sculpture manufacturer. Return valid JSON "
        "with product_subject, product_type, visible_facts, reasonable_inferences, "
        "unknowns, watermark, sensitive_content, suggested_alt_text, title_directions, "
        "and category_hints. Separate visible evidence from inference. Never invent "
        "dimensions, SKU, price, material grade, or production time."
    )
    raw = call_deepseek(
        config,
        [
            {
                "role": "system",
                "content": (
                    "You are a precise visual product analyst for Stone Art Sculpture. "
                    "Return valid JSON only. Do not guess unsupported facts."
                ),
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": image_data_url(path)},
                    },
                    {"type": "text", "text": prompt},
                ],
            },
        ],
        response_format={"type": "json_object"},
    )
    result = parse_json_model_output(raw)
    if isinstance(result, dict):
        result.setdefault("local_path", str(path.resolve()))
    return result


def product_summary(item: dict[str, Any]) -> dict[str, Any]:
    return {
        key: item.get(key)
        for key in (
            "id",
            "sku",
            "title",
            "slug",
            "excerpt",
            "size",
            "material",
            "price",
            "status",
            "cover_image",
            "category_labels",
        )
    }


def similar_products(
    client: StoneArtClient, observation: dict[str, Any]
) -> list[dict[str, Any]]:
    subject = str(observation.get("product_subject") or "")
    product_type = str(observation.get("product_type") or "")
    facts = observation.get("visible_facts") or {}
    material = str(facts.get("material_cue") or "")
    query = " ".join(part for part in (material, subject or product_type) if part)
    data = client.list_products(query=query, page_size=20)
    items = data.get("items", [])
    if not items and product_type:
        items = client.list_products(query=product_type, page_size=20).get("items", [])
    return [product_summary(item) for item in items[:20]]


def draft_product(
    client: StoneArtClient,
    config: dict[str, str],
    observation: dict[str, Any],
    brief: str,
) -> dict[str, Any]:
    categories = client.categories()
    by_id, _ = category_index(categories)
    category_payload = []
    for item in categories:
        if not item.get("is_enabled", False):
            continue
        category_payload.append(
            {
                "id": int(item["id"]),
                "name": item.get("name"),
                "slug": item.get("slug"),
                "path": item.get("_path"),
                "parent_id": item.get("parent_id"),
                "product_count": item.get("product_count", 0),
            }
        )
    context = {
        "brand": config.get("PRODUCT_BRAND_NAME", "Stone Art Sculpture"),
        "user_brief": brief,
        "image_observation": observation,
        "image_count": len(observation.get("images") or []),
        "enabled_categories": category_payload,
        "similar_products": similar_products(client, observation),
        "required_output": (
            "Return one JSON object with title, slug, excerpt, body_markdown, seo_title, "
            "seo_description, status='draft', sku, size, material, price, category_ids, "
            "image_alts, missing_information, and claims_to_verify. Use only enabled "
            "category IDs from the supplied list. Do not include an H1 in body_markdown. "
            "If an image should appear inside the body, insert a placeholder such as "
            "{{product_image:1}} or {{product_image:2}} instead of inventing a URL. "
            "Placeholder numbers refer to the final gallery order: image 1 is the "
            "AI-processed cover, followed by the remaining original images."
        ),
    }
    system = PRODUCT_REFERENCE.read_text(encoding="utf-8")
    raw = call_deepseek(
        config,
        [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
        ],
        response_format={"type": "json_object"},
    )
    result = parse_json_model_output(raw)
    if not isinstance(result, dict):
        raise RuntimeError("DeepSeek did not return a JSON object")
    result["status"] = "draft"
    if not result.get("slug") and result.get("title"):
        result["slug"] = slugify(str(result["title"]))
    valid_ids = set(by_id)
    result["category_ids"] = [
        int(value)
        for value in result.get("category_ids") or []
        if str(value).isdigit() and int(value) in valid_ids
    ]
    result["category_paths"] = [
        str(by_id[category_id].get("_path") or "")
        for category_id in result["category_ids"]
    ]
    result["generated_by"] = "deepseek"
    return result


def normalize_cover_index(value: Any, image_count: int) -> int:
    try:
        index = int(value)
    except (TypeError, ValueError):
        index = 1
    if index < 1 or index > image_count:
        raise ValueError(f"cover index must be between 1 and {image_count}")
    return index - 1


def body_image_placeholder_indices(payload: dict[str, Any]) -> list[int]:
    body = str(payload.get("body_markdown") or payload.get("body_html") or "")
    return [
        int(value)
        for value in re.findall(
            r"\{\{product_image(?::|_)(\d+)\}\}", body, flags=re.I
        )
    ]


def build_create_preview(
    client: StoneArtClient,
    config: dict[str, str],
    draft: dict[str, Any],
    image_paths: list[Path],
    alts: list[str],
    publish: bool,
    cover_index: Any = 1,
    ai_cover: bool = True,
    watermark: bool = False,
) -> dict[str, Any]:
    payload, warnings = merge_defaults(draft, config)
    if publish:
        payload["status"] = "published"
    auto_series = config.get("PRODUCT_AUTO_SKU_SERIES", "").strip()
    if auto_series and not str(payload.get("sku") or "").strip():
        sku_result = next_sku_for_series(client, auto_series)
        payload["sku"] = sku_result["suggested_sku"]
    categories = client.categories()
    category_ids = resolve_category_ids(draft, categories)
    payload["category_ids"] = category_ids
    image_alts = alts or [str(value) for value in draft.get("image_alts") or []]
    errors: list[str] = []
    gallery_plan: list[dict[str, Any]] = []
    if image_paths:
        selected_index = normalize_cover_index(
            cover_index if cover_index not in {None, ""} else draft.get("cover_index", 1),
            len(image_paths),
        )
        infos = [image_info(path) for path in image_paths]
        max_bytes = int(config.get("PRODUCT_IMAGE_MAX_BYTES", str(1 << 20)))
        ordered_indices = [selected_index] + [
            index for index in range(len(image_paths)) if index != selected_index
        ]
        for order, source_index in enumerate(ordered_indices):
            path = image_paths[source_index]
            alt = (
                image_alts[source_index]
                if source_index < len(image_alts)
                else (
                    str(payload["title"])
                    if source_index == 0
                    else f"{payload['title']}, view {source_index + 1}"
                )
            )
            role = (
                "ai_cover"
                if order == 0 and ai_cover
                else ("cover" if order == 0 else "gallery")
            )
            gallery_plan.append(
                {
                    "order": order + 1,
                    "source_index": source_index + 1,
                    "role": role,
                    "path": str(path.resolve()),
                    "watermark": watermark,
                    "alt": (
                        alt + " in a landscaped outdoor setting"
                        if role == "ai_cover" and "landscape" not in alt.lower()
                        else alt
                    ),
                    "will_compress": path.stat().st_size > max_bytes,
                }
            )
            if path.stat().st_size > max_bytes:
                warnings.append(
                    f"{path.name} is larger than 1MB and will be compressed before upload"
                )
            if infos[source_index].get("warning"):
                warnings.append(
                    f"{path.name}: {infos[source_index]['warning']}"
                )
        if ai_cover and not config.get("ALIYUN_DASHSCOPE_API_KEY"):
            errors.append(
                "Aliyun image API key is missing; configure it or use --no-ai-cover"
            )
        placeholder_indices = body_image_placeholder_indices(payload)
        invalid_placeholders = [
            value for value in placeholder_indices if value < 1 or value > len(image_paths)
        ]
        if invalid_placeholders:
            errors.append(
                "body image placeholder index exceeds the available image count: "
                + ", ".join(str(value) for value in invalid_placeholders)
            )
        if not str(payload.get("cover_image") or "").startswith(("/uploads/", "http")):
            cover_prefix = "ai-cover" if ai_cover else "upload"
            payload["cover_image"] = f"<{cover_prefix}:{image_paths[selected_index].name}>"
        has_image = True
    else:
        infos = []
        has_image = bool(payload.get("cover_image"))
    validation_errors, validation_warnings = validate_product(
        payload, category_ids=category_ids, has_image=has_image
    )
    errors.extend(validation_errors)
    warnings.extend(validation_warnings)
    return {
        "ok": not errors,
        "dry_run": True,
        "errors": errors,
        "warnings": warnings,
        "image_files": infos,
        "image_alts": image_alts,
        "gallery_plan": gallery_plan,
        "cover_processing": {
            "enabled": ai_cover,
            "model": config.get("WAN_IMAGE_MODEL", "wan2.7-image"),
            "prompt": config.get("PRODUCT_COVER_AI_PROMPT", DEFAULT_COVER_PROMPT),
            "size": config.get("PRODUCT_COVER_AI_SIZE", "2K"),
        }
        if image_paths
        else None,
        "watermark": {
            "enabled": watermark and bool(image_paths),
            "text": config.get("PRODUCT_WATERMARK_TEXT", "Stone Art Sculpture"),
            "position": config.get("PRODUCT_WATERMARK_POSITION", "random"),
            "opacity": float(config.get("PRODUCT_WATERMARK_OPACITY", "0.50")),
        },
        "payload": payload,
        "category_paths": [
            item["_path"]
            for item in categories
            if int(item["id"]) in category_ids
        ],
        "sku_allocation": (
            {
                "mode": "automatic",
                "series": config.get("PRODUCT_AUTO_SKU_SERIES", "").strip(),
                "sku": payload.get("sku"),
            }
            if auto_series
            else {"mode": "manual", "sku": payload.get("sku")}
        ),
        "public_url": product_public_url(config, str(payload["slug"])),
    }


def prepare_product_images(
    config: dict[str, str],
    image_paths: list[Path],
    alts: list[str],
    cover_index: int,
    ai_cover: bool,
) -> dict[str, Any]:
    max_bytes = int(config.get("PRODUCT_IMAGE_MAX_BYTES", str(1 << 20)))
    quality = int(config.get("PRODUCT_IMAGE_JPEG_QUALITY", "90"))
    selected_index = normalize_cover_index(cover_index, len(image_paths))
    prepared: list[dict[str, Any]] = []
    ai_cover_result = None

    cover_source = image_paths[selected_index]
    if ai_cover:
        ai_cover_result = edit_product_cover(
            config,
            cover_source,
            output_path=(
                Path.cwd()
                / "work"
                / "generated"
                / (
                    hashlib.sha256(cover_source.read_bytes()).hexdigest()[:12]
                    + "-product-ai-cover.jpg"
                )
            ),
        )
        cover_path = Path(ai_cover_result["output"])
        cover_compression = ai_cover_result["compression"]
    else:
        cover_compression = compress_image(
            cover_source, max_bytes=max_bytes, quality_start=quality
        )
        cover_path = Path(cover_compression["path"])

    cover_alt = (
        alts[selected_index]
        if selected_index < len(alts)
        else "Product cover image"
    )
    if ai_cover and "landscape" not in cover_alt.lower():
        cover_alt += " in a landscaped outdoor setting"
    prepared.append(
        {
            "source_index": selected_index + 1,
            "role": "ai_cover" if ai_cover else "cover",
            "path": cover_path,
            "alt": cover_alt,
            "compression": cover_compression,
            "ai_cover": ai_cover_result,
        }
    )

    for index, path in enumerate(image_paths):
        if index == selected_index:
            continue
        compression = compress_image(
            path, max_bytes=max_bytes, quality_start=quality
        )
        alt = alts[index] if index < len(alts) else f"Product detail view {index + 1}"
        prepared.append(
            {
                "source_index": index + 1,
                "role": "gallery",
                "path": Path(compression["path"]),
                "alt": alt,
                "compression": compression,
                "ai_cover": None,
            }
        )
    return {
        "items": prepared,
        "paths": [item["path"] for item in prepared],
        "alts": [item["alt"] for item in prepared],
        "image_info": [
            {
                "source_index": item["source_index"],
                "role": item["role"],
                "source_path": str(image_paths[item["source_index"] - 1].resolve()),
                "upload_path": str(item["path"].resolve()),
                "compression": item["compression"],
                "ai_cover": item["ai_cover"],
                "alt": item["alt"],
            }
            for item in prepared
        ],
        "ai_cover_result": ai_cover_result,
    }


def render_product_images_in_body(
    payload: dict[str, Any], gallery: list[dict[str, Any]]
) -> None:
    if payload.get("body_markdown"):
        body = str(payload["body_markdown"])
        for index, image in enumerate(gallery, start=1):
            token_pattern = re.compile(
                r"\{\{product_image(?::|_)" + str(index) + r"\}\}", re.I
            )
            body = token_pattern.sub(
                f"![{image['alt']}]({image['url']})", body
            )
        payload["body_markdown"] = body
    if payload.get("body_html"):
        body = str(payload["body_html"])
        for index, image in enumerate(gallery, start=1):
            token_pattern = re.compile(
                r"\{\{product_image(?::|_)" + str(index) + r"\}\}", re.I
            )
            body = token_pattern.sub(
                (
                    f'<figure><img src="{image["url"]}" '
                    f'alt="{image["alt"]}" loading="lazy"></figure>'
                ),
                body,
            )
        payload["body_html"] = body


def backup_product(product: dict[str, Any]) -> Path:
    created = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = (
        Path.cwd()
        / "work"
        / "backups"
        / f"{created}-product-{product.get('id', 'unknown')}.json"
    )
    write_json(path, product)
    return path


def notification_time(config: dict[str, str]) -> str:
    timezone_name = config.get("FEISHU_TIMEZONE", "Asia/Shanghai").strip()
    try:
        zone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        timezone_name = "Asia/Shanghai"
        zone = ZoneInfo(timezone_name)
    return datetime.now(zone).strftime("%Y-%m-%d %H:%M %Z")


def is_chinese_title(value: str) -> bool:
    letters = [char for char in value if char.isalpha()]
    chinese = [char for char in letters if "\u4e00" <= char <= "\u9fff"]
    return bool(chinese) and len(chinese) >= max(1, round(len(letters) * 0.3))


def translate_title_zh(config: dict[str, str], title: str) -> str:
    title = title.strip()
    if not title or is_chinese_title(title):
        return title
    for _ in range(5):
        try:
            raw = call_deepseek(
                config,
                [
                    {
                        "role": "system",
                        "content": (
                            "Translate this Stone Art Sculpture product title into "
                            "natural Simplified Chinese. Return only the translated "
                            "title. Do not return an empty response."
                        ),
                    },
                    {"role": "user", "content": title},
                ],
                temperature=0.1,
                max_tokens=180,
            )
        except Exception:
            continue
        translated = raw.strip().strip("`").strip()
        first_line = next(
            (line.strip() for line in translated.splitlines() if line.strip()), ""
        )
        first_line = re.sub(
            r"^(?:中文标题|简体中文标题|标题)\s*[：:]\s*", "", first_line
        )
        first_line = first_line.strip().strip("\"'“”‘’").strip()
        chinese_count = sum(
            "\u4e00" <= char <= "\u9fff" for char in first_line
        )
        minimum_chinese = max(4, min(12, len(title.split())))
        if (
            first_line
            and first_line != title
            and is_chinese_title(first_line)
            and chinese_count >= minimum_chinese
        ):
            return first_line
    return ""


def feishu_signature(secret: str, timestamp: str) -> str:
    string_to_sign = f"{timestamp}\n{secret}"
    digest = hmac.new(
        string_to_sign.encode("utf-8"), digestmod=hashlib.sha256
    ).digest()
    return base64.b64encode(digest).decode("utf-8")


def notify_feishu_product(
    config: dict[str, str],
    *,
    event: str,
    product: dict[str, Any],
    changes: dict[str, Any] | None = None,
    note: str = "",
) -> dict[str, Any]:
    enabled = config.get(
        "FEISHU_PRODUCT_NOTIFY_ENABLED",
        config.get("FEISHU_BLOG_NOTIFY_ENABLED", "true"),
    ).lower()
    if enabled not in {"1", "true", "yes", "on"}:
        return {"enabled": False, "ok": True, "skipped": "disabled"}
    webhook = (
        config.get("FEISHU_PRODUCT_WEBHOOK_URL")
        or config.get("FEISHU_BLOG_WEBHOOK_URL", "")
    ).strip()
    secret = (
        config.get("FEISHU_PRODUCT_WEBHOOK_SECRET")
        or config.get("FEISHU_BLOG_WEBHOOK_SECRET", "")
    ).strip()
    if not webhook or not secret:
        return {"enabled": False, "ok": True, "skipped": "webhook missing"}

    action_labels = {
        "created": "新建产品草稿",
        "published": "发布新产品",
        "updated": "修改产品",
        "test": "飞书通知测试",
    }
    action = action_labels.get(event, event)
    status = str(product.get("status") or "draft")
    status_label = "已发布" if status == "published" else "草稿"
    title = str(product.get("title") or f"产品 {product.get('id', '')}")
    slug = str(product.get("slug") or "")
    public_link = product_public_url(config, slug) if status == "published" and slug else ""
    admin_link = product_admin_url(config)
    field_labels = {
        "title": "标题",
        "slug": "Slug",
        "excerpt": "摘要",
        "body_html": "正文",
        "body_markdown": "正文",
        "sku": "SKU",
        "size": "尺寸",
        "material": "材质",
        "price": "价格",
        "cover_image": "封面图片",
        "seo_title": "SEO 标题",
        "seo_description": "SEO 描述",
        "status": "状态",
        "images": "产品图片",
        "category_ids": "分类",
    }
    changed = [
        field_labels.get(key, key)
        for key in (changes or {})
        if key in field_labels
    ]
    lines = [
        f"**操作：** {action}",
        f"**标题：** {title}",
    ]
    translated = translate_title_zh(config, title)
    if translated and translated != title:
        lines.append(f"**中文标题：** {translated}")
    lines.append(f"**状态：** {status_label}")
    if product.get("id"):
        lines.append(f"**产品 ID：** {product['id']}")
    if product.get("sku"):
        lines.append(f"**SKU：** {product['sku']}")
    if product.get("material"):
        lines.append(f"**材质：** {product['material']}")
    if product.get("price"):
        lines.append(f"**价格：** {product['price']}")
    if changed:
        lines.append(f"**修改字段：** {', '.join(changed)}")
    if note:
        lines.append(f"**说明：** {note}")
    if public_link:
        lines.append(f"**产品链接：** [查看产品]({public_link})")
    lines.append(f"**后台管理：** [打开产品后台]({admin_link})")
    lines.append(f"**时间：** {notification_time(config)}")

    actions = []
    if public_link:
        actions.append(
            {
                "tag": "button",
                "type": "primary",
                "text": {"tag": "plain_text", "content": "查看产品"},
                "url": public_link,
            }
        )
    actions.append(
        {
            "tag": "button",
            "type": "default",
            "text": {"tag": "plain_text", "content": "后台管理"},
            "url": admin_link,
        }
    )
    payload = {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": {
                "template": {
                    "published": "green",
                    "created": "blue",
                    "updated": "orange",
                    "test": "wathet",
                }.get(event, "blue"),
                "title": {
                    "tag": "plain_text",
                    "content": f"Stone Art 产品通知 · {action}",
                },
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {"tag": "lark_md", "content": "\n".join(lines)},
                },
                {"tag": "action", "actions": actions},
            ],
        },
    }
    timestamp = str(int(time.time()))
    payload["timestamp"] = timestamp
    payload["sign"] = feishu_signature(secret, timestamp)
    response = requests.post(webhook, json=payload, timeout=30)
    body = safe_json(response)
    if response.status_code >= 400:
        raise ApiError(response.status_code, "Feishu webhook request failed", body)
    if body.get("StatusCode", body.get("code", 0)) not in {0, "0"}:
        raise ApiError(
            response.status_code,
            body.get("StatusMessage") or body.get("msg") or "Feishu rejected",
            body,
        )
    return {"enabled": True, "ok": True, "response": body}


def safe_notify_product(
    config: dict[str, str],
    *,
    event: str,
    product: dict[str, Any],
    changes: dict[str, Any] | None = None,
    note: str = "",
) -> dict[str, Any]:
    try:
        return notify_feishu_product(
            config, event=event, product=product, changes=changes, note=note
        )
    except Exception as exc:
        return {"enabled": True, "ok": False, "error": str(exc)}


def build_client(config: dict[str, str]) -> StoneArtClient:
    required = (
        "STONEART_BASE_URL",
        "STONEART_ADMIN_USER",
        "STONEART_ADMIN_PASSWORD",
    )
    missing = [key for key in required if not config.get(key)]
    if missing:
        raise RuntimeError(f"missing config: {', '.join(missing)}")
    client = StoneArtClient(config)
    client.login()
    return client


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument("--config", default=str(DEFAULT_CONFIG))
    sub = root.add_subparsers(dest="command", required=True)

    sub.add_parser("check", help="Validate login, products, categories, and media")

    cats = sub.add_parser("list-categories")
    cats.add_argument("--output", default="")

    products = sub.add_parser("list-products")
    products.add_argument("--query", default="")
    products.add_argument("--status", choices=["", "draft", "published"], default="")
    products.add_argument("--category-id", type=int, default=0)
    products.add_argument("--page", type=int, default=1)
    products.add_argument("--page-size", type=int, default=100)
    products.add_argument("--limit", type=int, default=0)
    products.add_argument("--full", action="store_true")

    get = sub.add_parser("get-product")
    get.add_argument("--id", type=int, required=True)
    get.add_argument("--output", default="")

    find = sub.add_parser("find-product")
    find.add_argument("--slug", default="")
    find.add_argument("--title", default="")

    vision = sub.add_parser("vision")
    vision.add_argument("--image", required=True)
    vision.add_argument("--prompt", default="")
    vision.add_argument("--output", default="")

    draft = sub.add_parser("draft-product")
    draft.add_argument("--observation", required=True)
    draft.add_argument("--brief", default="")
    draft.add_argument("--output", required=True)

    create = sub.add_parser("create-product")
    create.add_argument("--file", required=True)
    create.add_argument("--image", action="append", default=[])
    create.add_argument("--alt", action="append", default=[])
    create.add_argument("--cover-index", type=int, default=1)
    create.add_argument(
        "--no-ai-cover",
        action="store_true",
        help="Use the original cover image and skip Aliyun background replacement",
    )
    create.add_argument("--publish", action="store_true")
    create_watermark = create.add_mutually_exclusive_group()
    create_watermark.add_argument(
        "--watermark",
        action="store_true",
        help="Add the configured artistic watermark to every uploaded image",
    )
    create_watermark.add_argument(
        "--no-watermark",
        action="store_true",
        help="Skip watermarking even when PRODUCT_WATERMARK_ENABLED is true",
    )
    create.add_argument("--apply", action="store_true")
    create.add_argument("--no-notify", action="store_true")

    update = sub.add_parser("update-product")
    update.add_argument("--id", type=int, required=True)
    update.add_argument("--file", required=True)
    update.add_argument("--image", action="append", default=[])
    update.add_argument("--alt", action="append", default=[])
    update.add_argument("--replace-gallery", action="store_true")
    update_watermark = update.add_mutually_exclusive_group()
    update_watermark.add_argument(
        "--watermark",
        action="store_true",
        help="Add the configured artistic watermark to newly uploaded images",
    )
    update_watermark.add_argument(
        "--no-watermark",
        action="store_true",
        help="Skip watermarking even when PRODUCT_WATERMARK_ENABLED is true",
    )
    update.add_argument("--apply", action="store_true")
    update.add_argument("--no-notify", action="store_true")

    publish = sub.add_parser("publish-product")
    publish.add_argument("--id", type=int, required=True)
    publish.add_argument("--apply", action="store_true")
    publish.add_argument("--no-notify", action="store_true")

    verify = sub.add_parser("verify-product")
    verify.add_argument("--id", type=int, required=True)
    verify.add_argument("--output", default="")

    refs = sub.add_parser("media-references")
    refs.add_argument("--id", type=int, required=True)

    sku = sub.add_parser("next-sku")
    sku.add_argument("--series", default="")
    sku.add_argument("--prefix", default="")

    ai_cover = sub.add_parser("edit-product-cover")
    ai_cover.add_argument("--image", required=True)
    ai_cover.add_argument("--output", default="")
    ai_cover.add_argument("--prompt", default="")
    ai_cover.add_argument("--size", default="")

    prepare = sub.add_parser("prepare-image")
    prepare.add_argument("--image", required=True)
    prepare.add_argument("--output-dir", default="")
    prepare.add_argument("--max-bytes", type=int, default=0)

    test = sub.add_parser("test-feishu")
    test.add_argument("--title", default="Stone Art 产品通知测试")
    test.add_argument("--status", choices=["draft", "published"], default="draft")
    return root


def command_check(client: StoneArtClient, config: dict[str, str]) -> dict[str, Any]:
    categories = client.categories()
    products = client.list_products(page_size=1)
    media = client.request("GET", "/api/admin/media", params={"page": 1, "page_size": 1})
    return {
        "ok": True,
        "site": config["STONEART_BASE_URL"],
        "admin_user": config["STONEART_ADMIN_USER"],
        "products": products.get("total"),
        "categories": len(categories),
        "media": media.get("total"),
        "deepseek_configured": bool(config.get("DEEPSEEK_API_KEY")),
        "deepseek_model": config.get("DEEPSEEK_MODEL"),
        "auto_sku_series": config.get("PRODUCT_AUTO_SKU_SERIES", ""),
        "feishu_product_notify": config.get(
            "FEISHU_PRODUCT_NOTIFY_ENABLED",
            config.get("FEISHU_BLOG_NOTIFY_ENABLED", ""),
        ),
    }


def main() -> int:
    args = parser().parse_args()
    config = load_config(Path(args.config).expanduser())
    try:
        if args.command == "vision":
            result = vision_product(
                config, Path(args.image).expanduser(), args.prompt
            )
            output_json(result, args.output)
            return 0

        if args.command == "edit-product-cover":
            result = edit_product_cover(
                config,
                Path(args.image).expanduser(),
                Path(args.output).expanduser() if args.output else None,
                args.prompt,
                args.size,
            )
            output_json(result)
            return 0

        if args.command == "prepare-image":
            max_bytes = args.max_bytes or int(
                config.get("PRODUCT_IMAGE_MAX_BYTES", str(1 << 20))
            )
            result = compress_image(
                Path(args.image).expanduser(),
                max_bytes=max_bytes,
                quality_start=int(
                    config.get("PRODUCT_IMAGE_JPEG_QUALITY", "90")
                ),
                output_dir=(
                    Path(args.output_dir).expanduser()
                    if args.output_dir
                    else None
                ),
            )
            output_json(result)
            return 0

        if args.command == "test-feishu":
            result = notify_feishu_product(
                config,
                event="test",
                product={
                    "id": 0,
                    "title": args.title,
                    "slug": "",
                    "status": args.status,
                    "sku": "SAS-TEST",
                    "material": "Product notification test",
                },
                note="飞书 Webhook、签名和产品卡片发送验证成功。",
            )
            output_json(result)
            return 0

        client = build_client(config)

        if args.command == "check":
            output_json(command_check(client, config))
            return 0

        if args.command == "list-categories":
            categories = client.categories()
            category_index(categories)
            output_json(
                {
                    "items": [
                        {
                            "id": item.get("id"),
                            "parent_id": item.get("parent_id"),
                            "name": item.get("name"),
                            "slug": item.get("slug"),
                            "path": item.get("_path"),
                            "is_enabled": item.get("is_enabled"),
                            "product_count": item.get("product_count"),
                        }
                        for item in categories
                    ]
                },
                args.output,
            )
            return 0

        if args.command == "list-products":
            data = client.list_products(
                args.query,
                args.status,
                args.category_id,
                args.page,
                args.page_size,
            )
            items = data.get("items", [])
            if args.limit:
                items = items[: args.limit]
            if not args.full:
                items = [product_summary(item) for item in items]
            output_json({**data, "items": items})
            return 0

        if args.command == "get-product":
            output_json(client.get_product(args.id), args.output)
            return 0

        if args.command == "find-product":
            output_json(client.find_product(args.slug, args.title))
            return 0

        if args.command == "draft-product":
            observation = read_json(Path(args.observation).expanduser())
            result = draft_product(client, config, observation, args.brief)
            output_json(result, args.output)
            return 0

        if args.command == "create-product":
            draft = read_json(Path(args.file).expanduser())
            image_paths = [Path(value).expanduser() for value in args.image]
            apply_watermark = watermark_enabled(
                config,
                requested=args.watermark,
                disabled=args.no_watermark,
            )
            preview = build_create_preview(
                client,
                config,
                draft,
                image_paths,
                args.alt,
                args.publish,
                cover_index=args.cover_index,
                ai_cover=not args.no_ai_cover,
                watermark=apply_watermark,
            )
            if not args.apply:
                output_json(preview)
                return 0 if preview["ok"] else 2
            if preview["errors"]:
                output_json(preview)
                return 2

            payload = {key: value for key, value in preview["payload"].items() if key in PRODUCT_FIELDS}
            exact_duplicate_check(client, payload)
            category_ids = resolve_category_ids(draft, client.categories())
            prepared_assets = {
                "paths": [],
                "alts": [],
                "image_info": [],
                "ai_cover_result": None,
            }
            if image_paths:
                prepared_assets = prepare_product_images(
                    config,
                    image_paths,
                    args.alt or [str(value) for value in draft.get("image_alts") or []],
                    args.cover_index,
                    not args.no_ai_cover,
                )
            gallery, uploaded, upload_warnings = upload_images(
                client,
                prepared_assets["paths"],
                prepared_assets["alts"],
                str(payload["title"]),
                watermark=apply_watermark,
                watermark_options_override=watermark_options(config),
                max_bytes=int(
                    config.get("PRODUCT_IMAGE_MAX_BYTES", str(1 << 20))
                ),
                quality_start=int(
                    config.get("PRODUCT_IMAGE_JPEG_QUALITY", "90")
                ),
            )
            payload["images"] = merge_gallery(payload, gallery, replace_gallery=True)
            if gallery and not str(payload.get("cover_image") or "").startswith(("/uploads/", "http")):
                payload["cover_image"] = gallery[0]["url"]
            payload["category_ids"] = category_ids
            render_product_images_in_body(payload, payload["images"])
            errors, warnings = validate_product(
                payload,
                category_ids=category_ids,
                has_image=bool(payload.get("cover_image")),
            )
            warnings.extend(upload_warnings)
            if errors:
                output_json(
                    {
                        "ok": False,
                        "errors": errors,
                        "warnings": warnings,
                        "uploaded_media": uploaded,
                    }
                )
                return 2
            result = client.save_product(payload)
            product_id = int(result["id"])
            saved = client.get_product(product_id)
            public_check = (
                verify_public_product(config, str(saved.get("slug") or ""))
                if saved.get("status") == "published"
                else None
            )
            notification = (
                {"enabled": False, "ok": True, "skipped": "disabled by --no-notify"}
                if args.no_notify
                else safe_notify_product(
                    config,
                    event="published"
                    if saved.get("status") == "published"
                    else "created",
                    product=saved,
                )
            )
            output_json(
                {
                    "ok": True,
                    "id": product_id,
                    "status": saved.get("status"),
                    "public_url": product_public_url(config, saved.get("slug", "")),
                    "public_check": public_check,
                    "warnings": warnings,
                    "uploaded_media": uploaded,
                    "prepared_images": prepared_assets["image_info"],
                    "ai_cover": prepared_assets["ai_cover_result"],
                    "watermark": preview["watermark"],
                    "notification": notification,
                    "product": product_summary(saved),
                }
            )
            return 0

        if args.command == "update-product":
            current = client.get_product(args.id)
            patch = read_json(Path(args.file).expanduser())
            apply_watermark = watermark_enabled(
                config,
                requested=args.watermark,
                disabled=args.no_watermark,
            )
            categories = client.categories()
            merged = {
                key: current.get(key)
                for key in PRODUCT_FIELDS
                if key not in {"body_markdown"}
            }
            for key, value in patch.items():
                if key in PRODUCT_FIELDS:
                    merged[key] = value
            if "body_markdown" in patch:
                merged.pop("body_html", None)
            category_ids = resolve_category_ids(
                patch if any(key in patch for key in ("category_ids", "category_slugs", "category_paths", "categories")) else current,
                categories,
            )
            merged["category_ids"] = category_ids
            image_paths = [Path(value).expanduser() for value in args.image]
            merged, default_warnings = merge_defaults(merged, config)
            pending_info = [
                {**image_info(path), "will_watermark": apply_watermark}
                for path in image_paths
            ]
            pending_warnings = [
                f"{Path(item['path']).name}: {item['warning']}"
                for item in pending_info
                if item.get("warning")
            ]
            preview_payload = dict(merged)
            if image_paths:
                pending_gallery = [
                    {
                        "url": f"<upload:{path.name}>",
                        "alt": args.alt[index]
                        if index < len(args.alt)
                        else (
                            f"{merged.get('title')}, view {index + 1}"
                            if index
                            else str(merged.get("title") or "")
                        ),
                        "sort_order": index + 1,
                    }
                    for index, path in enumerate(image_paths)
                ]
                preview_payload["images"] = merge_gallery(
                    merged,
                    pending_gallery,
                    replace_gallery=args.replace_gallery,
                )
                if args.replace_gallery or not merged.get("cover_image"):
                    preview_payload["cover_image"] = pending_gallery[0]["url"]
            errors, validation_warnings = validate_product(
                preview_payload,
                category_ids=category_ids,
                has_image=bool(
                    preview_payload.get("cover_image")
                    or preview_payload.get("images")
                    or image_paths
                ),
                allow_legacy_h1=not any(
                    key in patch for key in ("body_html", "body_markdown")
                ),
            )
            changed = {
                key: {"before": current.get(key), "after": preview_payload.get(key)}
                for key in PRODUCT_FIELDS
                if current.get(key) != preview_payload.get(key)
            }
            if not args.apply:
                output_json(
                    {
                        "ok": not errors,
                        "dry_run": True,
                        "errors": errors,
                        "warnings": default_warnings
                        + validation_warnings
                        + pending_warnings,
                        "changed_fields": changed,
                        "pending_uploads": pending_info,
                        "payload": preview_payload,
                    }
                )
                return 0 if not errors else 2
            if errors:
                output_json({"ok": False, "errors": errors})
                return 2
            upload_warnings: list[str] = []
            uploaded: list[dict[str, Any]] = []
            if image_paths:
                gallery, uploaded, upload_warnings = upload_images(
                    client,
                    image_paths,
                    args.alt,
                    str(merged.get("title") or ""),
                    watermark=apply_watermark,
                    watermark_options_override=watermark_options(config),
                    max_bytes=int(
                        config.get("PRODUCT_IMAGE_MAX_BYTES", str(1 << 20))
                    ),
                    quality_start=int(
                        config.get("PRODUCT_IMAGE_JPEG_QUALITY", "90")
                    ),
                )
                merged["images"] = merge_gallery(
                    merged, gallery, replace_gallery=args.replace_gallery
                )
                if args.replace_gallery or not merged.get("cover_image"):
                    merged["cover_image"] = gallery[0]["url"]
            errors, final_warnings = validate_product(
                merged,
                category_ids=category_ids,
                has_image=bool(merged.get("cover_image") or merged.get("images")),
                allow_legacy_h1=not any(
                    key in patch for key in ("body_html", "body_markdown")
                ),
            )
            if errors:
                output_json(
                    {
                        "ok": False,
                        "errors": errors,
                        "uploaded_media": uploaded,
                    }
                )
                return 2
            changed = {
                key: {"before": current.get(key), "after": merged.get(key)}
                for key in PRODUCT_FIELDS
                if current.get(key) != merged.get(key)
            }
            backup = backup_product(current)
            client.save_product(merged, args.id)
            saved = client.get_product(args.id)
            notification = (
                {"enabled": False, "ok": True, "skipped": "disabled by --no-notify"}
                if args.no_notify or not changed
                else safe_notify_product(
                    config,
                    event="published"
                    if saved.get("status") == "published"
                    and current.get("status") != "published"
                    else "updated",
                    product=saved,
                    changes=changed,
                )
            )
            output_json(
                {
                    "ok": True,
                    "id": args.id,
                    "backup": str(backup.resolve()),
                    "changed_fields": changed,
                    "warnings": default_warnings
                    + validation_warnings
                    + final_warnings
                    + upload_warnings,
                    "uploaded_media": uploaded,
                    "notification": notification,
                    "product": product_summary(saved),
                }
            )
            return 0

        if args.command == "publish-product":
            current = client.get_product(args.id)
            payload = {key: current.get(key) for key in PRODUCT_FIELDS if key != "body_markdown"}
            payload["status"] = "published"
            category_ids = [int(value) for value in current.get("category_ids") or []]
            errors, warnings = validate_product(
                payload,
                category_ids=category_ids,
                has_image=bool(current.get("cover_image") or current.get("images")),
                allow_legacy_h1=True,
            )
            if not args.apply:
                output_json(
                    {
                        "ok": not errors,
                        "dry_run": True,
                        "errors": errors,
                        "warnings": warnings,
                        "product": product_summary(current),
                    }
                )
                return 0 if not errors else 2
            if errors:
                output_json({"ok": False, "errors": errors})
                return 2
            backup = backup_product(current)
            client.save_product(payload, args.id)
            saved = client.get_product(args.id)
            public_check = verify_public_product(
                config, str(saved.get("slug") or "")
            )
            notification = (
                {"enabled": False, "ok": True, "skipped": "disabled by --no-notify"}
                if args.no_notify
                else safe_notify_product(
                    config, event="published", product=saved
                )
            )
            output_json(
                {
                    "ok": True,
                    "id": args.id,
                    "backup": str(backup.resolve()),
                    "public_check": public_check,
                    "notification": notification,
                }
            )
            return 0

        if args.command == "verify-product":
            product = client.get_product(args.id)
            public_check = None
            if product.get("status") == "published":
                public_check = verify_public_product(
                    config, str(product.get("slug") or "")
                )
            result = {
                "ok": bool(product.get("title") and product.get("slug"))
                and (public_check is None or public_check.get("ok")),
                "product": product_summary(product),
                "category_ids": product.get("category_ids") or [],
                "image_count": len(product.get("images") or []),
                "public_check": public_check,
            }
            output_json(result, args.output)
            return 0 if result["ok"] else 2

        if args.command == "media-references":
            output_json(client.media_references(args.id))
            return 0

        if args.command == "next-sku":
            series = (args.series or args.prefix).strip()
            result = next_sku_for_series(client, series)
            result["note"] = (
                "Read-only SKU proposal. The create command rechecks uniqueness before saving."
            )
            output_json(result)
            return 0

        raise ValueError(f"unsupported command: {args.command}")
    except ApiError as exc:
        print(
            json.dumps(
                {"error": str(exc), "status": exc.status, "payload": exc.payload},
                ensure_ascii=False,
                indent=2,
            ),
            file=sys.stderr,
        )
        return 1
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
