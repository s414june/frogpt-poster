# vNext implementation and validation

Base: `main` commit `ff49ae9`. Work branch: `refactor/poster-vnext`.
No main push, remote branch push, deployment or MCP connection update performed.

## Implementation

- `composition.py`: BackgroundResolver, SubjectResolver, DesignResolver,
  TypographyResolver, PosterRequestResolver, PosterSpec, PosterRenderer.
  The resolved spec drives the existing renderer adapter. No new image engine.
- `openai_tool.py`: independent asset resolution before render, missing-subject
  transition, independent reference/design handling, optional geometry,
  normalized status alias, separate-layer preview/hash approval.
- `mcp_http.py`: automatic completion default; explicit preview/intake options;
  fileParams retained, background/reference attachment role preserved;
  schema additions, server version 0.4.0, compact normalized output.
- `types.py`, `client.py`, `image_pipeline.py`: resolved composition mode,
  exact resolved background colors, contain-fit foreground and alpha,
  optional visual-only preview using the same renderer.
- `blob_storage.py`, `blob_workflow.py`: new GPT source provenance in asset refs;
  old refs still parse. Subject refs retain known source without duplicate upload.
- `workflow.py`, `README.md`: replace conflicting mandatory multi-stage directions.
- Tests changed in `test_blob_storage`, `test_design_library`,
  `test_design_reference`, `test_geometry`, `test_layout_grid`,
  `test_mcp_output_order`, `test_openai_tool`, `test_staged_workflow`;
  added `test_composition.py`.

Removed the forced first questionnaire, default typography approval gate,
autopilot background path chooser, default random decoration and the no-image
background-generation branch. Preserved explicit draft review, byte validation,
host restrictions, public-upload controls, Blob TTL/rate limits and attribution.

## Automated validation

Command: `PYTHONPATH=src python -m unittest discover -s tests`.
Final full-suite rerun: 175 tests passed in 14.883 seconds (2026-10-20).

`tests/test_composition.py` validates A–F with deterministic image fixtures
standing in for AI-generated and uploaded images. Each case actually renders,
decodes and checks a PNG at 480×640, foreground visibility and geometry use.
Stock and built-in design catalog metadata use local fixtures; this does not
exercise a live image-generation model or the remote Pexels service.

| Case | Background | Subject provenance | Design | Geometry |
| --- | --- | --- | --- | --- |
| A | Solid | AI | Automatic | None |
| B | Saved Pexels fixture | AI | Automatic | Omitted by automatic choice |
| C | User fixture | User fixture | Automatic | None |
| D | Gradient | AI | User description | Omitted by automatic choice |
| E | Saved Pexels fixture | User fixture | Built-in catalog fixture | Explicit |
| F | Solid | AI | Automatic | Explicitly disabled despite supplied geometry |

Additional checks: no-subject transition, background-only rejection,
subject-position pixels/bounds, independent typography colors without reference,
formal attachment dispatch with mocked host download and real rendering,
background role annotation, visual preview hash approval, AI-disabled upload
requirement, user background priority, Blob provenance and no duplicate upload.

Existing suites cover attachment URL/redirect restrictions, image validation,
fonts, grid/overflow, geometry order, Blob URL responses, TTL, cleanup and errors.
Blob integration uses an in-memory backend; it is not a live Blob credential test.

`PYTHONPATH=src python scripts/verify_blob_manifest.py`: passed. Confirms checked-in
manifest flags and URLs, not live network availability. `git diff --check`: passed.
No dependency or Function added; existing Vercel/static exclusion rules unchanged.
Actual Vercel Function bundle size was not measured.

## Compatibility and live UAT

`prepare_poster`, formal attachments, asset_refs and legacy Base64/draft fields
remain. `status` stays an object for clients reading `status.code`; additive
`poster_status` normalizes the five vNext statuses. Legacy complete draft/image
inputs remain integrated visuals and are labeled `legacy_draft`; independent
background inputs never fulfill the subject requirement. `ready_to_render` is
an internal boundary followed immediately by rendering.

New immutable GPT asset refs include `-gpt` before the role; old refs remain valid
but cannot recover provenance that was never stored. Caller can explicitly retain
known `subject_source` on those old refs. No storage content migration required.

After an approved deployment, refresh MCP metadata and use a new conversation.
Verify tools/list includes the new options and all five fileParams. Then test
real conversation-mode attachment → host review → Vercel download → Blob → PNG
URL. This full host/platform path cannot be proven by local dispatch or mocks and
has not been claimed as passed. Live font/Blob URL availability and deployed
bundle size also remain deployment checks. No production state was changed.
