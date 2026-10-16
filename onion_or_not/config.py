"""Settings, read from the environment and from a .env file in the folder you run from."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path.cwd() / ".env")
except ImportError:
    pass

QUANTS = ("Q4_K_M", "Q5_K_M", "Q6_K", "Q8_0")


@dataclass
class Settings:
    typesafe_api_key: str = os.environ.get("TYPESAFE_API_KEY", "").strip()
    jev_model: str = os.environ.get("JEV_MODEL", "jev-1.13.0").strip()
    quant: str = os.environ.get("ONION_QUANT", "Q4_K_M").strip()
    gguf_override: str = os.environ.get("ONION_GGUF", "").strip()
    gpu_layers: int = int(os.environ.get("ONION_GPU_LAYERS", "-1"))
    models_dir: Path = Path(os.environ.get("ONION_MODELS_DIR", "models")).expanduser()
    host: str = os.environ.get("HOST", "127.0.0.1").strip()
    port: int = int(os.environ.get("PORT", "8000"))

    @property
    def gguf_path(self) -> Path:
        if self.gguf_override:
            return Path(self.gguf_override).expanduser()
        return self.models_dir / f"Qwen3-8B-{self.quant}.gguf"

    @property
    def quant_label(self) -> str:
        if self.gguf_override:
            name = Path(self.gguf_override).name
            for q in QUANTS:
                if q in name:
                    return q
            return name
        return self.quant


settings = Settings()
