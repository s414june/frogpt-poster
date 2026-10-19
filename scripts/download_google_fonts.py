import argparse
import json
import os
import re
import urllib.request
from pathlib import Path

GOOGLE_FONTS_METADATA_URL = "https://fonts.google.com/metadata/fonts"
GOOGLE_FONTS_GITHUB_API = "https://api.github.com/repos/google/fonts/contents/{bucket}/{folder}"
GOOGLE_FONTS_GITHUB_TREE_API = "https://api.github.com/repos/google/fonts/git/trees/main?recursive=1"
DEFAULT_OUTPUT_DIR = Path("assets") / "fonts"

LANGUAGE_SUBSETS = {
    "zh": {"chinese-simplified", "chinese-traditional", "chinese-hongkong"},
    "ja": {"japanese"},
    "ko": {"korean"},
    "en": {"latin"},
}


def fetch_metadata() -> dict:
    with urllib.request.urlopen(GOOGLE_FONTS_METADATA_URL, timeout=30) as response:
        raw = response.read().decode("utf-8")
    # Endpoint starts with XSSI guard: )]}'
    clean = re.sub(r"^\)\]\}'\s*", "", raw)
    return json.loads(clean)


def slugify_family(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "-", name.strip()).strip("-").lower()


def folder_key(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "", name.strip()).lower()


def _github_headers() -> dict:
    headers = {"User-Agent": "poster-font-downloader"}
    token = os.getenv("GITHUB_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def select_families(metadata: dict, cjk_limit_per_lang: int, en_limit: int) -> list[dict]:
    families = metadata.get("familyMetadataList", [])
    families_sorted = sorted(
        families,
        key=lambda item: int(item.get("popularity", 10**9)),
    )

    selected: list[dict] = []
    used = set()

    # CJK first
    for lang in ("zh", "ja", "ko"):
        subsets = LANGUAGE_SUBSETS[lang]
        count = 0
        for family in families_sorted:
            family_name = family.get("family")
            if not family_name or family_name in used:
                continue
            if family.get("isOpenSource") is False:
                continue
            family_subsets = set(family.get("subsets", []))
            if family_subsets.intersection(subsets):
                selected.append(family)
                used.add(family_name)
                count += 1
                if count >= cjk_limit_per_lang:
                    break

    # Mainstream English fallback (by top popularity ordering in metadata list)
    en_subsets = LANGUAGE_SUBSETS["en"]
    en_count = 0
    for family in families_sorted:
        family_name = family.get("family")
        if not family_name or family_name in used:
            continue
        if family.get("isOpenSource") is False:
            continue
        family_subsets = set(family.get("subsets", []))
        primary_script = (family.get("primaryScript") or "").lower()
        if family_subsets.intersection(en_subsets) and primary_script in ("latn", ""):
            selected.append(family)
            used.add(family_name)
            en_count += 1
            if en_count >= en_limit:
                break

    return selected


def build_repo_font_index() -> dict[str, list[dict]]:
    req = urllib.request.Request(GOOGLE_FONTS_GITHUB_TREE_API, headers=_github_headers())
    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise RuntimeError(
            "Failed to read Google Fonts repo index from GitHub API. "
            "Set GITHUB_TOKEN to avoid anonymous rate-limit."
        ) from exc

    tree = payload.get("tree", [])
    index: dict[str, list[dict]] = {}
    for item in tree:
        if item.get("type") != "blob":
            continue
        path = item.get("path", "")
        if not path:
            continue
        lower = path.lower()
        if not (lower.endswith(".ttf") or lower.endswith(".otf")):
            continue
        segments = path.split("/")
        if len(segments) < 3:
            continue
        bucket = segments[0]
        folder = segments[1]
        if bucket not in ("ofl", "apache", "ufl"):
            continue
        key = f"{bucket}/{folder}"
        index.setdefault(key, []).append(
            {
                "name": segments[-1],
                "download_url": f"https://raw.githubusercontent.com/google/fonts/main/{path}",
            }
        )
    return index


def download_fonts(
    selected: list[dict],
    output_dir: Path,
    dry_run: bool = False,
    max_files_per_family: int = 2,
) -> list[dict]:
    output_dir.mkdir(parents=True, exist_ok=True)
    downloaded: list[dict] = []
    font_index = build_repo_font_index()

    for family in selected:
        family_name = family.get("family", "unknown")
        row = {
            "family": family_name,
            "subsets": family.get("subsets", []),
            "target_dir": str(output_dir / slugify_family(family_name)),
        }
        family_repo_key = None
        for bucket in ("ofl", "apache", "ufl"):
            candidate = f"{bucket}/{folder_key(family_name)}"
            if candidate in font_index:
                family_repo_key = candidate
                break
        if not family_repo_key:
            row["status"] = "not_found_in_google_fonts_repo"
            downloaded.append(row)
            continue

        row["repo_path"] = family_repo_key
        files = font_index.get(family_repo_key, [])
        font_files = [
            item
            for item in files
            if Path(item.get("name", "")).suffix.lower() in {".ttf", ".otf"}
        ]
        font_files = sorted(
            font_files,
            key=lambda item: _font_file_priority(item.get("name", "")),
        )[:max_files_per_family]
        row["font_file_count"] = len(font_files)
        if not font_files:
            row["status"] = "no_ttf_or_otf_in_repo_folder"
            downloaded.append(row)
            continue

        family_dir = output_dir / slugify_family(family_name)
        row["status"] = "planned" if dry_run else "downloaded"
        downloaded.append(row)
        if dry_run:
            continue

        family_dir.mkdir(parents=True, exist_ok=True)
        for item in font_files:
            download_url = item.get("download_url")
            if not download_url:
                continue
            target_path = family_dir / item["name"]
            if target_path.exists():
                continue
            with urllib.request.urlopen(download_url, timeout=90) as response:
                target_path.write_bytes(response.read())

    return downloaded


def _font_file_priority(name: str) -> tuple[int, str]:
    text = name.lower()
    if "[wght]" in text or "variablefont" in text:
        return (0, text)
    if "regular" in text:
        return (1, text)
    if "medium" in text:
        return (2, text)
    if "bold" in text:
        return (3, text)
    return (9, text)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Batch download Google Fonts for CJK-first poster usage."
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Target folder for downloaded fonts.",
    )
    parser.add_argument(
        "--cjk-limit-per-lang",
        type=int,
        default=5,
        help="How many families to select per CJK language bucket (zh/ja/ko).",
    )
    parser.add_argument(
        "--en-limit",
        type=int,
        default=5,
        help="How many Latin-focused families to select.",
    )
    parser.add_argument(
        "--max-files-per-family",
        type=int,
        default=2,
        help="Maximum font files to download per family (prioritize variable/regular).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only print planned downloads without writing files.",
    )
    args = parser.parse_args()

    metadata = fetch_metadata()
    selected = select_families(
        metadata,
        cjk_limit_per_lang=args.cjk_limit_per_lang,
        en_limit=args.en_limit,
    )
    rows = download_fonts(
        selected,
        Path(args.output_dir),
        dry_run=args.dry_run,
        max_files_per_family=args.max_files_per_family,
    )

    print(
        json.dumps(
            {
                "selected_count": len(selected),
                "download_count": len(rows),
                "dry_run": args.dry_run,
                "output_dir": str(Path(args.output_dir).resolve()),
                "fonts": rows,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
