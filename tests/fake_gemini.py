"""A scripted stand-in for google-genai's Client, so the agent loop is tested without a key or network."""
from __future__ import annotations

from types import SimpleNamespace

from google.genai import types


def call(name: str, **args):
    return ("call", [(name, args)])


def text(answer: str):
    return ("text", answer)


class _Models:
    def __init__(self, script):
        self.script = list(script)
        self.requests: list[list] = []  # the `contents` the agent sent each turn

    def generate_content(self, model, contents, config):
        self.requests.append(list(contents))
        kind, payload = self.script.pop(0) if self.script else self.script_exhausted()
        if kind == "text":
            return SimpleNamespace(function_calls=None, text=payload, candidates=[])
        parts = [types.Part.from_function_call(name=n, args=a) for n, a in payload]
        content = types.Content(role="model", parts=parts)
        calls = [SimpleNamespace(name=n, args=a) for n, a in payload]
        return SimpleNamespace(function_calls=calls, text=None, candidates=[SimpleNamespace(content=content)])

    @staticmethod
    def script_exhausted():
        raise AssertionError("agent asked for more model turns than the script provides")


class FakeGemini:
    def __init__(self, script):
        self.models = _Models(script)
