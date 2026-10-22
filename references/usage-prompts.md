# Usage Guide and Ready-to-Copy Prompts

## Contents

1. When to show this guide
2. New product from one image
3. New product from multiple images
4. Draft-only intake
5. Missing specifications
6. Update an existing product
7. Batch product intake
8. Short everyday prompts

## 1. When to Show This Guide

Show this guide when the user asks:

- `这个 skill 怎么用？`
- `给我几个上架产品的提示词`
- `我发图片给你，你怎么操作？`
- Invokes the skill without a concrete image or product.

Keep the menu short and ask which workflow to start. Do not touch the production API.

## 2. New Product from One Image

```text
使用 $stoneart-product-manager，把这张图片里的产品上架到公司产品。

要求：
- 先用当前 Codex 对话的识图能力分析图片；只有 Codex 无法可靠识图时才调用本地 Qwen3-VL，最后才回退 DeepSeek
- 识别产品主体、可见材质、风格、细节、使用场景和图片中有没有水印
- 查询现有产品分类并选择最准确的叶子分类
- 如果 SKU 为空，就按当前有效系列自动取下一个编号
- 查询相近产品，避免标题和链接完全重复
- 写英文产品标题、摘要、正文、SEO 标题和 meta description
- 正文不要 H1，只使用 H2/H3
- 尺寸、价格、SKU、材质等级不确定就不要编造
- 先给我完整 dry-run 和图片顺序
- 我确认后再上传图片并发布
```

## 3. New Product from Multiple Images

```text
使用 $stoneart-product-manager，根据这组图片创建一个公司产品。

请把这些图片当作同一产品的一组素材：
- 自动判断主图、侧面图、细节图、底座图、场景图
- 把最有代表性、主体最清楚的正面图片作为封面
- 只把这张封面图交给本地 Qwen-Image-2.1（失败再回退阿里云百炼），移除水印/覆盖文字并完全替换户外背景
- 其余图片保留原图；大于 1MB 的图片自动高质量压缩
- 最终图库顺序是：AI 效果图封面 + 其余原图
- 例如我发 4 张，最终图库必须还是 4 张，不是 5 张
- 为每张图写准确的英文 alt
- 识别图片之间是否有重复视角
- 如果有水印、电话、网址、供应商 Logo，先指出位置，不要直接当最终上架图
- 根据真实可见内容写产品文案，不要靠图片猜尺寸和价格
- 产品正文需要插图时使用 {{product_image:1}}、{{product_image:2}} 等占位符；新建和更新产品都会在上传后替换为正式图片地址
- 选择正确分类，先 dry-run，不要写线上
```

## 4. Draft-Only Intake

```text
使用 $stoneart-product-manager，根据这张图片创建产品草稿，不要发布。

完成后返回：
1. 产品标题和 slug
2. 分类路径
3. 规格字段中哪些已确认、哪些为空
4. 产品正文和 SEO 字段
5. 图片上传与 gallery 顺序
6. 后台产品 ID
```

## 5. Missing Specifications

```text
使用 $stoneart-product-manager 处理这张产品图。

我只知道图片内容，没有准确尺寸、重量、SKU 和价格。请不要编造。
把未知项留空，并在正文中使用“custom size available”“contact for quotation”
这类真实可支持的表达。如果发布前必须补充事实，列出来让我确认。
```

## 6. Update an Existing Product

```text
使用 $stoneart-product-manager 更新这个产品：
<产品 URL、slug 或产品 ID>

先读取当前产品并备份。根据我补充的图片和说明：
- 只修改我明确要求的字段
- 保留没有提到的正文和 SEO 内容
- 如果增加图片，判断应该追加还是替换 gallery
- 如果修改已发布产品的 slug，记录旧 URL，并在部署后验证旧地址永久 301 到新地址
- 更新站内仍指向旧产品 URL 的内部链接
- 先显示字段 diff 和图片顺序
- 等我确认后再 --apply
```

## 7. Batch Product Intake

```text
使用 $stoneart-product-manager 处理这批产品图片。

先把图片按产品分组，不要一条命令直接全部发布。
每个产品输出：
- 建议标题和 slug
- 分类路径
- 可见事实
- 未知规格
- 水印情况
- 图片顺序
- 是否疑似与现有产品重复

全部先 dry-run。等我看完分组后，再按产品逐条创建或发布。
```

## 8. Short Everyday Prompts

```text
使用 $stoneart-product-manager，把这个产品图上架，先预览。
```

```text
使用 $stoneart-product-manager，根据图片写一个产品草稿，不要发布。
```

```text
使用 $stoneart-product-manager，看看这个产品和网站现有产品有没有重复。
```

```text
使用 $stoneart-product-manager，告诉我这个 skill 怎么用，先不要操作线上。
```
