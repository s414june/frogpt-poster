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
