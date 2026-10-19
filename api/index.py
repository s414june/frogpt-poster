"""Vercel ASGI entrypoint for poster tool API."""

import sys
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from gpt_package.openai_tool import TOOL_NAME, build_tool_definition, handle_tool_call

app = FastAPI(title="Poster Tool API", version="0.1.0")


class ToolCallRequest(BaseModel):
    arguments: dict[str, Any] = Field(default_factory=dict)


@app.get("/health")
def health() -> dict[str, Any]:
    return {"ok": True, "service": "poster-tool-api"}


@app.get("/tool")
def tool_definition() -> dict[str, Any]:
    return build_tool_definition()


@app.post("/poster")
def poster(payload: ToolCallRequest) -> dict[str, Any]:
    result = handle_tool_call(payload.arguments)
    return {"tool_name": TOOL_NAME, "result": result}

