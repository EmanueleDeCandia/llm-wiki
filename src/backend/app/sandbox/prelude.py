"""Prelude iniettato negli script sandbox (Skill §4-C, §5.2).

Configura matplotlib in modalità non-interattiva (Agg), intercetta
`plt.show()` e `save_figure()` per persistere le figure in
`sources/images/generated/` e scrivere un manifesto leggibile dal kernel
manager. L'ambiente è un sottoprocesso Python isolato (`-I`, isolated mode)
con timeout vincolante: nessun stato condiviso con il processo sidecar.
"""
from __future__ import annotations

PRELUDE = '''\
# --- LLM Wiki sandbox prelude (iniettato automaticamente) ---
import os as _llw_os
import json as _llw_json

LLW_VAULT = _llw_os.environ.get("LLW_VAULT", _llw_os.getcwd())
LLW_OUT_DIR = _llw_os.environ.get(
    "LLW_OUT_DIR",
    _llw_os.path.join(LLW_VAULT, "sources", "images", "generated"),
)
_llw_os.makedirs(LLW_OUT_DIR, exist_ok=True)
LLW_MANIFEST = _llw_os.path.join(LLW_OUT_DIR, "llw_manifest.json")

try:
    import matplotlib as _llw_mpl
    _llw_mpl.use("Agg", force=True)
    import matplotlib.pyplot as plt

    _llw_saved: list[str] = []

    def save_figure(fig=None, name=None):
        \"\"\"Salva una figura in sources/images/generated/ e la riporta nel manifesto.\"\"\"
        if fig is None:
            fig = plt.gcf()
        if fig is None:
            print("[llm-wiki] save_figure: nessuna figura attiva")
            return None
        name = name or f"plot_{len(_llw_saved) + 1}.png"
        path = _llw_os.path.join(LLW_OUT_DIR, name)
        fig.savefig(path, dpi=130, bbox_inches="tight")
        _llw_saved.append(name)
        try:
            with open(LLW_MANIFEST, "a", encoding="utf-8") as _f:
                _f.write(_llw_json.dumps({"figure": name}) + "\\n")
        except OSError:
            pass
        print(f"[llm-wiki] figura salvata: {name}")
        return path

    _llw_orig_show = plt.show

    def _llw_show(*args, **kwargs):
        \"\"\"plt.show() in headless: salva le figure attive invece di bloccare.\"\"\"
        if plt.get_fignums():
            for _num in plt.get_fignums():
                try:
                    save_figure(plt.figure(_num))
                except Exception as _exc:  # noqa: BLE001
                    print(f"[llm-wiki] errore salvataggio figura {_num}: {_exc}")
            plt.close("all")
        _llw_orig_show(*args, **kwargs)

    plt.show = _llw_show
except ImportError:
    def save_figure(fig=None, name=None):  # type: ignore
        print("[llm-wiki] matplotlib non disponibile")
        return None

# --- fine prelude ---
'''

FOOTER = "\n# --- fine script sandbox LLM Wiki ---\n"


def build_script(user_code: str) -> str:
    return PRELUDE + "\n" + user_code.rstrip() + FOOTER
