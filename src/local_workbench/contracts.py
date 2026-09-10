from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import Field, model_validator

from .config import StrictModel


def canonical(value) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def digest(value) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


class Message(StrictModel):
    role: Literal["system", "user", "assistant"]
    content: str
    name: str | None = Field(default=None, max_length=100)


class ChatRequest(StrictModel):
    model: str
    messages: list[Message] = Field(min_length=1, max_length=128)
    stream: bool = False
    response_format: dict | None = None
    max_tokens: int | None = Field(default=None, ge=1)
    max_completion_tokens: int | None = Field(default=None, ge=1)
    temperature: float | None = Field(default=None, ge=0, le=2)

    @model_validator(mode="after")
    def nonstream(self):
        if self.stream:
            raise ValueError("streaming is not supported")
        if self.max_tokens is not None and self.max_completion_tokens is not None:
            raise ValueError("use only one completion token limit")
        if self.response_format:
            kind = self.response_format.get("type")
            if kind not in {"json_object", "json_schema", "text"}:
                raise ValueError("unsupported response_format")
            if kind == "json_schema":
                wrapper = self.response_format.get("json_schema")
                if not isinstance(wrapper, dict) or not isinstance(wrapper.get("schema"), dict):
                    raise ValueError("json_schema requires json_schema.schema")
        return self


class Evidence(StrictModel):
    id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,159}$")
    text: str = Field(min_length=1, max_length=24000)
    approved: bool = Field(default=False, strict=True)
    status: Literal["current", "historical", "superseded"] = "current"
    source_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    source: str | None = Field(default=None, max_length=500)
    span: dict[str, int] | None = None


class RetrievalRequest(StrictModel):
    query: str = Field(min_length=1, max_length=2000)
    limit: int = Field(default=5, ge=1, le=20)
    mode: Literal["lexical", "hybrid"] = "hybrid"


class TaskRequest(StrictModel):
    model: str = "local-workbench"
    kind: Literal["product_brief", "evidence_match", "decision_review"]
    task: str = Field(min_length=1, max_length=4000)
    evidence: list[Evidence] = Field(default_factory=list, max_length=50)
    retrieval: RetrievalRequest | None = None

    @model_validator(mode="after")
    def unique_evidence(self):
        if len({row.id for row in self.evidence}) != len(self.evidence):
            raise ValueError("evidence IDs must be unique")
        return self


QUOTE = {
    "type": "object",
    "additionalProperties": False,
    "required": ["evidence_id", "quote"],
    "properties": {
        "evidence_id": {"type": "string"},
        "quote": {"type": "string", "minLength": 1},
    },
}
STRINGS = {"type": "array", "maxItems": 12, "items": {"type": "string", "minLength": 1}}


def output_schema(kind: str) -> dict:
    props = {"answerable": {"type": "boolean"}}
    if kind == "product_brief":
        props.update(
            {
                "facts": {"type": "array", "maxItems": 12, "items": QUOTE},
                "proposal": {"type": ["string", "null"]},
                "assumptions": STRINGS,
                "unknowns": STRINGS,
            }
        )
    elif kind == "evidence_match":
        match = json.loads(json.dumps(QUOTE))
        match["properties"]["requirement"] = {"type": "string", "minLength": 1}
        match["required"].append("requirement")
        props.update(
            {
                "matches": {"type": "array", "maxItems": 12, "items": match},
                "gaps": STRINGS,
            }
        )
    else:
        props.update(
            {
                "findings": {"type": "array", "maxItems": 12, "items": QUOTE},
                "assessment": {"type": ["string", "null"]},
                "counterarguments": STRINGS,
                "unknowns": STRINGS,
            }
        )
    return {
        "type": "object",
        "additionalProperties": False,
        "required": list(props),
        "properties": props,
    }


def abstention(kind: str) -> dict:
    result = {"answerable": False}
    reason = ["No current approved evidence was provided."]
    if kind == "product_brief":
        result.update(facts=[], proposal=None, assumptions=[], unknowns=reason)
    elif kind == "evidence_match":
        result.update(matches=[], gaps=reason)
    else:
        result.update(findings=[], assessment=None, counterarguments=[], unknowns=reason)
    return result
