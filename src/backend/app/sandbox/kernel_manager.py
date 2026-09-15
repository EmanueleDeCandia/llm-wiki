"""Pipeline C — Kernel di esecuzione sandbox (Skill §4-C, §5.2).

Esecuzione Python isolata in **sottoprocesso** (`python -I`, isolated mode)
con:
* timeout vincolante (default 30 s, configurabile);
* cattura di stdout/stderr;
* figure matplotlib automaticamente salvate in `sources/images/generated/`
  e restituite come base64 + path;
* script persistenti in `scripts/generated/task_{timestamp}.py`.

La firma `run()` è identica a quella di un eventuale `JupyterKernelGateway`
(`jupyter_client` opzionale): la sostituzione non tocca API né frontend.
"""
from __future__ import annotations

import base64
import os
import shutil
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from ..core.vault import Vault
from .prelude import build_script

MAX_DATA_URL_BYTES = 5 * 1024 * 1024


@dataclass
class Figure:
    name: str
    path: str  # relativo al vault
    size_bytes: int = 0
    data_url: str = ""


@dataclass
class SandboxResult:
    task_id: str
    script_path: str
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    duration_ms: int = 0
    timed_out: bool = False
    error: str | None = None
    figures: list[Figure] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.timed_out and self.error is None and self.exit_code == 0


def dataset_loader_snippet(vault_rel: str) -> str:
    """Snippet di contesto dati: espone `df` (polars) e `LLW_DATASET`."""
    return f"""
# --- contesto dati (iniettato dal kernel manager) ---
import os as _ctx_os
import polars as pl

LLW_DATASET_REL = {vault_rel!r}  # relativo a sources/
LLW_DATASET = _ctx_os.path.join(LLW_VAULT, "sources", LLW_DATASET_REL)

def load_dataset():
    \"\"\"Carica il dataset corrente come DataFrame polars.\"\"\"
    ext = _ctx_os.path.splitext(LLW_DATASET)[1].lower()
    if ext in (".csv", ".tsv"):
        return pl.read_csv(LLW_DATASET, separator="\\t" if ext == ".tsv" else ",")
    if ext == ".parquet":
        return pl.read_parquet(LLW_DATASET)
    raise ValueError(f"Formato dataset non supportato dal loader: {{ext}}")

df = load_dataset()
print(f"[llm-wiki] dataset caricato: {{LLW_DATASET_REL}} -> {{df.shape[0]}}x{{df.shape[1]}}")
# --- fine contesto dati ---
"""


class KernelManager:
    """Istanza del runtime di calcolo per il vault aperto."""

    def __init__(self, vault: Vault, timeout: int = 30, python: str = "") -> None:
        self.vault = vault
        self.timeout = timeout
        self.python = python or sys.executable

    def run(self, code: str, task_name: str | None = None,
            dataset_rel: str | None = None) -> SandboxResult:
        code = code.strip()
        if not code:
            return SandboxResult(task_id="", script_path="", error="Codice Python vuoto")

        task_id = time.strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]
        name = task_name or "task"
        slug = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)[:40] or "task"
        script_rel = f"scripts/generated/{slug}_{task_id}.py"
        script_path = self.vault.root / script_rel
        script_path.parent.mkdir(parents=True, exist_ok=True)

        script = build_script(code)
        if dataset_rel:
            script = script.replace(
                "# --- fine prelude ---",
                "# --- fine prelude ---" + dataset_loader_snippet(dataset_rel),
                1,
            )
        script_path.write_text(script, encoding="utf-8")

        out_dir = self.vault.generated_images
        out_dir.mkdir(parents=True, exist_ok=True)
        manifest = out_dir / "llw_manifest.json"
        if manifest.exists():
            manifest.unlink()

        env = {
            **os.environ,
            "LLW_VAULT": str(self.vault.root),
            "LLW_OUT_DIR": str(out_dir),
            "MPLBACKEND": "Agg",
            "PYTHONIOENCODING": "utf-8",
            "MPLCONFIGDIR": str(self.vault.root / ".mplcache"),
        }
        start = time.perf_counter()
        timed_out = False
        proc_err: str | None = None
        exit_code: int | None = None
        stdout = stderr = ""
        try:
            proc = subprocess.run(
                [self.python, "-I", str(script_path)],
                cwd=str(self.vault.root),
                env=env,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
            exit_code = proc.returncode
            stdout, stderr = proc.stdout, proc.stderr
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            stdout = exc.stdout or "" if isinstance(exc.stdout, str) else (exc.stdout or b"").decode("utf-8", "replace")
            stderr = exc.stderr or "" if isinstance(exc.stderr, str) else (exc.stderr or b"").decode("utf-8", "replace")
            proc_err = f"Timeout: esecuzione interrotta dopo {self.timeout}s"
        duration_ms = int((time.perf_counter() - start) * 1000)

        if timed_out:
            return SandboxResult(
                task_id=task_id, script_path=script_rel, exit_code=None,
                stdout=stdout, stderr=stderr + f"\n{proc_err}",
                duration_ms=duration_ms, timed_out=True, error=proc_err,
            )

        return SandboxResult(
            task_id=task_id,
            script_path=script_rel,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr
            + (
                "\n[suggerimento] 'df' non esiste: è definito solo se selezioni un dataset nel campo "
                "'dataset' (es. datasets/sales.csv) prima di eseguire."
                if exit_code
                and not dataset_rel
                and "name 'df' is not defined" in stderr
                else ""
            ),
            duration_ms=duration_ms,
            figures=self._collect_figures(manifest, out_dir),
        )

    def _collect_figures(self, manifest: Path, out_dir: Path) -> list[Figure]:
        names: list[str] = []
        try:
            if manifest.exists():
                for line in manifest.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    import json

                    try:
                        item = json.loads(line)
                        if item.get("figure"):
                            names.append(item["figure"])
                    except json.JSONDecodeError:
                        pass
                manifest.unlink()
        except OSError:
            pass
        # fallback: file png/jpeg nati durante l'esecuzione
        if not names:
            now = time.time()
            for p in out_dir.iterdir():
                if p.suffix.lower() in (".png", ".jpg", ".jpeg") and now - p.stat().st_mtime < 30:
                    names.append(p.name)
        figures: list[Figure] = []
        for name in names:
            p = out_dir / name
            if not p.is_file():
                continue
            size = p.stat().st_size
            data_url = ""
            if size <= MAX_DATA_URL_BYTES:
                b64 = base64.b64encode(p.read_bytes()).decode("ascii")
                mime = "image/png" if p.suffix == ".png" else "image/jpeg"
                data_url = f"data:{mime};base64,{b64}"
            figures.append(Figure(
                name=name,
                path=self.vault.rel(p),
                size_bytes=size,
                data_url=data_url,
            ))
        return figures


def create_kernel(vault: Vault, timeout: int = 30, python: str = "") -> KernelManager:
    """Factory del kernel. In futuro: `LLW_KERNEL=jupyter` passerà a un
    `JupyterKernelGateway` (jupyter_client) con la stessa firma run()."""
    if os.environ.get("LLW_KERNEL", "subprocess") == "jupyter":
        try:
            import jupyter_client  # type: ignore # noqa: F401

            raise NotImplementedError(
                "JupyterKernelGateway in fase di integrazione: usa LLW_KERNEL=subprocess"
            )
        except ImportError:
            pass
    return KernelManager(vault, timeout=timeout, python=python)
