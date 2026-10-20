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

## MCP AI 生圖兩階段流程（v0.3.0）

1. 完成需求確認後，AI 先生成一張**背景與主體整合、完全無文字**的海報設計圖。主體包圍框置中於 `(50%, 50%)`，寬、高各不得超過畫布寬、高的 50%；上下留白。
2. 測試預設 480×640。助理將圖片等比例縮小，以 JPEG quality 60–70 壓縮，base64 本體以 100,000 字元內為目標；不得截斷。實際圖片位元組編碼成 `data:image/jpeg;base64,...`，傳入 `generated_background_base64`，並確認 `generated_background_text_free_confirmed=true`。
3. 未確認排字時，工具回傳 `awaiting_typography_confirmation`、無字預覽及 `draft_image_sha256`，**不渲染文案**。助理顯示圖片並問「無字海報已準備好，是否準備好加上文案？」後停止，等待下一則明確同意。`intake_confirmed` 與「全部交給你」都不能代替此確認。
4. 收到同意後，傳回同一張圖、文案、`typography_confirmed=true`，以及 `approved_draft_sha256=<上一步 draft_image_sha256>`。未提供或圖片雜湊不同，仍回到無字預覽確認階段。確認狀態不依賴單一 serverless instance。
5. 文案只由套件字型排版，標題、副標、內文、CTA 共用一個顏色，以所有文字區域的最低對比度選擇深色或淺色。已確認的 AI 圖使用 `both/reference`，不另加幾何或重組主體。
6. 完成後以回傳 base64 解碼，驗證實際圖片並轉存 PNG，提供預覽與下載。若不是 base64，先取得 image content／附件／可讀取圖片資源的**實際圖片位元組**，再轉 base64、解碼並存 PNG。不能把 JSON、HTML、錯誤或路徑文字編碼冒充圖片；取不到圖片位元組時應明確回報。

此確認閘門由 `/mcp` 的 `prepare_poster` 執行；`/api/poster` 保留為低階直接渲染 API。

## Tool contract

Tool name: `generate_poster_with_real_image_priority`

Key arguments:
- `poster_text_file`: UTF-8 JSON input path
- `poster_request`: inline request object (recommended for web/mobile)
- `title`, `body`: optional overrides
- `subject`, `primary_color`, `secondary_color`, `accent_color`: visual style hints
- `background_mode`: `auto` | `solid` | `gradient` | `reference`
  - `auto` 預設偏向單色背景（不自動套漸層）；若要漸層請明確指定 `gradient`，或使用 GPT 自動設計模式讓系統判斷。
- `image_role_mode`: `auto` | `subject` | `background` | `both`
- `geometry_enabled`: `true/false` (solid/gradient + single subject 時預設會加幾何裝飾)
- `subject_mask_mode`: `rounded` | `feather`
- `subject_border_px`: `0` or `8..20` (僅使用者明確要求時加粗邊框)
- `background_color_hint`: 使用者想要的背景色提示詞（例如 `blue light`, `暖橘`, `深綠`）。也支援只有明度語意（如 `light`、`dark`）來調整背景亮暗。
- `creative_source_preference`: `auto` | `real_image_priority` | `gpt_generate`
  - `gpt_generate`：在未自訂設計參數時，交由 GPT 以**非隨機**規則自動判斷背景策略（Pexels / 單色 / 漸層 / 需先生成無字背景）。
- `intake_answers`: 可選；以 `{question_id: answer}` 回傳首輪問卷答案（例如 `creative_source_preference`、`image_ready`）。
- `user_image_base64`
- `subject_image_base64` (可疊加為前景主體，建議透明背景 PNG)
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

MCP 本機路徑模式（僅本機開發建議）：
- 預設已接受 `user_image_paths`、`subject_image_paths`、`reference_image_paths`（仍建議優先使用 base64 / asset_refs）。
- 若你要關閉本機路徑輸入，可設定：
  - `FROGPT_ALLOW_LOCAL_IMAGE_PATHS=false`
- 圖片 URL（`*_image_urls`）仍會被拒絕。

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
- MCP 在 intake 完成後，**預設不自動啟用變體**（避免隨機跳版）。
- 只有明確傳入 `regenerate_variant=true` 才會產生新變體，且會忽略傳入舊 `variation_token`。
- 若首輪問卷選擇「由 GPT 生成與自動判斷」，且未自訂設計參數，系統會啟用 GPT 自動設計模式（`design_autopilot.active=true`）。

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
- sans-serif (黑體) is prioritized; heading default weight is reduced one step (prefers medium/semibold over black/bold), body keeps one consistent font/weight.
- when no explicit palette is provided, colors are automatically extracted from user/GPT-provided images (subject/reference/background draft).
- when `background_color_hint` is provided, palette selection first tries to match that hue from image colors; if no close same hue exists, it still uses image colors and adjusts saturation/lightness toward the hint.
- all copy shares one dark/light text color, selected using minimum contrast across the text regions.
- subject image uses one mask style at a time (`rounded` or `feather`) and preserves original aspect ratio.
- border is optional and only applied when requested (`subject_border_px`, 8-20px).
- image-role handling: in `auto`, the tool first asks via intake then infers role from prompt keywords and image traits; `both` means direct text-on-image mode and disables geometry.
- in `image_role_mode=both`, text placement uses a small focus-avoid algorithm to move text blocks away from visual focal area; typography is constrained to two sizes (slogan large, all other copy smaller).
- for solid/gradient background with a single subject, geometric accents are added by default (unless `geometry_enabled=false`) and are distributed from subject-side or edge-side anchors (wider spread allowed, but not fully random scattering).
- geometric colors use one shared logic for all shapes: hue families are capped at 3, and default harmony stays close to background (hue-near and/or saturation-near). Contrast/complementary jump colors are only enabled when user prompt explicitly asks for it (e.g. 跳色/撞色/contrast).
- geometric motifs use a repeated two-tone system (same hue family: primary + lighter step) with consistent alpha and size ratios for stronger brand consistency.
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
- Pexels is **off by default** and controlled only by environment variables.
- Enable with `FROGPT_ENABLE_PEXELS=true` and set `PEXELS_API_KEY`.
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

## Blob static migration and build verification

- One-time migration tool (manual, not per-build):
  - `PYTHONPATH=src python scripts/migrate_blob_static.py --check-access`
  - `PYTHONPATH=src python scripts/migrate_blob_static.py --apply`
- Normal build verification:
  - `PYTHONPATH=src python scripts/verify_blob_manifest.py`

## HTTP API (Vercel-ready)

Files:
- `api\index.py` (Vercel Python serverless entrypoint)
- `requirements.txt`

Endpoints:
- `GET /api/health`
- `GET /api/tool`
- `POST /api/poster`
- `POST /mcp` (MCP JSON-RPC endpoint; also accepts `/api/mcp`)

MCP endpoint recommendation for GPT connector:
- Use `https://<your-domain>/mcp` as the tool URL (avoid using `.py` suffix path).
- Compatibility note: `GET /` now redirects to `/mcp`; `POST /` is still accepted as MCP fallback for clients that probe root first.

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

Path handling note:
- Chat sandbox paths like `/mnt/data/...` are often not readable by your deployed MCP runtime.
- MCP adapter enforces **base64-only** for user-facing calls through ChatGPT.
- URL/path image fields (`*_image_urls`, `*_image_paths`, `reference_image_urls`, `reference_image_paths`) are rejected with a friendly re-upload hint.

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
- MCP endpoint request body limit is **8 MB**. Since MCP is base64-only, compress/resize images before upload when needed.
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

## Explicit copy controls (v0.3.1)

MCP top-level arguments or `poster_request.style` accept `text_align` (`left` / `center` / `right`), `headline_source` (`title` / legacy `body_first`), and `body_y_ratio` (0–1, top of body block). Use `headline_source="title"` to keep explicit title newlines as the large heading. In `both` mode, `body_y_ratio=0.64` places subtitle/body nearer the vertical center; placement is clamped inside the canvas. All blocks retain one shared color.

## Line spacing

All multiline title and body blocks use a 1.5-em line advance: one font em plus a 0.5-em gap, calculated separately for each font size and rounded only to the nearest pixel. Block height estimation uses the same advance as drawing; 8px grid snapping does not alter line spacing.

## Attachment preflight and error reporting

Before rendering, the assistant must obtain and successfully decode the current attachment bytes. A missing local path is a pre-tool attachment failure: stop reusing it, reacquire the same attachment through an available platform mechanism, or stop with「附件讀取失敗，尚未傳入套件」and request reattachment. The remote MCP server cannot read or repair the chat host filesystem. Never encode a filename/path, invent base64, or regenerate the user photo as a replacement. Only known image ValidationErrors receive base64 recovery advice; runtime/renderer failures preserve their error status and diagnostics. Generic transport errors do not establish a server-side cause.

## Conversation-mode fallback

If the host cannot reacquire a missing attachment, stop before rendering and recommend「工作」instead of「對話」, with the original image reattached in the new work. For unknown tool/transport errors, allow at most one extra retry after a concrete input correction or successful byte recovery; unchanged failures stop immediately. Do not guarantee that switching modes fixes server errors. If already in Work, report the failure stage and retain diagnostics instead of looping on mode-switch advice. The MCP server cannot recreate chat-host files or automatically switch user modes.

## Font selection

Default `font_family=sans` uses Noto Sans TC (黑體). Set `font_family` at MCP/API top-level or in `poster_request.style` to `serif` (明體／宋體, Noto Serif TC), `kai` (楷體, LXGW WenKai TC), or `rounded` (圓體, Chiron GoRound TC). Chinese aliases are accepted. Explicit family choice filters font files before typography ranking. Unknown or undeployed families return a validation error rather than silently substituting sans. Direct API callers may supply validated server-local `assets.open_source_font_paths` for other deployed fonts when no family is selected. Runtime fonts retain their OFL licenses.

## Runtime font bundle budget

`.vercelignore` uses an exact file allowlist matching `font_registry.FONT_FAMILIES`: six font files (sans Regular/Medium, serif Regular/Medium, kai Regular, rounded Regular) and four OFL licenses. Variable-font duplicates, unused weights and duplicate SC families remain in the development repository but are excluded from deployment. Font files are loaded for rendering; the API still returns rendered image bytes as base64, not encoded font files.

Local ignore-rule audit: font resources fall from 170.45 MB to 74.67 MB (decimal). This is a measured source-font reduction, **not** a verified Vercel function bundle size. Dependencies and build-time packaging still contribute to the final deployment. `tests/test_font_bundle.py` checks that only registered fonts/licenses are included and that fonts remain below an 80 MB budget. Each family was also locally loaded through FreeType and rendered through the image-to-base64-to-PNG pipeline.


### 使用設計海報作為靈感

助理先檢視使用者的參考海報，設 `design_reference=true`，並以
`reference_style_description` 記錄配色、構圖、材質、光線與留白。
API 會回傳 `needs_background_generation`，由助理生成新的無字視覺。
API 本身不呼叫生圖模型。參考海報不會作為成品背景。

助理將新圖的實際 JPEG/PNG data URL 放入 `generated_background_base64`，
並設定 `generated_background_text_free_confirmed=true`，同時傳入 `text_layers`：

```json
[{"text":"秋日限定", "font_family":"serif", "font_size":42,
  "color":"#174C61", "x":32, "y":40, "width":416, "height":100,
  "align":"left", "line_spacing":8}]
```

所有位置、尺寸、字級與行距均為最終畫布像素；支援 sans、serif、kai、rounded。
文字換行由助理指定，超出文字框時回傳錯誤，不自動裁切或縮字。
此流程可同輪完成無字視覺與 API 排字；使用者要求先看草稿時，助理先展示再等候。
未啟用此模式時保留既有分階段確認流程。


參考風格模式不限制各層字級相同。GPT 優先從參考圖觀察字級層次、字重及行距，
再換算成畫布像素；無法辨認的屬性才使用既有預設。`font_weight` 可為 400、700
（黑體/明體真實字型），楷體與圓體目前僅 400。預設不傳時仍為 400。
參考圖預設可重新配色（保留撞色關係）並微調構圖；使用者明確指定忠實還原時才固定。


### 變體與文字網格

參考模式預設 `design_variant="reinterpret"`，多彩風格換主輔色（可從新主圖取色），
至少改兩項構圖決策；只有明確要求還原時使用 `faithful`。
這是助理看圖與生圖階段的指引，API 不會自動判斷兩張圖的視覺相似度或擷取主圖顏色。

`typography_grid` 在參考模式預設開啟，其餘流程不變。短邊約 1% 為網格單位，
12 欄與 2 單位 gutter 供構圖規劃；實際文字依真實字型墨跡對齊基本網格，
距邊緣至少 5% 短邊、區塊彼此及主體保護區至少 2 單位。
GPT 看新圖後以 `protected_regions=[{"x":0,"y":80,"width":530,"height":500}]`
傳入主體/照片區；未提供時回傳警告，不宣稱已檢查主體距離。
位置修正最多 8 單位，不自動縮字、改文案或重畫照片。無解則回傳錯誤請助理調整版面。
指定 `allow_overlap=true` 可允許該層疊字，但仍遵守邊界。

每層可設定 `group`，連續同組區塊的垂直間距超過 2 倍較大字級時提示過鬆，
不自動壓縮刻意留白。`letter_spacing` 支援 0–0.25 em 的像素值，保留字型原始 advance
與標點基線，不強制左右撐滿。結果 `layout_report` 回報網格、修正位置與警告。

### Explicit Pexels backgrounds

An explicit `pexels_query` or `auto_pexels_fallback=true` never silently switches
to AI generation. If configuration is incomplete, the tool returns
`pexels_unavailable` and `missing_configuration` (environment variable names only).
Enable `FROGPT_ENABLE_PEXELS=true` and configure `PEXELS_API_KEY` on the server.
Empty searches return `pexels_no_results` so the assistant can revise the query.
For a stock background plus a foreground product, pass `pexels_query`,
`background_mode="reference"`, `image_role_mode="background"`, and a transparent
PNG in `subject_image_base64`. The product is composited over the photo and
Pexels photographer attribution is retained.

### 已存 Pexels 圖庫（不使用 API）

`use_local_reference_library=true` 列出已存圖片 ID、作者和來源連結；
選定後傳 `reference_library_id="pexels-13392284"`。也支援放在 `poster_request`。
這條流程直接讀取 repo 的圖片與 manifest，不需要 API key、不呼叫網路，
也不會被 `FROGPT_ENABLE_PEXELS` 影響；同時傳入的線上搜尋參數會被忽略。
圖片作為背景，商品使用 `subject_image_base64` 疊在前景，保留作者/Pexels 署名。
Windows manifest 路徑會轉為跨平台路徑，以 repo 根目錄解析。
目前 manifest 中作者為 Unknown 的圖片暫不提供，待補齊真實作者後即可使用。
線上 API 搜尋則單獨使用 `pexels_query` 與伺服器環境設定。

## 設計稿參考庫與署名

設計稿放在 `assets/design-references/attributed/`（需署名）或
`assets/design-references/original/`（自己畫的免署名），並維護各自的
`manifest.json`。空資料夾已用 `.gitkeep` 保留。詳見該目錄 README。
`list_design_references=true` 取得最新目錄與縮圖，
`design_reference_ids` 指定實際參考的設計稿；不會把設計稿直接當背景。
必要署名與照片作者合併、去重為一排，不標示來源用途。
灰底半透明（alpha=150/255），貼齊右上邊緣，底框貼齊文字，不加 padding 或外距。

## GPT 幾何圖層與主體文字

`geometry_layers` 可放頂層或 `poster_request.style`，適用所有背景。
支援 `circle`、`rectangle`、`line`，位置尺寸為最終畫布像素，
設定 fill、stroke、opacity、stroke_width；圓形寬高必須相同。
圖層依順序疊加於照片之上、商品之下，最後渲染文字及署名。
`geometry_enabled=false` 停用；有精確圖層時不再額外隨機加裝飾。

```json
{"geometry_layers":[{"shape":"circle","x":80,"y":260,"width":180,"height":180,"fill":null,"stroke":"#000000","opacity":0.35,"stroke_width":3}]}
```

主標預設字級提高約 20%，副標略增；明確 text_layers 字級維持不變。
商品包裝品牌／標籤等非標語文字可用 AI 生成，允許自繪、曲面與透視字樣。
海報主標、副標及 CTA 仍使用工具字型。現有 text-free 確認欄位
指的是沒有額外海報文案，不排除主體原生文字。


### GPT 獨立幾何圖層（優先）
GPT 環境先自行畫透明 PNG，以頂層 `geometry_image_base64` 或
`poster_request.assets.geometry_image_base64` 傳入。PNG 必須含 alpha 並與最終畫布
同尺寸，保留透明邊界；不能把主體、背景或標語畫進此圖。
API 依背景 → 幾何 → 主體三個視覺圖層合成，最後排文案及引用。
不裁切、不改色、不額外生成裝飾；圖片優先於舊的 `geometry_layers`，
`geometry_enabled=false` 可停用兩者。舊形狀參數保留給非 GPT 或明確要求 API 繪製的流程。
純黑用 #000000，不從品牌色自動帶入綠色；已刪除形狀不可自動補回。
FrogToothpaste 本次調整規格見 `examples/frogtoothpaste-design.json`。
