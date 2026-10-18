---
name: stoneart-product-manager
description: End-to-end creation and publishing of Stone Art Sculpture products from a product image or reference photo. Use this skill whenever the user sends a sculpture, statue, fountain, planter, bench, fireplace, gazebo, bust, relief, or other product image and asks to identify it, write its product page, create a draft, add it to the company website, upload its gallery images, set its category, optimize it for Google SEO, add or configure product-image watermarks, update an existing product, or 上架/发布/新建公司产品. Also use it for near-miss requests such as “把这个图片放到产品里”, “根据图片写一个产品”, “上架这个雕塑”, “给产品图片加水印”, or when the user wants ready-to-copy product-listing prompts, even if they do not name this skill.
compatibility: Requires Python 3.10+, network access, requests, Pillow, and dashscope. Uses Aliyun Wan2.7 for AI product covers and DeepSeek for fallback vision and structured draft generation.
---

# Stone Art Product Manager

Create production-ready Stone Art Sculpture products from images, including image understanding, category selection, product copy, SEO fields, media upload, gallery creation, publication, verification, and Feishu notification.

## Configuration

Read credentials from `config.local.env` in this skill directory. Environment variables override that file. Never print passwords, API keys, bearer tokens, or webhook secrets in chat or logs.

If `config.local.env` is absent:

```bash
cp config.example.env config.local.env
chmod 600 config.local.env
```

Run a read-only configuration check:

```bash
cd <skill-directory>
python scripts/stoneart_products.py check
```

Product-cover configuration:

```dotenv
ALIYUN_WAN_COMPATIBLE_BASE_URL=...
ALIYUN_WAN_DASHSCOPE_BASE_URL=...
ALIYUN_DASHSCOPE_API_KEY=...
WAN_IMAGE_MODEL=wan2.7-image
PRODUCT_COVER_AI_SIZE=2K
PRODUCT_COVER_AI_PROMPT=请移除所有水印和覆盖文字；保留雕塑主体，不得变形或重绘。...
PRODUCT_IMAGE_MAX_BYTES=1048576
PRODUCT_IMAGE_JPEG_QUALITY=90
```

Wan2.7 is used for the selected product cover. DeepSeek is not used for background replacement.

Product watermark configuration:

```dotenv
PRODUCT_WATERMARK_ENABLED=true
PRODUCT_WATERMARK_TEXT=Stone Art Sculpture
PRODUCT_WATERMARK_POSITION=random
PRODUCT_WATERMARK_COLORS=#f2b45b,#e06c75,#8f8dff,#5cc9c0
PRODUCT_WATERMARK_OPACITY=0.50
PRODUCT_WATERMARK_WIDTH_RATIO=0.42
PRODUCT_WATERMARK_FONT_PATH=assets/fonts/GreatVibes-Regular.ttf
```

The bundled Great Vibes font is distributed under the SIL Open Font License. The watermark is drawn after AI cover generation and before upload, so the AI prompt does not need to create or preserve any overlay text.

## When the User Asks How to Use the Skill

If the user asks what the skill can do, requests prompt examples, or invokes it without a concrete image or product:

1. Read `references/usage-prompts.md`.
2. Show the short workflow menu for new products, multi-image products, drafts, updates, and batch intake.
3. Provide the most relevant copyable prompts.
4. Do not call the production API or create a product until the user chooses a task.

## Required References

Read only the references needed for the current task:

- Image inspection and observation schema: `references/image-analysis.md`.
- Product copy, category selection, specifications, and Google SEO: `references/product-editor.md`.
- Ready-to-copy prompts: `references/usage-prompts.md`.
- API fields, payloads, and troubleshooting: `references/api.md`.

## Core Workflow

### 1. Establish the intent

Determine whether the user wants:

- A product draft only.
- A published product (`上架` or `发布`).
- An update to an existing product.

If the user explicitly says `上架`, `发布`, `publish`, or `go live`, the final action may publish. Otherwise create a draft.

If the user supplies only an image and no product facts, do not invent dimensions, SKU, weight, lead time, price, or material grade. Missing facts stay blank or become `[VERIFY]` notes outside the live product fields.

### 2. Inspect the image with Codex first

Use Codex's own image viewing capability on every supplied image. Prefer `view_image`; do not call DeepSeek merely because the task is multi-step.

Record:

- Primary subject and object type
- Material and finish only when visually supportable
- Color, style, period, pose, and visible details
- Intended setting and buyer use
- Multiple-image relationships, angles, details, and packaging shots
- Visible watermark, source logo, product code, or overlaid text
- Sensitive content or misleading image elements
- Concrete alt text
- Which image is the strongest front/hero view and should become the AI cover

Write the observations to `work/<slug>/observation.json` using the schema in `references/image-analysis.md`.

Use DeepSeek vision only when Codex cannot inspect the image reliably:

```bash
python scripts/stoneart_products.py vision \
  --image work/<slug>/images/product.jpg \
  --output work/<slug>/vision.json
```

### 3. Gather category and duplicate context

Load the live category tree:

```bash
python scripts/stoneart_products.py list-categories \
  --output work/<slug>/categories.json
```

Search for closely related products before naming the new one:

```bash
python scripts/stoneart_products.py list-products \
  --query "bronze heron" \
  --limit 20
```

Choose the most specific enabled leaf category. Add a parent category only when the website already uses that pattern. Do not create a new category unless the user explicitly asks.

Category IDs are never hard-coded in the skill. The create command resolves `category_ids`, `category_slugs`, or full `category_paths` against the latest admin category tree and rejects missing or disabled categories.

The production site uses several historical SKU series. Do not increment the global maximum SKU blindly. Configure the currently active series in `config.local.env`:

```dotenv
PRODUCT_AUTO_SKU_SERIES=SAS-215
```

When a draft has no SKU and this series is configured, the skill scans the latest products in that series and proposes the next number, such as `SAS-21559`. The create command rechecks exact SKU uniqueness before saving. Leave the setting blank if the user must supply an external SKU.

Preview the next SKU without writing:

```bash
python scripts/stoneart_products.py next-sku --series SAS-215
```

### 4. Create the structured product draft

Use Codex to write the draft from the observations, or let the bundled DeepSeek drafting command produce a first pass:

```bash
python scripts/stoneart_products.py draft-product \
  --observation work/<slug>/observation.json \
  --brief "Target buyers comparing outdoor bronze heron sculptures" \
  --output work/<slug>/draft.json
```

Review the generated JSON. Correct category IDs, remove unsupported claims, and ensure the content follows `references/product-editor.md`.

Required public fields:

- `title`
- `slug`
- `excerpt`
- `body_markdown`
- `seo_title`
- `seo_description`
- `status` (`draft` unless publication was explicitly requested)

Optional factual fields:

- `sku`
- `size`
- `material`
- `price`
- `sort_order`
- `category_ids`
- `image_alts`

`sku` may be omitted when automatic numbering is enabled. Category selection is still reviewed by Codex, but the resulting category IDs are validated against the live taxonomy.

The product page template renders the title as H1. Never include another H1 in the body. Use H2 for major sections and H3 only below an H2.

When an image should appear inside the product body, use a gallery placeholder instead of inventing an upload URL:

```text
{{product_image:1}}
{{product_image:2}}
```

The create command replaces placeholders with the final CMS URLs after upload. Image 1 is the AI-processed cover; the remaining numbers follow the final gallery order.

### 5. Preview the exact product payload

Run without `--apply`:

```bash
python scripts/stoneart_products.py create-product \
  --file work/<slug>/draft.json \
  --image work/<slug>/images/product-01.jpg \
  --image work/<slug>/images/product-02.jpg \
  --cover-index 1
```

The preview resolves category slugs to IDs, checks slug conflicts, validates required fields, shows which source image will become the AI cover, lists the final gallery order, and marks images that will be compressed. It does not call Aliyun or upload anything.

### 6. Upload images and create the product

For a draft:

```bash
python scripts/stoneart_products.py create-product \
  --file work/<slug>/draft.json \
  --image work/<slug>/images/product-01.jpg \
  --image work/<slug>/images/product-02.jpg \
  --cover-index 1 \
  --apply
```

For an explicit publish request:

```bash
python scripts/stoneart_products.py create-product \
  --file work/<slug>/draft.json \
  --image work/<slug>/images/product-01.jpg \
  --cover-index 1 \
  --publish \
  --apply
```

Before upload, the CLI:

1. Compresses images larger than `PRODUCT_IMAGE_MAX_BYTES`.
2. Sends only the selected hero image to Aliyun Wan2.7.
3. Removes watermarks/overlay text and replaces the full background using `PRODUCT_COVER_AI_PROMPT`.
4. Restores the generated image to the source dimensions.
5. Compresses the generated image if needed.
6. Adds the configured watermark to every final upload image when enabled.
7. Recompresses a watermarked image if it exceeds the upload limit.
8. Uploads the AI cover first, followed by the remaining original images.

For four supplied images, the final gallery has four images:

```text
1. AI-processed hero cover
2. Original image 2
3. Original image 3
4. Original image 4
```

The original hero is not added as a fifth item. Inspect the generated cover with `view_image` before saving. Reject it if the sculpture changes shape, gains or loses major details, contains added people/text/logos, or looks physically implausible.

Use `--no-ai-cover` only when the user explicitly wants to skip Wan2.7.

### 6.1 Watermark final upload images

Use `--watermark` when the user asks for a brand watermark on the final images. When `PRODUCT_WATERMARK_ENABLED=true`, watermarking is automatic; use `--no-watermark` for a one-off exception.

The bundled script uses a transparent multicolor gradient, a subtle shadow, a random rotation, and a random quiet edge position. Portrait images choose only from the top-left or top-right edge zones so the mark remains inside the product page's top-cropped `4 / 3` gallery frame. It writes new files under `work/processed/watermarked/` and never modifies the source photos.

Preview the look before a production upload:

```bash
python scripts/add_watermark.py \
  --image work/<slug>/images/product-01.jpg \
  --output-dir work/<slug>/images/watermarked
```

Inspect the preview with `view_image`. Adjust `PRODUCT_WATERMARK_TEXT`, `PRODUCT_WATERMARK_OPACITY`, `PRODUCT_WATERMARK_WIDTH_RATIO`, `PRODUCT_WATERMARK_COLORS`, or `PRODUCT_WATERMARK_POSITION` if the text obscures the sculpture, becomes hard to read, or is clipped by the gallery crop. Keep the watermark away from faces and carved details; use the top corners on full-height statues.

Standalone image tools:

```bash
python scripts/stoneart_products.py edit-product-cover \
  --image work/<slug>/images/product-01.jpg \
  --output work/<slug>/images/ai-cover.jpg

python scripts/stoneart_products.py prepare-image \
  --image work/<slug>/images/detail.jpg
```

### 7. Verify the saved product

```bash
python scripts/stoneart_products.py verify-product --id <product-id>
```

Verify title, slug, status, category IDs, cover image, gallery, SEO fields, and public HTTP status. Fetch the saved product again before reporting success.

## Existing Product Updates

Fetch and back up the current product first:

```bash
python scripts/stoneart_products.py get-product \
  --id <product-id> \
  --output work/<slug>/before.json
```

Create a patch JSON containing only the fields to change:

```bash
python scripts/stoneart_products.py update-product \
  --id <product-id> \
  --file work/<slug>/patch.json
```

The command displays a dry-run diff. Add `--apply` after reviewing it. Use `--replace-gallery` only when the new images should replace the existing gallery.

## Publishing

Publish an existing draft only when the user explicitly asks:

```bash
python scripts/stoneart_products.py publish-product --id <product-id>
python scripts/stoneart_products.py publish-product --id <product-id> --apply
```

Publication validation requires a title, slug, enabled category, and cover image. Missing optional facts do not block publication, but the page must not claim them.

## Content Rules

- Write public copy in English unless the user requests another language.
- Describe what is visible and what Stone Art can actually customize.
- Keep product titles descriptive, specific, and free of unsupported superlatives.
- Prefer 4-6 useful H2 sections over a wall of generic copy.
- Explain material, finish, placement, customization, packing, and ordering in buyer language.
- Do not invent prices, dimensions, SKU numbers, production times, customer stories, certifications, or material grades.
- Use `Contact for quotation` only when the user accepts a quote-based price.
- Add internal links when they help the buyer compare categories, materials, projects, or services.
- Use descriptive image alt text rather than keyword lists.

## Image Rules

- AI-process the selected cover for every new product unless the user explicitly disables it.
- The cover prompt removes watermarks and overlay text and replaces the entire outdoor background.
- Preserve the sculpture subject, proportions, material appearance, pose, and visible details.
- Keep the generated cover as gallery image 1.
- Keep the other supplied images in the gallery in their reviewed order.
- Use final gallery images in the body with `{{product_image:N}}` placeholders when they clarify a detail.
- Warn the user before publishing a visibly watermarked non-cover image.
- Apply the configured watermark only to final upload copies, never to the user's original files.
- Keep the mark translucent and low-impact; it must not obscure the sculpture's face, hands, or defining ornament.
- Use the bundled `assets/fonts/GreatVibes-Regular.ttf` or another font with a redistributable license.
- Do not infer exact scale from a photo without a reference object. Convert visual guesses into customization language, not fake measurements.
- Statue nudity can be legitimate classical art; still report explicit or unrelated sensitive content.

## Image Compression

- Check every local image before upload.
- If a file is at or below `PRODUCT_IMAGE_MAX_BYTES`, upload it unchanged.
- If it is larger, preserve its dimensions when possible and use progressive JPEG quality reduction.
- Downscale only when size-only compression cannot reach the limit.
- Write compressed copies under `work/processed/` and never overwrite the user's source files.
- The AI-generated cover is also compressed when necessary.
- Watermarked copies are written under `work/processed/watermarked/` and compressed again only when needed.

## Category Selection

Use the live category tree rather than guessing IDs. Examples:

- Marble Virgin Mary statue: `virgin-mary-statues` or the correct descendant under `religious-statues`.
- Bronze heron fountain: `bronze-water-fountains` or `animal-fountains`, depending on the product's primary selling point.
- Marble planter: `marble-flower-pots`.
- Bronze bust: `bronze-busts`.

When two categories are plausible, choose the one that best matches the search intent and product type. Use the other only as a secondary category when that is already the site convention.

## Duplicate and Reuse Rules

- Block an exact duplicate slug or exact duplicate product title.
- Near-similar products are allowed because sculpture suppliers often offer size and finish variants.
- Make the title and first paragraph identify the real differences: subject, material, composition, finish, or use.
- Media upload deduplication is not a license to reuse an image across unrelated products. Check `media-references` when the API reports deduplication.

## Feishu Notifications

The CLI sends signed Feishu cards after successful product creation, updates, and publication. Configuration:

- `FEISHU_PRODUCT_NOTIFY_ENABLED`
- `FEISHU_PRODUCT_WEBHOOK_URL`
- `FEISHU_PRODUCT_WEBHOOK_SECRET`
- `FEISHU_TIMEZONE`

Test without changing products:

```bash
python scripts/stoneart_products.py test-feishu
```

A notification failure must not roll back a successful product save. Report notification status separately.

## Safety

- Treat the live site as production.
- Preview before applying.
- Never delete a product or media asset unless the user explicitly requests deletion and the record has no references.
- Never overwrite an existing product without backing it up.
- Do not publish placeholder copy, empty categories, or a product with no usable cover image.
