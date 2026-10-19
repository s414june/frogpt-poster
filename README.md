# gpt-package

OpenAI Tools plugin for an anti-`AI-look` poster workflow:
- prefers user-provided real photos,
- uses AI image generation only as fallback,
- validates text-file input before running,
- renders and saves poster output (`.png`).

## Quick start

```bash
pip install -e .
```

## Tool contract

Tool name: `generate_poster_with_real_image_priority`

Key arguments:
- `poster_text_file`: UTF-8 JSON input path
- `poster_request`: inline request object (recommended for web/mobile)
- `title`, `body`: optional overrides
- `subject`, `primary_color`, `secondary_color`, `accent_color`: visual style hints
- `background_mode`: `auto` | `solid` | `gradient` | `reference`
- `image_role_mode`: `auto` | `subject` | `background` | `both`
- `geometry_enabled`: `true/false` (solid/gradient + single subject 時預設會加幾何裝飾)
- `subject_mask_mode`: `rounded` | `feather`
- `subject_border_px`: `0` or `8..20` (僅使用者明確要求時加粗邊框)
- `background_color_hint`: 使用者想要的背景色提示詞（例如 `blue light`, `暖橘`, `深綠`）。也支援只有明度語意（如 `light`、`dark`）來調整背景亮暗。
- `user_image_paths`, `user_image_urls`, `user_image_base64`
- `subject_image_paths`, `subject_image_urls`, `subject_image_base64` (可疊加為前景主體，建議透明背景 PNG)
- `reference_image_urls`: style reference images (URL)
- `reference_image_paths`: local reference images (e.g. downloaded library files)
- `reference_image_base64`: style reference images (base64)
- `generated_background_base64`: a GPT-generated background draft to use as top-priority reference
- `generated_background_text_free_confirmed`: set `true` only after confirming generated background has no text/logo/watermark
  - both fields are accepted at top-level arguments or inside `poster_request`
- `pexels_query`, `pexels_orientation`, `pexels_per_page`: fetch references from Pexels API
- `auto_pexels_fallback`: opt-in automatic Pexels query when no image/reference is provided (default: off)
- `use_reference_as_fallback`: if no user photo, allow reference image to be used directly
- `open_source_font_paths`
- `width`, `height`, `allow_ai_fallback`
- `request_intake_only` (只回前置提問，不渲染)
- `show_design_guide` (回傳簡易設計指南)
- `regenerate_variant`: `true` 時每次呼叫自動產生新的 `variation_token`，可在同文案下得到不同幾何圖案/對應色分布
- `intake_confirmed`（MCP 流程：第一次問卷完成後請設為 `true`）
- `intake_session_token`（MCP 會話記憶鍵；第一次回傳，後續重用可免手動維護 intake flag）

If `open_source_font_paths` is omitted/empty, the tool auto-discovers fonts under:
- `assets\fonts` (`.ttf`, `.otf`, `.ttc`)

Open-source font compliance:
- font files must be under `assets\fonts` to be accepted by validation.

## UAT quick run (local)

1. Prepare a JSON text file like `examples\uat\poster-input.json`.
2. Run:

```bash
python scripts\uat_run_tool.py --input examples\uat\tool-call.json
```

3. Expected:
- `ok: true` for valid payloads,
- `ok: false` with `ValidationError` for invalid payloads.
- `output_path` points to a generated poster image for successful calls.
- `output_image_base64` is included for browser/mobile clients.
- `status.code` returns `completed` or `failed`.
- `status.code` may return `needs_input` when request data is incomplete.
- `output_image_data_url` can be rendered directly in UI (`<img src=\"...\">`).
- `output_preview_markdown` is included for clients/GPT that can render Markdown image previews.
- `source_credit_overlay_applied` / `source_credit_overlay_text` indicate whether corner source attribution was stamped.
- `scripts\uat_run_tool.py` will also save a JPG preview to `outputs\uat-jpg\` when render succeeds.

MCP intake behavior (強制一次)：
- 第一次要求生成海報時，會先回傳問卷與 `intake_session_token`，不直接渲染。
- 後續呼叫請重用同一個 `intake_session_token`；帶完整 brief 後會自動記憶 intake 已完成。
- `intake_session_token` / `intake_confirmed` 可放在頂層 arguments，或放在 `poster_request` 內（兩者都會被接收）。
- 你仍可顯式傳 `intake_confirmed=true`，但不是必填。
- 首輪問卷會包含背景模式題：`auto / solid / gradient / reference`。
- 首輪問卷也會詢問圖片角色：`auto / subject / background / both`。
- MCP 在 intake 完成後，若未顯式提供 `variation_token`，會自動啟用變體模式（等同 `regenerate_variant=true`）以避免每次重跑完全相同。
- MCP 在 intake 完成後，若未顯式設定 `regenerate_variant`，預設會啟用變體模式並忽略傳入的舊 `variation_token`（避免重跑仍同圖）。

When first interaction enters intake mode, the tool returns:
- `intake_questions` (copy/image/style/prompt-oriented questions)
- optional `design_guide` (when `show_design_guide=true` or `request_intake_only=true`)

For cleaner copy control, prefer:
- `poster_request.copy.headline`
- `poster_request.copy.subtitle`
- `poster_request.copy.organization`
- `poster_request.copy.cta`

Typography/layout policy:
- no solid background box behind slogan/body text.
- title/subtitle are center-aligned and kept near visual center (not tied to subject edges), with larger default sizes.
- body/campaign copy is center-aligned in lower area.
- typography uses two sizes by default: headline + primary campaign line use major size; remaining detail line(s) use minor size.
- sans-serif (黑體) is prioritized; heading prefers heavier weight, body keeps one consistent font/weight.
- when no explicit palette is provided, colors are automatically extracted from user/GPT-provided images (subject/reference/background draft).
- when `background_color_hint` is provided, palette selection first tries to match that hue from image colors; if no close same hue exists, it still uses image colors and adjusts saturation/lightness toward the hint.
- text color is auto-switched between dark/light to keep luminance contrast against background.
- subject image uses one mask style at a time (`rounded` or `feather`) and preserves original aspect ratio.
- border is optional and only applied when requested (`subject_border_px`, 8-20px).
- image-role handling: in `auto`, the tool first asks via intake then infers role from prompt keywords and image traits; `both` means direct text-on-image mode and disables geometry.
- in `image_role_mode=both`, text placement uses a small focus-avoid algorithm to move text blocks away from visual focal area; typography is constrained to two sizes (slogan large, all other copy smaller).
- for solid/gradient background with a single subject, geometric accents are added by default (unless `geometry_enabled=false`) and are distributed from subject-side or edge-side anchors (wider spread allowed, but not fully random scattering).
- geometric colors use one shared logic for all shapes: hue families are capped at 3, and default harmony stays close to background (hue-near and/or saturation-near). Contrast/complementary jump colors are only enabled when user prompt explicitly asks for it (e.g. 跳色/撞色/contrast).
- geometric color still enforces a minimum color distance from background (avoid “too similar to notice”).
- ellipse/oval geometry is disabled; only perfect circles are used when circular motifs are rendered.

No-image flow:
- if no user image/reference is provided, tool returns `status.code = needs_background_generation` (regardless of `background_mode`, including `solid/gradient`)
- it includes `background_generation_prompt`; generate a **text-free** background first, then retry with `generated_background_base64`.
- retry must include `generated_background_text_free_confirmed=true`; otherwise tool keeps `needs_background_generation` to prevent accidental text-in-background output.
- prompt policy defaults to presentation style: mostly solid/soft-gradient background, minimal geometry, clear foreground subject.

Reference image citation flow (non-regenerated background):
- you can pass `reference_image_urls` (including Pexels photo page URLs) or `reference_image_paths`.
- when a reference image is used as fallback background, renderer stamps top-right credit label (e.g. `June Wu/Pexels`) using the same open-source font pipeline.
- if you also pass `subject_image_*`, system keeps reference as background and composites subject object in foreground.

## Pexels reference workflow (no repo image storage)

For legal and operational safety, use Pexels via official API:
- Set environment variable: `PEXELS_API_KEY`
- Provide `pexels_query` (and optional orientation/per_page)
- The tool downloads reference images to temp storage at runtime, then cleans them up.

Returned fields include:
- `source_credits` (Pexels photo page, photographer, source URL)
- `style_from_reference_applied` (palette extracted from reference)
- `reference_images_used` (reference image used directly as fallback or not)
- `auto_pexels_query_used` (only when `auto_pexels_fallback=true` and API key exists)

Recommended generation order:
1. Use user-provided real images if available (highest priority).
2. If no user image, pass a GPT-generated background draft via `generated_background_base64` to guide style.
3. If still no image input, use `pexels_query` as fallback reference source.
4. Keep `auto_pexels_fallback=false` during manual-library phase; turn it on later when API is available.
5. Always render text using open-source fonts from `assets\fonts` or explicit font paths.

## Pexels compliance notes

- Do **not** scrape Pexels pages for bulk extraction; use official API.
- Do **not** redistribute source image files on a standalone basis.
- Keep a prominent link to Pexels and credit photographer when possible.
- Review current Pexels License and Terms before production rollout:
  - https://www.pexels.com/license/
  - https://www.pexels.com/terms-of-service/

## UAT with text interface (chat-like)

Run:

```bash
python scripts\uat_text_ui.py
```

Then follow prompts in terminal (`file` mode or `manual` mode).
This is the fastest self-operated UAT flow without wiring a remote endpoint.

## About testing directly inside ChatGPT UI

To click-and-run this as a real ChatGPT Tool in ChatGPT, you still need:
- a hosted tool endpoint (HTTP) that calls this package,
- tool registration in your OpenAI app/tool configuration.

This repo now provides the tool schema + handler, local UAT scripts, and an HTTP wrapper for deployment.

## HTTP API (Vercel-ready)

Files:
- `api\index.py` (Vercel Python serverless entrypoint)
- `requirements.txt`

Endpoints:
- `GET /api/health`
- `GET /api/tool`
- `POST /api/poster`

Example request:

```bash
curl -X POST "http://127.0.0.1:8000/api/poster" ^
  -H "Content-Type: application/json" ^
  -d "{\"arguments\":{\"poster_text_file\":\"examples\\\\uat\\\\poster-input.json\"}}"
```

Web/mobile-style request (no local path):

```bash
curl -X POST "http://127.0.0.1:8000/api/poster" ^
  -H "Content-Type: application/json" ^
  -d "{\"arguments\":{\"poster_request\":{\"title\":\"Inline\",\"body\":\"No local path\",\"layout\":{\"width\":1080,\"height\":1350},\"allow_ai_fallback\":true,\"assets\":{\"open_source_font_paths\":[]}}}}"
```

Manual-library mode sample (GPT background reference, no auto Pexels):

```bash
python scripts\uat_run_tool.py --input examples\uat\tool-call-manual-library.json
```

Download the fixed Pexels set from page URLs into local library:

```bash
python scripts\download_pexels_reference_pages.py
```

Downloaded assets + manifest:
- `assets\reference-library\pexels\*.jpeg`
- `assets\reference-library\pexels\manifest.json`

Then test local reference reuse:

```bash
python scripts\uat_run_tool.py --input examples\uat\tool-call-pexels-library.json
```

Local run:

```bash
vercel dev
```

Deployment notes:
- MCP endpoint request body limit is **8 MB**. Prefer `subject_image_urls` / `user_image_urls`; only use base64 for smaller images.
- Keep serverless bundle slim via `.vercelignore`. This project excludes most `assets\fonts` and keeps lightweight runtime families.
- For Traditional Chinese rendering in deployment, keep `assets\fonts\Noto_Sans_TC\static\*.ttf` (or equivalent CJK sans static files) in bundle; otherwise text may degrade to tofu squares.
- If deploy still nears platform limits, remove extra local assets (docs/examples/test data/fonts) from runtime bundle.

## Font storage folder

Place your downloaded open-source fonts in:
- `assets\fonts`

They will be picked up automatically when `open_source_font_paths` is not provided.

Batch download (Google Fonts, CJK-first):

```bash
python scripts\download_google_fonts.py
```

## Render output directory

Generated posters are written to:
- local: `outputs\posters`
- Vercel: `/tmp/posters`

You can override with environment variable:
- `POSTER_OUTPUT_DIR`
