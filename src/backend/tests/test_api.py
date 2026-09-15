"""Test API end-to-end + suite di conformità (Step 5 della Skill)."""
from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from .conftest import SAMPLE_PAPER, build_simple_pdf


@pytest.fixture()
def client(vault_root: Path) -> TestClient:
    from app.main import app, state

    state.vault = None
    with TestClient(app) as c:
        yield c
    state.vault = None


def test_health_and_llm_offline(client: TestClient) -> None:
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["llm"]["provider"] == "none"  # nessun modello AI attivo
    assert body["llm"]["configured"] is False


def test_vault_open_initializes_index(client: TestClient, vault_root: Path) -> None:
    r = client.post("/api/v1/vault/open", json={"path": str(vault_root)})
    assert r.status_code == 200
    body = r.json()
    assert body["root"] == str(vault_root)
    assert (vault_root / "_index" / "INDEX.md").is_file()
    assert (vault_root / "_index" / "graph.json").is_file()
    assert (vault_root / "CLAUDE.md").is_file()  # semi dal template
    assert (vault_root / "scripts" / "sandbox_runner.py").is_file()


def _open(client: TestClient, root: Path) -> None:
    r = client.post("/api/v1/vault/open", json={"path": str(root)})
    assert r.status_code == 200


# --- Conformità 1: Test Ingest (PDF → note atomiche, sorgente intatta) ------

def test_conformity_ingest_pdf(client: TestClient, vault_root: Path) -> None:
    _open(client, vault_root)
    pdf = vault_root / "sources" / "papers" / "paper_v1.pdf"
    build_simple_pdf(["Deep Learning Foundations", "Gradients drive training."], pdf)
    before = pdf.read_bytes()

    files = {"file": ("paper_v1.pdf", pdf.read_bytes(), "application/pdf")}
    r = client.post("/api/v1/ingest/file", files=files)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["source_path"] == "sources/papers/paper_v1.pdf"
    assert body["notes_created"], "nessuna nota atomica creata"
    assert body["sources_integrity_ok"] is True
    assert body["index_updated"] is True

    # verifica note atomiche in wiki/concepts con provenienza
    concepts = list((vault_root / "wiki" / "concepts").glob("*.md"))
    assert concepts
    content = concepts[0].read_text(encoding="utf-8")
    assert "sources/papers/paper_v1.pdf" in content
    # sorgente immutata
    assert pdf.read_bytes() == before


# --- Conformità 2: Data Science (CSV → correlazione → sintesi + grafico) ----

def test_conformity_data_science(client: TestClient, vault_root: Path, sample_csv: Path) -> None:
    _open(client, vault_root)
    dst = vault_root / "sources" / "datasets" / "sales.csv"
    dst.write_bytes(sample_csv.read_bytes())
    r = client.post("/api/v1/ingest/file",
                    files={"file": ("sales.csv", dst.read_bytes(), "text/csv")})
    assert r.status_code == 200
    assert r.json()["notes_created"]  # scheda metadati

    code = (
        "import polars as pl\n"
        "corr = df.select(pl.corr('revenue', 'units')).item()\n"
        "print('correlazione', round(corr, 4))\n"
        "import matplotlib.pyplot as plt\n"
        "fig, ax = plt.subplots()\n"
        "ax.scatter(df['units'].to_list(), df['revenue'].to_list())\n"
        "ax.set_xlabel('units'); ax.set_ylabel('revenue')\n"
        "plt.show()\n"
    )
    r = client.post("/api/v1/sandbox/run", json={
        "code": code,
        "task_name": "correlazione_vendite",
        "dataset": "datasets/sales.csv",
        "synthesize": True,
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"], body["stderr"]
    assert "correlazione" in body["stdout"]
    assert body["figures"] and body["figures"][0]["path"].startswith("sources/images/generated/")
    assert (vault_root / body["figures"][0]["path"]).is_file()
    assert body["synthesis_note"]
    synth = vault_root / "wiki" / "synthesis" / body["synthesis_note"]
    assert synth.is_file()
    text = synth.read_text(encoding="utf-8")
    assert "![[sources/images/generated/" in text  # embedding del plot
    assert "correlazione" in text


# --- Conformità 3: Lint (link orfano → rilevato in lint_report.md) ----------

def test_conformity_lint_orphan(client: TestClient, vault_root: Path) -> None:
    _open(client, vault_root)
    p = vault_root / "wiki" / "concepts" / "orfana.md"
    p.write_text(
        "---\n"
        "title: \"Orfana\"\n"
        "type: concept\n"
        "created: 2026-01-01\n"
        "updated: 2026-01-01\n"
        "sources:\n  - \"[[sources/papers/x.pdf]]\"\n"
        "aliases: []\n"
        "tags: []\n"
        "relations:\n  prerequisites: []\n  related: []\n  conflicts_with: []\n"
        "---\n"
        "# Orfana\n\n## Sintesi Esecutiva\n\nX.\n\n"
        "## Formalizzazione & Dettagli\n\nY.\n\n"
        "## Relazioni nel Grafo\n\n- [[ConcettoCheNonEsiste]]\n\n"
        "## Discrepanze & Limiti\n\nNessuno.\n",
        encoding="utf-8",
    )
    (vault_root / "sources" / "papers" / "x.pdf").write_bytes(b"%PDF-1.4 dummy\n")

    r = client.post("/api/v1/lint/run")
    assert r.status_code == 200
    body = r.json()
    assert any(o["target"] == "ConcettoCheNonEsiste" for o in body["orphan_links"])
    report = (vault_root / "_index" / "lint_report.md").read_text(encoding="utf-8")
    assert "ConcettoCheNonEsiste" in report


# --- Endpoint di supporto ----------------------------------------------------

def test_graph_nodes_endpoint(client: TestClient, vault_root: Path) -> None:
    _open(client, vault_root)
    (vault_root / "sources" / "papers" / "a.txt").write_text(SAMPLE_PAPER, encoding="utf-8")
    r = client.post("/api/v1/ingest/file",
                    files={"file": ("a.txt", (vault_root / "sources" / "papers" / "a.txt").read_bytes(), "text/plain")})
    assert r.status_code == 200
    r = client.get("/api/v1/graph/nodes")
    assert r.status_code == 200
    g = r.json()
    assert g["node_count"] >= 3  # doc + concepts + source
    assert g["edge_count"] >= 1
    types = {n["type"] for n in g["nodes"]}
    assert "concept" in types and "source" in types


def test_agent_query_offline(client: TestClient, vault_root: Path) -> None:
    _open(client, vault_root)
    (vault_root / "sources" / "papers" / "a.txt").write_text(SAMPLE_PAPER, encoding="utf-8")
    client.post("/api/v1/ingest/file",
                files={"file": ("a.txt", (vault_root / "sources" / "papers" / "a.txt").read_bytes(), "text/plain")})
    r = client.post("/api/v1/agent/query", json={"question": "Cos'è l'attention mechanism?"})
    assert r.status_code == 200
    body = r.json()
    assert body["provider"].startswith("deterministic")
    assert body["citations"]
    assert "attention" in body["answer_markdown"].casefold()


def test_notes_save_and_validate(client: TestClient, vault_root: Path) -> None:
    _open(client, vault_root)
    valid = (
        "---\n"
        "title: \"Nuova Nota\"\n"
        "type: concept\n"
        "created: 2026-01-01\n"
        "updated: 2026-01-01\n"
        "sources:\n  - \"[[sources/papers/a.txt]]\"\n"
        "aliases: []\n"
        "tags: []\n"
        "relations:\n  prerequisites: []\n  related: []\n  conflicts_with: []\n"
        "---\n"
        "# Nuova Nota\n\n## Sintesi Esecutiva\n\nS.\n\n"
        "## Formalizzazione & Dettagli\n\nD.\n\n"
        "## Relazioni nel Grafo\n\n- Nessuna.\n\n"
        "## Discrepanze & Limiti\n\nNessuna.\n"
    )
    r = client.put("/api/v1/notes/wiki/concepts/nova.md", json={"content": valid})
    assert r.status_code == 200, r.text
    r = client.get("/api/v1/notes/wiki/concepts/nova.md")
    assert r.status_code == 200
    assert r.json()["frontmatter"]["title"] == "Nuova Nota"
    # frontmatter invalido → 422
    r = client.put("/api/v1/notes/wiki/concepts/bad.md", json={"content": "nessun frontmatter"})
    assert r.status_code == 422
    # area non scrivibile
    r = client.put("/api/v1/notes/sources/papers/hack.md", json={"content": valid})
    assert r.status_code == 400


def test_sandbox_cleanup_and_delete_file(client: TestClient, vault_root: Path) -> None:
    """I nuovi endpoint di gestione: cleanup artefatti sandbox + delete file
    rigenerabili. Le sorgenti (non generate) devono restare intatte."""
    _open(client, vault_root)
    scripts = vault_root / "scripts" / "generated"
    scripts.mkdir(parents=True, exist_ok=True)
    (scripts / "task_test.py").write_text("print(1)\n", encoding="utf-8")
    images = vault_root / "sources" / "images" / "generated"
    images.mkdir(parents=True, exist_ok=True)
    (images / "plot_1.png").write_bytes(b"\x89PNG-fake-bytes")
    synth = vault_root / "wiki" / "synthesis"
    synth.mkdir(parents=True, exist_ok=True)
    (synth / "analisi-test.md").write_text(
        "---\ntitle: 'Analisi: test'\ntype: synthesis\ncreated: '2026-01-01'\n"
        "updated: '2026-01-01'\nsources:\n- '[[scripts/generated/task_test.py]]'\n"
        "aliases: []\ntags: []\nrelations:\n  prerequisites: []\n  related: []\n  conflicts_with: []\n---\n"
        "# Analisi: test\n\n## Sintesi Esecutiva\n\n"
        "Esecuzione sandbox `scripts/generated/task_test.py` completata in 1 ms (exit 0).\n",
        encoding="utf-8",
    )
    src = vault_root / "sources" / "papers" / "protected.pdf"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_bytes(b"%PDF-1.4 fake-protected")

    # 1) delete_file rifiuta le sorgenti non generate (immunità)
    r = client.delete("/api/v1/files/sources/papers/protected.pdf")
    assert r.status_code == 400
    assert src.is_file()

    # 2) cleanup rimuove script + figure + sintesi correlate, tocca le sorgenti
    r = client.post("/api/v1/sandbox/cleanup", json={"include_synthesis": True})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["count"] >= 3
    assert not (scripts / "task_test.py").exists()
    assert not (images / "plot_1.png").exists()
    assert not (synth / "analisi-test.md").exists()
    assert src.is_file()

    # 3) delete_file funziona su una nota wiki
    note = vault_root / "wiki" / "entities" / "tmp.md"
    note.write_text("---\ntitle: T\ntype: entity\n---\n# T\n", encoding="utf-8")
    r = client.delete("/api/v1/files/wiki/entities/tmp.md")
    assert r.status_code == 200 and r.json()["deleted"] is True
    assert not note.exists()

    # 4) il grafo non contiene più i nodi eliminati
    g = client.get("/api/v1/graph/nodes").json()
    ids = {n["id"] for n in g["nodes"]}
    assert not any("task_test" in i for i in ids)


def test_ingest_rejects_unknown_extension(client: TestClient, vault_root: Path) -> None:
    _open(client, vault_root)
    r = client.post("/api/v1/ingest/file",
                    files={"file": ("x.exe", b"binary", "application/octet-stream")})
    assert r.status_code == 415


def test_vault_required(client: TestClient) -> None:
    r = client.get("/api/v1/graph/nodes")
    assert r.status_code == 409


def test_file_serving(client: TestClient, vault_root: Path) -> None:
    _open(client, vault_root)
    from PIL import Image

    img = Image.new("RGB", (10, 10), "red")
    p = vault_root / "sources" / "images" / "test.png"
    img.save(p, "PNG")
    r = client.get("/api/v1/files/sources/images/test.png")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
