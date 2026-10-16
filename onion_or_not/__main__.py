"""Command line: `onion-or-not` starts the site; `onion-or-not download` fetches the open model."""
from __future__ import annotations

import argparse
import sys
import webbrowser


def main(argv=None) -> None:
    from .config import QUANTS, settings

    p = argparse.ArgumentParser(prog="onion-or-not", description="Satire or real news? Ask Jev and AnyJev.")
    sub = p.add_subparsers(dest="cmd")
    s = sub.add_parser("serve", help="start the site (the default)")
    s.add_argument("--host", default=settings.host)
    s.add_argument("--port", type=int, default=settings.port)
    s.add_argument("--no-browser", action="store_true", help="don't open a browser tab")
    d = sub.add_parser("download", help="download Qwen3-8B (GGUF) from Hugging Face for AnyJev")
    d.add_argument("--quant", default=settings.quant, choices=QUANTS,
                   help="Q4_K_M ≈ 5 GB (default), Q5_K_M ≈ 5.9 GB, Q6_K ≈ 6.7 GB, Q8_0 ≈ 8.7 GB")
    a = p.parse_args(argv)

    if a.cmd == "download":
        from .models import download
        print(f"Downloading Qwen3-8B-{a.quant}.gguf from huggingface.co/Qwen/Qwen3-8B-GGUF ...")
        path = download(a.quant)
        print(f"Saved to {path}")
        if a.quant != settings.quant and not settings.gguf_override:
            print(f"To use it, set ONION_QUANT={a.quant} in .env")
        return

    host = getattr(a, "host", settings.host)
    port = getattr(a, "port", settings.port)
    if host not in ("127.0.0.1", "localhost", "::1"):
        print(f"Warning: serving on {host} makes the site, and your TypeSafe key's usage, reachable from "
              f"other machines.", file=sys.stderr)
    url = f"http://{'127.0.0.1' if host in ('0.0.0.0', '::') else host}:{port}"
    print(f"Onion or Not → {url}  (Ctrl+C to stop)")
    if not getattr(a, "no_browser", False):
        try:
            webbrowser.open(url)
        except Exception:
            pass
    import uvicorn
    uvicorn.run("onion_or_not.server:app", host=host, port=port, log_level="warning")


if __name__ == "__main__":
    main()
