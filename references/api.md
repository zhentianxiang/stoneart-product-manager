# Stone Art Product Admin API

## Authentication

Base URL comes from `STONEART_BASE_URL`.

`POST /api/admin/session`

```json
{
  "username": "admin",
  "password": "***"
}
```

If captcha is required, fetch `GET /api/admin/captcha`, solve the arithmetic question, then retry with:

```json
{
  "username": "admin",
  "password": "***",
  "captcha_token": "***",
  "captcha_answer": "12"
}
```

Protected requests use:

```text
Authorization: Bearer <token>
```

## Categories

`GET /api/admin/categories`

Returns:

```json
{
  "items": [
    {
      "id": 155765,
      "parent_id": 155763,
      "name": "Virgin Mary Statues",
      "slug": "virgin-mary-statues",
      "description": null,
      "sort_order": 1,
      "is_enabled": true,
      "product_count": 49
    }
  ]
}
```

Category IDs are database IDs. Always fetch them live; never guess.

## Products

- `GET /api/admin/products?page=1&page_size=30&q=&status=&category_id=`
- `GET /api/admin/products/{id}`
- `POST /api/admin/products`
- `PUT /api/admin/products/{id}`
- `PATCH /api/admin/products/status`
- `DELETE /api/admin/products/{id}`

Product writable fields:

```text
sku
title
slug
excerpt
body_html
body_markdown
size
material
price
cover_image
seo_title
seo_description
status
sort_order
images
category_ids
```

`title` and `slug` are required. `status` must be `draft` or `published`.

When `body_markdown` is sent, the server converts it to HTML and overwrites `body_html`. When updating existing HTML content, send `body_html` and omit `body_markdown` unless an intentional rewrite is requested.

### Product image shape

```json
{
  "images": [
    {
      "url": "/uploads/example.jpg",
      "alt": "Outdoor bronze heron sculpture",
      "sort_order": 1
    }
  ]
}
```

### Category IDs

```json
{
  "category_ids": [155844]
}
```

## Media

- `GET /api/admin/media?page=1&page_size=40&q=&usage=&task=&ref=`
- `POST /api/admin/media` with multipart field `file`
- `GET /api/admin/media/{id}/references`

Upload response:

- New media: asset object containing `id`, `url`, `original_name`, `content_type`, and `size_bytes`.
- Deduplicated content: `{"deduplicated": true, "asset": {...}}`.
- Duplicate filename with different content: HTTP `409`.

The upload API accepts JPEG, PNG, GIF, and WebP up to the server's configured multipart limit.

## Public Product URL

```text
/products/{slug}/
```

## CLI Reference

```bash
python scripts/stoneart_products.py check
python scripts/stoneart_products.py list-categories
python scripts/stoneart_products.py list-products --query "bronze bird"
python scripts/stoneart_products.py get-product --id 7844
python scripts/stoneart_products.py vision --image product.jpg
python scripts/stoneart_products.py draft-product \
  --observation work/example/observation.json \
  --output work/example/draft.json
python scripts/stoneart_products.py create-product \
  --file work/example/draft.json \
  --image work/example/images/front.jpg \
  --cover-index 1
python scripts/stoneart_products.py create-product \
  --file work/example/draft.json \
  --image work/example/images/front.jpg \
  --cover-index 1 \
  --publish \
  --apply
python scripts/stoneart_products.py edit-product-cover \
  --image work/example/images/front.jpg \
  --output work/example/images/ai-cover.jpg
python scripts/stoneart_products.py prepare-image \
  --image work/example/images/detail.jpg
python scripts/stoneart_products.py verify-product --id 12345
python scripts/stoneart_products.py update-product \
  --id 12345 \
  --file work/example/patch.json
python scripts/stoneart_products.py publish-product --id 12345
python scripts/stoneart_products.py media-references --id 58332
python scripts/stoneart_products.py next-sku --series SAS-215
python scripts/add_watermark.py \
  --image work/example/images/product-01.jpg \
  --output-dir work/example/images/watermarked
python scripts/stoneart_products.py sync-knowledge-base --preview
python scripts/stoneart_products.py sync-knowledge-base
```

## Product Image Watermarks

`add_watermark.py` creates a new copy with a translucent multicolor script watermark. It supports `random`, `top-left`, `top-right`, `bottom-left`, `bottom-right`, `middle-left`, and `middle-right` positions. For portrait product photos, `random` selects between the top corners so the mark remains inside the product page's top-cropped gallery frame.

`create-product` and `update-product` accept `--watermark` and `--no-watermark`. When neither is supplied, `PRODUCT_WATERMARK_ENABLED` controls the behavior. The upload pipeline writes watermarked copies under `work/processed/watermarked/`, recompresses them when necessary, and never overwrites source images.

## Local KB Website Sync

The Local KB admin API requires an authenticated session and an allowed `Origin` header:

- `POST /api/auth/login` with `username` and `password`
- `GET /api/imports/stoneart/preview` for a read-only preview
- `POST /api/imports/stoneart/sync` to sync products, images, exports, vector indexing, and translations

Configure `LOCAL_KB_BASE_URL`, `LOCAL_KB_ADMIN_ORIGIN`, `LOCAL_KB_ADMIN_USERNAME`, and `LOCAL_KB_ADMIN_PASSWORD`. Keep `LOCAL_KB_ADMIN_ORIGIN` on the public HTTPS origin even when `LOCAL_KB_BASE_URL` uses the local Docker proxy at `http://127.0.0.1:3210`.

After a published product is created, a published product is updated, or a draft is published, the CLI calls the sync endpoint automatically when `LOCAL_KB_SYNC_ENABLED=true`. The result appears under `knowledge_sync`. Product saves succeed even if Local KB returns an authentication, timeout, connectivity, or license error.

## Category and SKU Allocation

- Categories are live database records identified by `category_ids`.
- Use `category_slugs` or full `category_paths` in a draft when human-readable selection is easier.
- The CLI resolves those names against `GET /api/admin/categories`.
- Missing or disabled categories stop the create/update before writing.
- `PRODUCT_AUTO_SKU_SERIES` selects the active SKU family.
- `next-sku --series SAS-215` reads existing products in that family and returns the next available value.
- Automatic SKU allocation is checked again against exact SKU matches before the product is saved.

## Product Image Pipeline

For new product creation:

1. Validate every local image with Pillow.
2. Compress files larger than `PRODUCT_IMAGE_MAX_BYTES` into `work/processed/`.
3. Send only the selected `--cover-index` image to Aliyun Wan2.7.
4. Restore the generated image to the source dimensions.
5. Compress the generated image when necessary.
6. Upload the AI cover as image 1.
7. Upload each remaining original image in order.

The final gallery length equals the number of supplied original images. The original hero is replaced by the AI cover in that list.

`body_markdown` may contain:

```text
{{product_image:1}}
{{product_image:2}}
```

The CLI replaces them with Markdown figures after media upload. This also applies to `update-product`: placeholders are resolved against the final gallery after new images are merged or replace the existing gallery. An out-of-range placeholder, or one placed inside an existing `<figure>`, stops the save.

Relevant configuration:

```dotenv
ALIYUN_WAN_COMPATIBLE_BASE_URL=...
ALIYUN_WAN_DASHSCOPE_BASE_URL=...
ALIYUN_DASHSCOPE_API_KEY=...
WAN_IMAGE_MODEL=wan2.7-image
PRODUCT_COVER_AI_SIZE=2K
PRODUCT_COVER_AI_PROMPT=...
PRODUCT_IMAGE_MAX_BYTES=1048576
PRODUCT_IMAGE_JPEG_QUALITY=90
```

## Troubleshooting

- `title and slug are required`: fill both fields.
- `status must be draft or published`: use a supported status.
- `category not found or disabled`: fetch fresh categories and use an enabled leaf.
- `slug already exists`: improve the product distinction or update the existing product instead.
- `only image uploads are allowed`: upload JPEG, PNG, GIF, or WebP.
- `filename already exists`: rename the local file; do not overwrite the library asset.
