# FroGPT Poster

Poster rendering on the existing Vercel Python / Pillow / Blob stack.

## vNext composition workflow

`prepare_poster` remains the MCP entry point. Every new composition has a
background, an independent foreground subject, and API-rendered typography.
Geometry is optional and defaults to absent.

1. GPT interprets the brief and copy. It chooses a background color/gradient or
   selects an ID from the saved Pexels catalog. A supplied background takes priority.
2. Missing foreground returns `needs_subject_generation` with a subject prompt.
   GPT generates the isolated subject and retries using the same brief and refs.
   The API never generates or substitutes a stock background for the subject.
3. GPT uses user inspiration, selected built-in designs, or its own design judgment.
   It can pass `subject_position` and independently styled `text_layers`; missing
   explicit layout uses the existing measured typography defaults.
4. Resolvers validate a `PosterSpec`; the renderer composites background → optional
   geometry → subject → typography, using existing Pillow/font code.
5. Deliver only when `rendered=true` and `poster_status=completed`.

Default is automatic completion. `intake_confirmed` is retained for compatibility,
not required and never an upload authorization. `request_intake_only=true` explicitly
requests the optional questionnaire. Only set `preview_only=true` when the user
asks to review the visual first. A preview returns a digest; approval requires
`typography_confirmed=true` and the same `approved_draft_sha256`. Reuse the full
original request/refs, with no changed visual inputs. Approval state is stateless.

## Inputs and compatibility

Prefer the MCP `openai/fileParams` attachment fields:

| Field | Meaning |
| --- | --- |
| `subject_image` | Foreground, original or AI-generated |
| `background_image` | Background only; never implies a subject |
| `reference_image` | Design inspiration only |
| `geometry_image` | Optional transparent PNG, final canvas size |
| `draft_image` | Legacy complete text-free visual, including background and subject |

Host file objects contain `download_url`, `file_id`, optional `mime_type`/`file_name`.
HTTPS platform hosts only, redirects rejected, bytes decoded server-side. A local
filesystem path is not an attachment. Local path inputs remain development-only;
production keeps its existing restriction. No alternate endpoint bypasses host review.

Existing actual-byte Base64 inputs remain supported: `subject_image_base64` (array),
`user_image_base64` (legacy array), `generated_background_base64` (legacy complete
visual), `reference_image_base64`, `geometry_image_base64`. Do not encode paths,
JSON or error text as images. `generated_background_text_free_confirmed=true` still
asserts no poster copy/watermark in a legacy complete draft; product labels are allowed.
Unqualified legacy `user_image` / `both` remains a complete visual for compatibility.
For a background-only Base64 input explicitly use `image_role_mode=background`.

`asset_refs` reuses Blob assets: `background`, `subjects` (array), `geometry`,
`references` (array), `draft`. Never upload both ref and image for the same role.
`store_poster_asset` is optional. New AI assets retain provenance in their immutable
ref path; legacy refs remain valid. Legacy refs without recorded provenance require
`subject_source=ai_generated` on retry if that source is known.

Additional design fields:

- `subject_source`: `user_upload` (default) or `ai_generated`.
- `subject_position`: `{x,y,width,height}` in final canvas pixels; contain-fit,
  original aspect ratio and alpha preserved, validated within canvas.
- `background_mode`: `solid`, `gradient`, `reference`, `auto` (solid fallback).
- `primary_color`, `secondary_color`, `accent_color`, `background_color_hint`.
- `design_reference`, `reference_style_description`, `design_reference_ids`.
- `design_variant`: `reinterpret` default, `faithful` only when requested.
- `geometry_enabled=false` overrides all geometry. Supplying no geometry is valid.
- `text_layers`: per-layer text, font family/weight/size, color, pixel box,
  alignment, line spacing, letter spacing. Independent sizes/colors are valid
  without a reference. Overflow fails explicitly; no silent clipping.
- `typography_grid`, `protected_regions`: existing grid/safe-margin validation.

Default fonts: `sans` (Noto Sans TC), `serif` (Noto Serif TC), `kai` (LXGW WenKai TC),
`rounded` (Chiron GoRound TC). Existing deployed fonts/OFL licenses, Blob font
provider and measured typography algorithms are retained. No new dependencies.

## Status contract

To preserve clients reading `status.code`, its object format remains unchanged.
The additive `poster_status` gives the normalized vNext status:

| Legacy `status.code` | `poster_status` |
| --- | --- |
| `needs_subject_generation` | `needs_subject_generation` |
| `needs_input`, preview approval, legacy text-free check, catalog selection | `needs_user_input` |
| `completed` | `completed` |
| `failed` | `failed` |
| storage/configuration diagnostics | `needs_user_input` with original diagnostic retained |

`ready_to_render` is an internal composition boundary; the normal call renders
immediately rather than imposing an additional round trip. Replies include
`rendered`, `next_action`, and on resolved compositions `composition` with
background/subject/design sources and `geometry_used`. Blob-completed replies
include `image_url`/`download_url`; local mode retains verified PNG Base64.

## Saved assets and credits

`use_local_reference_library=true` lists the saved Pexels manifest; GPT selects
`reference_library_id`. The API does not automatically pick a photo. Saved stock
uses existing local/Blob references and retains photographer credit. Online
`pexels_query` is an explicit legacy opt-in requiring `FROGPT_ENABLE_PEXELS=true`
and `PEXELS_API_KEY`; missing config is diagnosed, never silently replaced.

`list_design_references=true` lists design inspiration. `design_reference_ids`
selects entries in `assets/design-references/{attributed,original}`. Design images
never become background photos. Required designer and photo credits are merged
using the existing source attribution overlay.

## Transport and deployment

Endpoints remain `/mcp` (`/api/mcp` alias), `/api/poster`, `/api/tool`, `/api/health`.
The low-level API shares the same composition resolver after materialization;
MCP retains host attachment handling and upload review diagnostics.

Public Blob: source assets 24h, posters 72h. Anyone holding the URL can read it;
cleanup is periodic, not guaranteed immediate expiry. Production uploads still
require `FROGPT_BLOB_ENABLED=true` and `FROGPT_UPLOAD_ENABLED=true` plus existing
Blob credentials. Explicitly authorized uploads only; host rejections must not be
bypassed by curl, different endpoints or misleading annotations. Sensitive uploads
are not authorized by intake flags. Rate limits, image validation and TTL checks remain.

Install/test:

```bash
pip install -e .
PYTHONPATH=src python -m unittest discover -s tests
PYTHONPATH=src python scripts/verify_blob_manifest.py
```

Static migration remains manual:

```bash
PYTHONPATH=src python scripts/migrate_blob_static.py --check-access
PYTHONPATH=src python scripts/migrate_blob_static.py --apply
```

No new serverless function, bundled fonts or photos are introduced. Existing
`.vercelignore`/`vercel.json` exclusion and migration rules are retained.

After deployment, refresh/rescan the MCP connection and start a new conversation.
Verify `tools/list` contains `preview_only`, `subject_source`, `subject_position`
and the five `openai/fileParams` fields; a version label alone is insufficient.
Deployment does not invalidate the host's cached tool schema.

See `docs/vnext-validation.md` for scope, automated checks and remaining live UAT.
