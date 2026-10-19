"""Download a fixed Pexels reference set and write manifest for MCP usage."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gpt_package.reference_images import resolve_reference_url


PEXELS_PAGE_URLS = [
    "https://www.pexels.com/zh-tw/photo/460621/",
    "https://www.pexels.com/zh-tw/photo/13392284/",
    "https://www.pexels.com/zh-tw/photo/38904020/",
    "https://www.pexels.com/zh-tw/photo/167699/",
    "https://www.pexels.com/zh-tw/photo/1527934/",
    "https://www.pexels.com/zh-tw/photo/17720580/",
    "https://www.pexels.com/zh-tw/photo/1591373/",
    "https://www.pexels.com/zh-tw/photo/36821001/",
    "https://www.pexels.com/zh-tw/photo/1270184/",
    "https://www.pexels.com/zh-tw/photo/30784971/",
    "https://www.pexels.com/zh-tw/photo/40213797/",
    "https://www.pexels.com/zh-tw/photo/38683553/",
    "https://www.pexels.com/zh-tw/photo/3d-34939148/",
    "https://www.pexels.com/zh-tw/photo/30925664/",
    "https://www.pexels.com/zh-tw/photo/30713980/",
    "https://www.pexels.com/zh-tw/photo/1435752/",
    "https://www.pexels.com/zh-tw/photo/38661110/",
]


def main() -> None:
    root = Path("assets") / "reference-library" / "pexels"
    root.mkdir(parents=True, exist_ok=True)
    manifest_items: list[dict] = []

    for idx, page_url in enumerate(PEXELS_PAGE_URLS):
        resolved = resolve_reference_url(page_url)
        image_url = str(resolved.get("url", "")).strip()
        if not image_url.startswith("http"):
            raise RuntimeError(f"Failed to resolve image URL: {page_url}")

        ext = Path(urlparse(image_url).path).suffix.lower()
        if ext not in (".jpg", ".jpeg", ".png", ".webp"):
            ext = ".jpg"
        photo_id = resolved.get("photo_id") or (idx + 1)
        file_name = f"pexels-{photo_id}{ext}"
        file_path = root / file_name
        _download_binary(image_url, file_path)

        manifest_items.append(
            {
                "id": f"pexels-{photo_id}",
                "source": "pexels",
                "photo_id": photo_id,
                "photographer": resolved.get("photographer", ""),
                "credit_label": resolved.get("credit_label", ""),
                "page_url": resolved.get("page_url", page_url),
                "image_url": image_url,
                "local_path": str(file_path).replace("/", "\\"),
            }
        )
        print(f"[{idx + 1}/{len(PEXELS_PAGE_URLS)}] downloaded {file_name}")

    manifest = {"source": "pexels", "count": len(manifest_items), "items": manifest_items}
    (root / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved manifest: {(root / 'manifest.json')}")


def _download_binary(url: str, output_path: Path) -> None:
    req = Request(url, headers={"User-Agent": "frogpt-poster/1.0"})
    with urlopen(req, timeout=60) as response:
        content = response.read()
    if not content:
        raise RuntimeError(f"Empty download: {url}")
    output_path.write_bytes(content)


if __name__ == "__main__":
    main()
