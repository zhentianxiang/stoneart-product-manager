# Product Editor and Google SEO Guide

## Contents

1. Product-page structure
2. Title strategy
3. SEO fields
4. Body structure
5. Factual discipline
6. Category selection
7. Image alt text
8. Final checklist

## 1. Product-Page Structure

The CMS renders `title` as the page H1. The body must never contain another H1.

Use:

- H2 for major sections.
- H3 only for questions or details nested under an H2.
- Short paragraphs and scannable lists.
- A comparison or specification table only when real facts exist.
- Internal links to genuinely related categories, products, projects, or services.

Recommended body sections:

1. Product overview
2. Design and visible details
3. Material and craftsmanship
4. Placement and applications
5. Customization and ordering
6. Packing and delivery
7. Frequently Asked Questions, with at least three genuinely useful H3 questions

Do not force a section when the image or facts do not support it. Every complete
product body must still include a factual FAQ and an inline detail image when at
least two product images are available.

## 2. Title Strategy

Write a descriptive product title in English. Include the most important entity, material or finish, product type, and use when visible.

Good patterns:

- `Outdoor Bronze Double Heron Sculpture for Garden Water Feature`
- `Hand-Carved White Marble Virgin Mary Statue for Church`
- `Antique Bronze Lion Head Planter for Estate Garden`
- `Large Marble Tiered Fountain with Classical Figures`

Avoid:

- `Best Beautiful Amazing Sculpture`
- `Hot Sale Factory Direct High Quality Custom Statue`
- Exact competitor titles
- Values that are not visible or verified
- Repeating the same keyword more than twice

Titles should usually be 45-75 characters. Product variants may have similar titles, but the subject, material, finish, composition, or intended use must distinguish them.

## 3. SEO Fields

### SEO title

Target approximately 50-60 characters. Make it useful to a buyer, not a comma-stuffed keyword string.

Example:

`Bronze Double Heron Sculpture for Garden Water Feature`

### Meta description

Target approximately 140-160 characters. State what the product is, its material or finish when supportable, where it can be used, and that customization is available.

Example:

`Create a refined garden focal point with a hand-finished bronze double heron sculpture. Custom size, finish, and landscape project support available.`

### Excerpt

Target 120-220 characters. It appears near the gallery and may be used in cards and search results. Do not duplicate the first body paragraph word for word.

### Chinese product name

`name_zh` is a separate Simplified Chinese product name used by the website's Chinese search. It does not replace the English `title`.

Write a concise, natural catalog name that preserves:

- Subject and sculpture type
- Material or finish when stated
- Intended use or setting when stated
- SKU or product code when the English title includes one

Good:

- `白色大理石天使墓碑`
- `花园用青铜双鹭雕塑`
- `古典大理石层叠喷泉`

Avoid:

- Full-sentence marketing copy
- Pinyin instead of Chinese
- Facts not present in the English title or verified product data
- Changing a supplied SKU or product code

If the English title changes materially, re-check `name_zh` for accuracy. Preserve a manually edited Chinese name unless the edit makes it inconsistent with the new title.

### Specification fields

Keep the structured specifications separate so the product page can render them consistently:

- `size`: dimensions only, with units and axis labels such as `H 120 × W 60 × L 80 cm`.
- `material`: the supplied material or finish, such as `Grade A white marble`.
- `weight`: the supplied weight with units, such as `Approx. 500 kg`.
- `price`: the supplied price and currency, such as `USD 1,650`.

Do not append weight to `size`. If weight is unknown, leave `weight` empty and do not estimate it from a photograph.

## 4. Body Structure

### Opening paragraph

Answer what the product is and where it is used within the first 2-3 sentences. Mention only visible or verified details.

### In-body product images

The product gallery is managed separately from the article body. For a complete
product page with at least two images, include image 2 on its own line after the
most relevant design, detail, material, or craftsmanship section. It should support
that section rather than interrupt the opening paragraph.

Use placeholders rather than inventing media URLs:

```text
{{product_image:1}}
{{product_image:2}}
```

Place each placeholder on its own line or between paragraphs. Do not insert it inside an existing `<figure>` or Markdown image, because the command expands it into a complete figure.

Final gallery order is:

1. AI-processed cover
2. Remaining original images in reviewed order

The create and update commands replace each placeholder with the final uploaded image URL. For updates, confirm the numbering against the gallery that results from the merge or `--replace-gallery` operation.

If the generated draft omits this image, the CLI inserts `{{product_image:2}}` near
the end of the first relevant H2 section. It never duplicates an existing body image.

### Design and visible details

Describe pose, composition, facial expression, feathers, drapery, foliage, base, silhouette, and other concrete details visible in the supplied images.

### Material and craftsmanship

Use a specific material only when it is known or visually supported:

- Natural marble
- Cast bronze
- Stainless steel
- Limestone
- Wrought iron

If material cannot be confirmed, write `material can be confirmed for the project` rather than asserting a specific stone or alloy.

Describe general Stone Art capabilities only when relevant:

- Hand carving
- Lost-wax bronze casting
- Patina and surface finishing
- Custom dimensions and composition
- Structural and installation coordination

### Placement and applications

Use concrete settings supported by the image:

- Villa garden
- Church or memorial garden
- Hotel entrance
- Public park
- Landscape project
- Interior collection
- Water feature

### Customization and ordering

Explain what can be customized without inventing lead times or prices:

- Size and proportions
- Material selection
- Finish and patina
- Base design
- Project drawings
- Freight planning

### Packing and delivery

Describe known workshop practice conservatively: protective packing, reinforced crates, and export shipping coordination. Do not invent delivery days or guarantees.

### Frequently Asked Questions

End every complete product body with one `## Frequently Asked Questions` section.
Use at least three H3 questions. The default set should cover customization,
confirmation of dimensions/weight/delivery details, and how to request a quote.
Do not state unknown specifications, prices, or lead times. If the model omits the
section, the CLI appends this safe, factual default FAQ automatically.

## 5. Factual Discipline

Never invent:

- Price or discount
- Exact dimensions or weight
- SKU or item number
- Production lead time
- Material grade
- Certifications
- Customer names, reviews, or project locations
- Delivery guarantees

If the user provides facts, preserve them exactly. If the image only suggests them, use language that communicates customization rather than certainty.

For missing facts, the draft may include a private field:

```json
{
  "missing_information": [
    "Exact dimensions",
    "SKU",
    "Selling price"
  ],
  "claims_to_verify": [
    "Bronze alloy composition"
  ]
}
```

These private fields are stripped before the product is saved.

## 6. Category Selection

Use enabled leaf categories from the live category tree.

Examples:

- Marble Virgin Mary statue: `virgin-mary-statues`
- Jesus statue: `jesus-statues`
- Bronze animal: `bronze-animal-sculptures` plus the specific animal child when relevant
- Marble fountain: `marble-fountains` or a more specific fountain child
- Marble flower pot: `marble-flower-pots`
- Marble bust: `marble-busts`
- Marble bench: `marble-benches`
- Stone fireplace: `stone-fireplaces`
- Bronze flower pot: `bronze-flower-pot`

If an image could fit multiple categories, choose the category that best represents the buyer's main search intent. Add a second category only when it is objectively useful and the site already lists similar products that way.

The CMS stores categories as numeric database IDs. Drafts may use `category_slugs` or `category_paths`, but the CLI must resolve them against the latest category API before saving.

## 6.1 SKU Numbering

Do not use an invented SKU. The live catalogue contains several historical series such as `SAS-112xxx`, `SAS-215xx`, and other imported families. The currently active series is configured with:

```dotenv
PRODUCT_AUTO_SKU_SERIES=SAS-215
```

When the user has not supplied a SKU, use the next value from the configured active series. The CLI checks the latest products in that family and verifies exact uniqueness again before saving.

If the user provides an external SKU or item number, preserve it exactly and do not replace it with the automatic value.

## 7. Image Alt Text

Describe the image, not the sales pitch.

Good:

- `Outdoor bronze double heron sculpture with a reeded base`
- `White marble Virgin Mary statue in a church garden`
- `Hand-carved marble planter with acanthus relief`

Avoid:

- `best bronze sculpture factory supplier`
- `marble statue marble sculpture garden statue`
- Repeating the exact title on every gallery image

For multiple angles, distinguish front view, side detail, base, finish, and installation context.

The AI-processed cover alt text should describe the sculpture in its new environment. Do not claim a specific real location unless the user supplied one.

## 8. Final Checklist

- Title identifies the product without unsupported claims.
- Slug is unique and descriptive.
- Any changed published slug has a verified permanent redirect from the old URL.
- Excerpt is buyer-useful and not keyword-stuffed.
- Body has no H1.
- H2 and H3 hierarchy is logical.
- A complete FAQ section contains at least three useful H3 questions.
- Multi-image products include a detail image in a relevant body section.
- Facts match the user's input and visible evidence.
- Category IDs are valid and enabled.
- Cover image is the strongest clear view.
- Gallery order tells a coherent product story.
- Alt text describes each visible image.
- SEO title and meta description are concise.
- `name_zh` exists, is natural Simplified Chinese, and matches the English product title.
- `weight` is stored in its own field when known and is not mixed into `size`.
- Status matches the user's explicit request.
