# Product Image Analysis

## Contents

1. Priority order
2. What Codex should record
3. Observation JSON schema
4. Multi-image sets
5. Watermarks and sensitive content
6. DeepSeek fallback

## 1. Priority Order

Use Codex's own image capability first. It can reason across product context, compare similar products, detect image order, and write the final product draft in one coherent workflow.

Use DeepSeek vision only when:

- Codex cannot access the image.
- The image is too ambiguous for a confident first pass.
- A second structured observation would materially reduce uncertainty.

## 2. What Codex Should Record

For each image, record only what is supportable:

- Main subject
- Product type
- Material cues
- Color and finish
- Style or period
- Pose, composition, and base
- Visible texture and ornament
- Intended setting
- Buyer use cases
- Whether it is a hero, detail, side, scale, installation, packing, or workshop image
- Visible watermark or supplier marker
- Privacy or sensitive-content risk
- Concrete alt text

Separate observation from inference:

- `visible_facts`: directly visible.
- `reasonable_inferences`: likely but not certain.
- `unknowns`: facts needed before publishing.

## 3. Observation JSON Schema

Save to `work/<slug>/observation.json`:

```json
{
  "product_subject": "double heron garden sculpture",
  "product_type": "bronze sculpture and water feature",
  "images": [
    {
      "path": "/absolute/path/product-01.jpg",
      "role": "hero",
      "visible_facts": {
        "subject": "two standing herons",
        "material_cue": "dark bronze with gilded legs",
        "pose": "one upright, one bending toward a water element",
        "base": "naturalistic aquatic plants and reeds",
        "setting": "outdoor garden"
      },
      "reasonable_inferences": {
        "style": "naturalistic",
        "buyer_use": "garden or landscape water feature"
      },
      "watermark": {
        "present": false,
        "notes": ""
      },
      "sensitive_content": {
        "present": false,
        "notes": ""
      },
      "alt_text": "Outdoor bronze double heron sculpture with gilded legs"
    }
  ],
  "requested_facts": {
    "sku": "",
    "size": "",
    "material": "",
    "price": ""
  },
  "unknowns": [
    "Exact dimensions",
    "Bronze alloy composition",
    "Production lead time"
  ],
  "user_brief": ""
}
```

The `requested_facts` object must contain only facts the user supplied. Do not move visually guessed values into it.

## 4. Multi-Image Sets

Order images intentionally:

1. Strongest clear hero view
2. Alternate angle
3. Material or carving detail
4. Base or finish detail
5. Installation context
6. Workshop or packing proof

Reject blurry duplicate angles unless they show a real difference. Do not use multiple near-identical images just to inflate the gallery.

Choose one source image as the front/hero cover. For a new product, this is the only image sent to Aliyun Wan2.7 for full background replacement. The final gallery is:

```text
AI-processed hero
+ every remaining original image
```

For example, four supplied photos produce four gallery items, not five. The original hero is replaced by the AI-generated cover in the gallery.

If an image should also appear inside the product body, use `{{product_image:1}}` through `{{product_image:N}}` in `body_markdown`. Numbering follows the final gallery order.

The skill automatically compresses files above `PRODUCT_IMAGE_MAX_BYTES`. Keep the source files unchanged and write compressed versions under `work/processed/`.

## 5. Watermarks and Sensitive Content

If a supplier watermark, price tag, URL, phone number, or product code is visible:

- Record its location and type.
- Do not treat the image as final product media without the user's approval.
- Prefer a clean original from the user.

Classical artistic nudity can be a legitimate sculpture subject. Still record minors, explicit sexual content, graphic violence, or unrelated private information. Do not send sensitive images to any external model without user authorization.

## 6. DeepSeek Fallback

```bash
python scripts/stoneart_products.py vision \
  --image work/<slug>/images/product-01.jpg \
  --output work/<slug>/vision.json
```

Review the fallback JSON. DeepSeek may misidentify material or scale; treat its material and dimension guesses as suggestions, not facts.
