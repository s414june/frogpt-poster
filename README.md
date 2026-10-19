# gpt-package

OpenAI Tools plugin scaffold for an anti-`AI-look` poster workflow:
- prefers user-provided real photos,
- uses AI image generation only as fallback,
- validates text-file input before running.

## Quick start

```bash
pip install -e .
```

## Tool contract

Tool name: `generate_poster_with_real_image_priority`

Key arguments:
- `poster_text_file`: UTF-8 JSON input path
- `title`, `body`: optional overrides
- `user_image_paths`, `open_source_font_paths`
- `width`, `height`, `allow_ai_fallback`

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
- `api\index.py` (Vercel FastAPI entrypoint)
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

Local run:

```bash
python -m uvicorn api.index:app --reload
```

## Font storage folder

Place your downloaded open-source fonts in:
- `assets\fonts`

They will be picked up automatically when `open_source_font_paths` is not provided.
