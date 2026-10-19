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
- `user_image_paths`, `user_image_urls`, `user_image_base64`
- `open_source_font_paths`
- `width`, `height`, `allow_ai_fallback`
- `request_intake_only` (只回前置提問，不渲染)
- `show_design_guide` (回傳簡易設計指南)

If `open_source_font_paths` is omitted/empty, the tool auto-discovers fonts under:
- `assets\fonts` (`.ttf`, `.otf`, `.ttc`)

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

When first interaction lacks complete fields, the tool returns:
- `intake_questions` (copy/image/style/prompt-oriented questions)
- optional `design_guide` (when `show_design_guide=true` or `request_intake_only=true`)

For cleaner copy control, prefer:
- `poster_request.copy.headline`
- `poster_request.copy.subtitle`
- `poster_request.copy.organization`
- `poster_request.copy.cta`

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

Local run:

```bash
vercel dev
```

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
