"""Test del kernel sandbox — Pipeline C (Step 3 della Skill)."""
from __future__ import annotations

from pathlib import Path

from app.core.vault import Vault
from app.index.index_builder import write_indexes
from app.sandbox.kernel_manager import KernelManager

from .conftest import SAMPLE_PAPER


def _vault(vault_root: Path) -> Vault:
    vault = Vault(root=vault_root, template_root=vault_root)
    vault.ensure_topology()
    (vault.root / "sources" / "papers" / "paper.txt").write_text(SAMPLE_PAPER, encoding="utf-8")
    write_indexes(vault)
    return vault


def test_simple_stdout(vault_root: Path) -> None:
    vault = _vault(vault_root)
    km = KernelManager(vault, timeout=30)
    res = km.run('print("hello-sandbox", 1 + 1)')
    assert res.ok, res.stderr
    assert "hello-sandbox 2" in res.stdout
    assert res.exit_code == 0
    assert res.script_path.startswith("scripts/generated/")
    assert (vault.root / res.script_path).is_file()  # script persistente (§2)


def test_matplotlib_figure_saved(vault_root: Path) -> None:
    vault = _vault(vault_root)
    km = KernelManager(vault, timeout=60)
    code = (
        "import matplotlib.pyplot as plt\n"
        "fig, ax = plt.subplots()\n"
        "ax.plot([1, 2, 3], [4, 5, 6])\n"
        "ax.set_title('test')\n"
        "plt.show()\n"
    )
    res = km.run(code)
    assert res.ok, res.stderr
    assert len(res.figures) == 1
    f = res.figures[0]
    assert f.path.startswith("sources/images/generated/")
    assert (vault.root / f.path).is_file()
    assert f.data_url.startswith("data:image/png;base64,")


def test_timeout_enforced(vault_root: Path) -> None:
    vault = _vault(vault_root)
    km = KernelManager(vault, timeout=1)
    import time

    start = time.time()
    res = km.run("import time\ntime.sleep(5)\n")
    elapsed = time.time() - start
    assert res.timed_out
    assert res.error and "Timeout" in res.error
    assert elapsed < 4.5  # ucciso ben prima dei 5s


def test_error_capture(vault_root: Path) -> None:
    vault = _vault(vault_root)
    km = KernelManager(vault, timeout=30)
    res = km.run("raise ValueError('boom-42')")
    assert not res.ok
    assert res.exit_code not in (0, None)
    assert "boom-42" in res.stderr


def test_dataset_context(vault_root: Path) -> None:
    vault = _vault(vault_root)
    csv = vault.root / "sources" / "datasets" / "sales.csv"
    csv.write_text("a,b\n1,2\n3,4\n5,6\n", encoding="utf-8")
    km = KernelManager(vault, timeout=30)
    res = km.run("print('shape', df.shape)", dataset_rel="datasets/sales.csv")
    assert res.ok, res.stderr
    assert "shape (3, 2)" in res.stdout
    assert "sales.csv" in res.stdout  # loader stampato


def test_sandbox_does_not_touch_sources(vault_root: Path) -> None:
    """Lo script sandbox non deve poter scrivere nelle sorgenti originali:
    l'app lo esegue nel vault ma verifica l'hash dopo l'operazione."""
    vault = _vault(vault_root)
    vault.snapshot_sources()
    km = KernelManager(vault, timeout=30)
    km.run("print('ok')")
    assert vault.verify_sources() == []
