# Stone Art Product Manager

Codex skill for turning sculpture product photos into completed Stone Art Sculpture product listings.

## Features

- Inspect product images with Codex vision first
- Use local Qwen3-VL-30B-A3B-Instruct as the structured vision fallback
- Use DeepSeek vision only when both Codex and the local vision model are unavailable
- Identify product subject, material, style, and use
- Match the product to the live category tree
- Generate SEO-focused product copy without inventing facts
- Generate a structured draft with DeepSeek when helpful
- Select one hero image and replace its full background with local Qwen-Image-2.1, falling back to Aliyun Wan2.7 when the local service is unavailable
- Remove watermark and overlay text from the AI cover
- Keep the AI cover plus all remaining originals in a correctly sized gallery
- Use uploaded gallery images inside product body content
- Compress images above 1MB without overwriting the source files
- Add a translucent multicolor script watermark to final upload images
- Randomize watermark placement among quiet edge zones
- Upload cover and gallery images to the CMS media library
- Preview the exact product payload before writing
- Create product drafts or publish on explicit request
- Preserve existing body HTML during updates
- Back up products before changes
- Verify category, gallery, SEO, status, and public URL
- Send signed Feishu cards after product changes
- Trigger Local KB website sync after publishing or updating a published product
- Report Local KB license and connectivity failures without rolling back the product

## Install

Copy this folder into a Codex skill directory:

```text
~/.agents/skills/stoneart-product-manager/
```

Install dependencies:

```bash
python3 -m pip install -r requirements.txt
```

Create local configuration:

```bash
cp config.example.env config.local.env
chmod 600 config.local.env
```

Never commit `config.local.env`.

## Quick Start

Open a Codex conversation and send a product image with:

```text
使用 $stoneart-product-manager，把这张图片里的产品上架到公司产品。
先识别图片，选择正确分类并生成产品文案；有明确尺寸、价格或 SKU 就使用，
没有就不要编造。创建前先给我预览。
```

Read `SKILL.md` and `references/usage-prompts.md` for the full workflow.

## CLI

```bash
python scripts/stoneart_products.py --help
python scripts/stoneart_products.py check
python scripts/stoneart_products.py list-categories
python scripts/stoneart_products.py list-products --query "bronze heron"
python scripts/stoneart_products.py vision --image product.jpg
python scripts/stoneart_products.py draft-product \
  --observation work/example/observation.json \
  --output work/example/draft.json
python scripts/add_watermark.py \
  --image product.jpg \
  --output-dir work/example/watermarked
python scripts/stoneart_products.py sync-knowledge-base --preview
python scripts/stoneart_products.py sync-knowledge-base
```

## Security

- Credentials and API keys stay in `config.local.env`.
- New products are drafts unless publication is explicit.
- Product creation shows a dry-run before `--apply`.
- Existing products are backed up before updates.
- Product and media deletion is not implemented as an automatic workflow.
