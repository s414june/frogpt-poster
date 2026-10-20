"""Public API, lazily imported so health checks do not load rendering dependencies."""
__all__ = ["PosterGenerator","PosterRequest","TOOL_NAME","build_tool_definition","handle_tool_call"]
def __getattr__(name):
    if name == "PosterGenerator":
        from .client import PosterGenerator
        return PosterGenerator
    if name == "PosterRequest":
        from .types import PosterRequest
        return PosterRequest
    if name in ("TOOL_NAME","build_tool_definition","handle_tool_call"):
        from . import openai_tool
        return getattr(openai_tool,name)
    raise AttributeError(name)
