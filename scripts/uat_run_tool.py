import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gpt_package.openai_tool import TOOL_NAME, build_tool_definition, handle_tool_call


def main() -> int:
    parser = argparse.ArgumentParser(description="Run local UAT for poster tool handler.")
    parser.add_argument(
        "--input",
        required=True,
        help="Path to tool-call JSON containing {\"arguments\": {...}}",
    )
    parser.add_argument(
        "--show-schema",
        action="store_true",
        help="Print tool schema before executing the call",
    )
    args = parser.parse_args()

    if args.show_schema:
        print(json.dumps(build_tool_definition(), ensure_ascii=False, indent=2))

    input_path = Path(args.input)
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    arguments = payload.get("arguments", {})
    result = handle_tool_call(arguments)
    jpg_path = _save_jpg_preview(result)
    payload_out = {"tool": TOOL_NAME, "result": result}
    if jpg_path:
        payload_out["uat_jpg_output"] = jpg_path
    print(json.dumps(payload_out, ensure_ascii=False, indent=2))
    return 0


def _save_jpg_preview(result: dict) -> str | None:
    if not isinstance(result, dict):
        return None
    if not result.get("ok") or not result.get("rendered"):
        return None
    output_path = str(result.get("output_path", "")).strip()
    if not output_path:
        return None
    source = Path(output_path)
    if not source.is_file():
        return None

    out_dir = Path("outputs") / "uat-jpg"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = out_dir / f"{source.stem}-{stamp}.jpg"
    with Image.open(source) as img:
        img.convert("RGB").save(target, format="JPEG", quality=92, optimize=True)
    return str(target.resolve())


if __name__ == "__main__":
    raise SystemExit(main())
