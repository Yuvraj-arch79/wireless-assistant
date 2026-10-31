"""Versioned development limits. Secrets never enter stored snapshots."""
import os
from pathlib import Path
from pydantic import BaseModel, ConfigDict, Field, model_validator
from .common import digest

ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    data_dir: Path = ROOT / "data" / "app"
    port: int = Field(default=8765, ge=1024, le=65535)
    model_a: str = Field(default="gemini-3.8-flash", pattern=r"^[a-zA-Z0-9._-]+$")
    model_b: str = Field(default="gemini-3.8-flash", pattern=r"^[a-zA-Z0-9._-]+$")
    model_c: str = Field(default="gemini-3.8-flash", pattern=r"^[a-zA-Z0-9._-]+$")
    embedding_model: str = "gemini-embedding-001"
    embedding_dimensions: int = Field(default=768, ge=128, le=3072)
    # Lexical preview is developer-only. Chat requires a compatible hybrid build.
    active_seconds: float = Field(default=180, gt=0, le=600)
    call_seconds: float = Field(default=25, gt=0, le=60)
    tool_seconds: float = Field(default=5, gt=0, le=30)
    max_calls: int = Field(default=12, ge=3, le=24)
    max_retries: int = Field(default=2, ge=0, le=3)
    max_repairs: int = Field(default=1, ge=0, le=1)
    max_steps: int = Field(default=96, ge=1, le=192)
    max_searches: int = Field(default=4, ge=1, le=8)
    max_history: int = Field(default=4, ge=1, le=8)
    max_tools: int = Field(default=24, ge=1, le=48)
    max_input_bytes: int = Field(default=4000, ge=100, le=32768)
    role_input_bound: int = Field(default=24000, ge=4000, le=48000)
    role_output_tokens: int = Field(default=2000, ge=256, le=4000)
    total_token_bound: int = Field(default=250000, ge=10000, le=500000)
    recent_bound: int = Field(default=1500, ge=100, le=4000)
    history_map_bound: int = Field(default=800, ge=100, le=1600)
    max_passages: int = Field(default=12, ge=1, le=20)
    evidence_bound: int = Field(default=11000, ge=1000, le=20000)
    max_active: int = Field(default=2, ge=1, le=2)
    default_release: str = "18"
    config_version: str = "prototype-0.1"

    @model_validator(mode="after")
    def reserve_fits(self):
        if self.embedding_model != "gemini-embedding-001":
            raise ValueError("Embedding model change needs a reviewed compatible rebuild")
        if self.default_release != "18":
            raise ValueError("Only the pinned Release 18 baseline is configured")
        if self.total_token_bound < 3 * (self.role_input_bound + self.role_output_tokens):
            raise ValueError("Token budget cannot cover A/B/C")
        return self

    def snapshot(self):
        data = self.model_dump(mode="json", exclude={"data_dir"})
        data["contract_version"] = "1"
        data["tokenizer_version"] = "utf8-byte-upper-bound-v1"
        data["prompt_version"] = "abc-v1"
        return data

    @property
    def config_hash(self):
        return digest(self.snapshot())

    @property
    def database(self):
        return self.data_dir / "assistant.sqlite3"

    @classmethod
    def environment(cls):
        args = {}
        for field in ("data_dir", "port", "model_a", "model_b", "model_c"):
            value = os.environ.get("WA_" + field.upper())
            if value:
                args[field] = value
        return cls(**args)
