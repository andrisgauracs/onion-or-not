"""The three models the site can ask, all with the same question about the headline text only.

- Jev: TypeSafe's hosted decision model, through the official `typesafe-sdk`. Needs TYPESAFE_API_KEY.
- AnyJev L0: Qwen3-8B on this machine (llama.cpp), read out by AnyJev's `Decider` at level "L0" with a
  content-free prior: it reads the options in every order and removes the model's bias toward one option.
- Qwen3-8B raw: the same model and the same readout without the L0 correction, for comparison.
"""
from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional

from .config import settings

QUESTION = "Is this headline satire from The Onion, or real news?"
OPTIONS = ["satire", "real news"]
QWEN_TOKENIZER = "Qwen/Qwen3-8B"
GGUF_REPO = "Qwen/Qwen3-8B-GGUF"
JEV_PRICE_PER_INPUT_TOKEN = 0.042 / 1e6       # USD; output tokens are free (TypeSafe pricing, Oct 2026)


def ask_order(swapped: bool) -> List[str]:
    return OPTIONS[::-1] if swapped else list(OPTIONS)


# ------------------------------------------------------------------------------------------- Jev
class Jev:
    def __init__(self):
        self._client = None

    def status(self) -> Dict:
        if not settings.typesafe_api_key:
            return dict(ready=False, reason="no_key", model=settings.jev_model)
        return dict(ready=True, model=settings.jev_model)

    def ask(self, headline: str, swapped: bool = False) -> Dict:
        from typesafe_sdk import Choice, RetryPolicy, TypeSafeClient
        if not settings.typesafe_api_key:
            raise RuntimeError("TYPESAFE_API_KEY is not set. Add it to .env and restart.")
        if self._client is None:
            self._client = TypeSafeClient(api_key=settings.typesafe_api_key)
        options = ask_order(swapped)
        t0 = time.perf_counter()
        r = self._client.system_one(
            state=headline,
            questions={"verdict": Choice(instructions=QUESTION, criteria={o: None for o in options})},
            model=settings.jev_model,
            # also retry 499, which the API can return when a request is dropped mid-flight
            retry=RetryPolicy(max_retries=4, backoff_initial=0.5, backoff_max=8.0, timeout=60.0,
                              http_statuses={408, 429, 499, *range(500, 600)}))
        ms = (time.perf_counter() - t0) * 1000
        a = r.choices["verdict"]
        cost = r.usage.input_tokens * JEV_PRICE_PER_INPUT_TOKEN
        return dict(probs={o: float(a.probabilities[o]) for o in OPTIONS}, latency_ms=ms,
                    model=r.model, cost_usd=cost)


# ------------------------------------------------------------------------------------- local model
class LocalQwen:
    """One GGUF loaded once and shared by the raw and L0 readouts. llama.cpp isn't thread-safe, so every
    call takes the lock."""

    def __init__(self):
        self.lock = threading.Lock()
        self.backend = None
        self.deciders: Dict[str, object] = {}
        self.loading = False
        self.load_error: Optional[str] = None
        self.load_seconds: Optional[float] = None

    def model_path(self) -> Path:
        return settings.gguf_path

    def status(self) -> Dict:
        p = self.model_path()
        base = dict(model=f"Qwen3-8B {settings.quant_label}", file=str(p))
        if self.load_error:
            return dict(base, ready=False, reason="load_error", detail=self.load_error)
        if self.backend is not None:
            return dict(base, ready=True, loaded=True)
        if not p.exists():
            return dict(base, ready=False, reason="no_model")
        return dict(base, ready=True, loaded=False, loading=self.loading)

    def load(self) -> None:
        with self.lock:
            if self.backend is not None:
                return
            self.loading = True
            try:
                if not self.model_path().exists():
                    raise FileNotFoundError(f"{self.model_path()} not found. Run: onion-or-not download")
                from anyjev import Decider
                from anyjev.backends.llamacpp import LlamaCppBackend
                t0 = time.perf_counter()
                # the HF tokenizer renders the prompts and is checked token for token against the GGUF;
                # n_gpu_layers=-1 puts every layer on the GPU (the backend's default, 0, is CPU only)
                self.backend = LlamaCppBackend(str(self.model_path()), tokenizer=QWEN_TOKENIZER,
                                               n_gpu_layers=settings.gpu_layers, n_ctx=2048)
                self.deciders = {
                    "raw": Decider(self.backend, level="raw"),
                    "anyjev": Decider(self.backend, level="L0", prior="content_free"),
                }
                self._ask_locked("anyjev", "warm-up", False)   # computes the content-free prior once
                self.load_seconds = time.perf_counter() - t0
                self.load_error = None
            except Exception as e:
                self.backend, self.deciders = None, {}
                self.load_error = f"{type(e).__name__}: {e}"
                raise
            finally:
                self.loading = False

    def _ask_locked(self, which: str, headline: str, swapped: bool) -> Dict:
        from anyjev import Question
        q = Question.choice(QUESTION, ask_order(swapped), name="verdict")
        level = "L0" if which == "anyjev" else "raw"
        t0 = time.perf_counter()
        d = self.deciders[which].decide(headline, [q], require=level)["verdict"]
        ms = (time.perf_counter() - t0) * 1000
        return dict(probs={o: float(d.distribution[o]) for o in OPTIONS}, latency_ms=ms,
                    model=f"Qwen3-8B {settings.quant_label}" + (" · AnyJev L0" if level == "L0" else " · no correction"),
                    cost_usd=0.0)

    def ask(self, which: str, headline: str, swapped: bool = False) -> Dict:
        if self.backend is None:
            self.load()
        with self.lock:
            return self._ask_locked(which, headline, swapped)


jev = Jev()
local = LocalQwen()


def ask(model: str, headline: str, swapped: bool = False) -> Dict:
    if model == "jev":
        return jev.ask(headline, swapped)
    if model in ("anyjev", "raw"):
        return local.ask(model, headline, swapped)
    raise ValueError(f"unknown model {model!r}")


def download(quant: str) -> Path:
    from huggingface_hub import hf_hub_download
    name = f"Qwen3-8B-{quant}.gguf"
    settings.models_dir.mkdir(parents=True, exist_ok=True)
    return Path(hf_hub_download(GGUF_REPO, name, local_dir=str(settings.models_dir)))


os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
