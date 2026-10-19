# Fonts drop folder

Put your downloaded open-source font files here:
- `.ttf`
- `.otf`
- `.ttc`
- `.woff2`

When `open_source_font_paths` is empty, the tool auto-discovers fonts from this folder (`assets\fonts`) recursively.

## Batch download from Google Fonts

You can auto-download a CJK-first set from Google Fonts:

```bash
python scripts\download_google_fonts.py
```

Options:
- `--cjk-limit-per-lang` (default: `5`)
- `--en-limit` (default: `5`)
- `--max-files-per-family` (default: `2`)
- `--dry-run` (preview only)

## Deduplication policy

Keep one canonical family directory and retain distinct static weights/styles. Duplicate root Noto Sans files and variable versions of families that already have static fonts have been removed. Keep standalone Japanese, Korean, Simplified Chinese and Hong Kong families because their localized glyph designs differ. Current font families support Chinese/Japanese/Korean/English; no unrelated-language-only family was present. Multilingual glyph coverage inside an otherwise supported font is not a reason to remove it. Runtime deployment continues to use the exact allowlist in `.vercelignore`, not every development font.
