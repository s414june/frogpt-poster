import argparse
import json
import sys
from pathlib import Path

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
    print(json.dumps({"tool": TOOL_NAME, "result": result}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

