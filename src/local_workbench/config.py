from __future__ import annotations

import ipaddress
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ModelProfile(StrictModel):
    model: str = Field(min_length=1, max_length=200)
    num_ctx: int = Field(default=8192, ge=1024, le=131072)
    output_tokens: int = Field(default=768, ge=32, le=8192)
    temperature: float = Field(default=0, ge=0, le=2)
    thinking: bool = Field(default=False, strict=True)
    keep_alive: str = "5m"
    revision: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def leaves_input_capacity(self):
        if self.output_tokens + 512 >= self.num_ctx:
            raise ValueError("output_tokens must leave at least 512 tokens for input")
        return self


class RetrievalConfig(StrictModel):
    search_url: str = "http://127.0.0.1:8091/v1/search"
    corpus_id: str = "default"
    timeout_seconds: float = Field(default=30, ge=0.1, le=300)
    allow_remote: bool = False

    @model_validator(mode="after")
    def endpoint_is_explicit(self):
        validate_service_url(self.search_url, self.allow_remote)
        return self


def validate_service_url(value: str, allow_remote: bool = False) -> str:
    url = urlsplit(value)
    if url.scheme not in {"http", "https"} or not url.hostname:
        raise ValueError("service URL must be HTTP(S)")
    if url.username or url.password or url.query or url.fragment:
        raise ValueError("service URL cannot contain credentials, query or fragment")
    try:
        loopback = ipaddress.ip_address(url.hostname).is_loopback
    except ValueError:
        loopback = url.hostname.lower() == "localhost"
    if not loopback and (not allow_remote or url.scheme != "https"):
        raise ValueError("non-loopback services require explicit allow_remote and HTTPS")
    return value.rstrip("/")


class Settings(StrictModel):
    state_dir: Path
    ollama_url: str = "http://127.0.0.1:11434"
    allow_remote: bool = False
    ollama_token_env: str | None = None
    api_token_env: str | None = None
    models: dict[str, ModelProfile]
    queue_limit: int = Field(default=4, ge=0, le=32)
    queue_timeout_seconds: float = Field(default=20, gt=0, le=600)
    provider_timeout_seconds: float = Field(default=180, gt=0, le=1800)
    max_request_bytes: int = Field(default=1048576, ge=1024, le=8388608)
    max_response_bytes: int = Field(default=2097152, ge=1024, le=8388608)
    task_repairs: int = Field(default=1, ge=0, le=2)
    gateway_strip_json_fence: bool = False
    retrieval: RetrievalConfig | None = None

    @field_validator("state_dir", mode="before")
    @classmethod
    def explicit_state_path(cls, value):
        expanded = os.path.expandvars(str(value))
        if "$" in expanded or not Path(expanded).expanduser().is_absolute():
            raise ValueError("state_dir must resolve to an explicit absolute path")
        return Path(expanded).expanduser()

    @field_validator("ollama_token_env", "api_token_env")
    @classmethod
    def environment_names(cls, value):
        if value is not None and (
            not value or not value.replace("_", "A").isalnum() or value[0].isdigit()
        ):
            raise ValueError("token setting must be an environment variable name")
        return value

    @model_validator(mode="after")
    def validate_services(self):
        validate_service_url(self.ollama_url, self.allow_remote)
        if not self.models or len(self.models) > 16:
            raise ValueError("configure one to sixteen model aliases")
        for alias in self.models:
            if (
                not alias
                or len(alias) > 100
                or any(
                    c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.:"
                    for c in alias
                )
            ):
                raise ValueError("model alias contains unsupported characters")
        return self


def load_settings(path: str | Path) -> Settings:
    source = Path(path)
    if source.stat().st_size > 65536:
        raise ValueError("configuration exceeds 64 KiB")
    return Settings.model_validate(json.loads(source.read_text(encoding="utf-8")))
