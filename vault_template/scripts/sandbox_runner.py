#!/usr/bin/env python3
"""Entrypoint di esecuzione dinamica per script del vault (Skill §2).

Uso autonomo (fuori dall'applicazione):
    python scripts/sandbox_runner.py scripts/generated/task_x.py

Riproduce il prelude del kernel manager (Agg, save_figure, manifesto)
così gli script in scripts/generated/ restano eseguibili anche in locale.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

VAULT = Path(__file__).resolve().parents[1]
OUT_DIR = VAULT / "sources" / "images" / "generated"
OUT_DIR.mkdir(parents=True, exist_ok=True)
MANIFEST = OUT_DIR / "llw_manifest.json"

os.environ.setdefault("LLW_VAULT", str(VAULT))
os.environ.setdefault("LLW_OUT_DIR", str(OUT_DIR))


def _install_matplotlib_hooks() -> None:
    try:
        import matplotlib

        matplotlib.use("Agg", force=True)
        import matplotlib.pyplot as plt
    except ImportError:
        return

    saved: list[str] = []

    def save_figure(fig=None, name: str | None = None) -> str | None:
        if fig is None:
            fig = plt.gcf()
        if fig is None:
            print("[sandbox] save_figure: nessuna figura attiva")
            return None
        name = name or f"plot_{len(saved) + 1}.png"
        path = OUT_DIR / name
        fig.savefig(path, dpi=130, bbox_inches="tight")
        saved.append(name)
        with open(MANIFEST, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"figure": name}) + "\n")
        print(f"[sandbox] figura salvata: {name}")
        return str(path)

    orig_show = plt.show

    def show(*args, **kwargs):  # noqa: ANN001, ANN003
        if plt.get_fignums():
            for num in plt.get_fignums():
                save_figure(plt.figure(num))
            plt.close("all")
        return orig_show(*args, **kwargs)

    plt.show = show
    globals()["save_figure"] = save_figure


def main() -> int:
    if len(sys.argv) < 2:
        print("uso: python scripts/sandbox_runner.py <script.py> [args...]")
        return 2
    _install_matplotlib_hooks()
    script = Path(sys.argv[1])
    if not script.is_absolute():
        script = VAULT / script
    sys.argv = [str(script), *sys.argv[2:]]
    with open(script, "r", encoding="utf-8") as fh:
        code = compile(fh.read(), str(script), "exec")
    g = {"__name__": "__main__", "__file__": str(script), "save_figure": globals().get("save_figure")}
    exec(code, g)  # noqa: S102 — script del vault, contesto fidato
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
