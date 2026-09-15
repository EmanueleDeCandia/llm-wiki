/**
 * Template di analisi predefiniti per il pannello Sandbox.
 *
 * Ogni template è Python generico: introspecta il DataFrame `df` (polars)
 * e scopre da solo le colonne numeriche/testuali/date, quindi l'utente
 * non deve scrivere né modificare codice. `df` esiste solo se nel form
 * è selezionato un dataset (lo selezioniamo noi al momento dell'uso).
 */
export interface AnalysisTemplate {
  id: string;
  label: string;
  description: string;
  needsDataset: boolean;
  code: string;
}

export const ANALYSIS_TEMPLATES: AnalysisTemplate[] = [
  {
    id: 'anteprima',
    label: '👀 Anteprima + schema',
    description: 'Prime righe, forma e tipi di ogni colonna — il primo passo per conoscere un dataset.',
    needsDataset: true,
    code: `# Anteprima + schema (generico)
print(f"forma: {df.height} righe x {df.width} colonne")
print("\\n— tipi delle colonne —")
for c, t in df.schema.items():
    print(f"  {c}: {t}")
print("\\n— prime 10 righe —")
print(df.head(10))
`,
  },
  {
    id: 'riassunto',
    label: '📊 Riassunto statistico',
    description: 'Min/max/mediana/media/deviazione delle colonne numeriche + valori mancanti per colonna.',
    needsDataset: true,
    code: `# Riassunto statistico (generico)
import polars as pl
num_cols = [c for c, t in df.schema.items() if t.is_numeric()]
print(f"forma: {df.height} righe x {df.width} colonne")
print("\\n— valori mancanti per colonna —")
for c in df.columns:
    n = df.filter(pl.col(c).is_null()).height
    print(f"  {c}: {n} ({100.0 * n / df.height:.1f}%)")
if num_cols:
    print("\\n— statistiche colonne numeriche —")
    print(df.select(num_cols).describe())
else:
    print("Nessuna colonna numerica nel dataset.")
`,
  },
  {
    id: 'correlazione',
    label: '🔗 Correlazione + scatter',
    description: 'Matrice delle correlazioni tra TUTTE le colonne numeriche + scatter con la coppia più forte.',
    needsDataset: true,
    code: `# Correlazione + scatter (generico: trova da solo le coppie)
import polars as pl
import matplotlib.pyplot as plt
num_cols = [c for c, t in df.schema.items() if t.is_numeric()]
print(f"colonne numeriche: {num_cols}")
if len(num_cols) < 2:
    print("Servono almeno 2 colonne numeriche per la correlazione.")
else:
    clean = df.select(num_cols).drop_nulls()
    print(f"\\nosservazioni senza valori mancanti: {clean.height}")
    print("\\n— matrice delle correlazioni —")
    print(clean.corr())
    best_x, best_y, best_r = None, None, None
    for i in range(len(num_cols)):
        for j in range(i + 1, len(num_cols)):
            r = df.select(pl.corr(num_cols[i], num_cols[j])).item()
            if r is None:
                continue
            print(f"correlazione {num_cols[i]} vs {num_cols[j]}: {round(r, 4)}")
            if best_r is None or abs(r) > abs(best_r):
                best_x, best_y, best_r = num_cols[i], num_cols[j], r
    if best_x is None:
        print("Nessuna correlazione calcolabile (colonne con solo null?).")
    else:
        pair = df.select([best_x, best_y]).drop_nulls()  # null rimossi a coppia
        fig, ax = plt.subplots(figsize=(6, 4))
        ax.scatter(pair[best_x].to_list(), pair[best_y].to_list(), alpha=0.7)
        ax.set_title(f"{best_x} vs {best_y}  (r = {best_r:.3f}, n={pair.height})")
        ax.set_xlabel(best_x)
        ax.set_ylabel(best_y)
        plt.tight_layout()
        plt.show()
`,
  },
  {
    id: 'distribuzioni',
    label: '📈 Distribuzioni (istogrammi)',
    description: 'Un istogramma per ogni colonna numerica: vedi forma, skew e valori anomali.',
    needsDataset: true,
    code: `# Distribuzioni (generico: un istogramma per colonna numerica)
import matplotlib.pyplot as plt
num_cols = [c for c, t in df.schema.items() if t.is_numeric()]
if not num_cols:
    print("Nessuna colonna numerica nel dataset.")
else:
    k = min(len(num_cols), 4)
    fig, axes = plt.subplots(1, k, figsize=(5 * k, 3.5), squeeze=False)
    for ax, c in zip(axes[0], num_cols[:k]):
        ax.hist(df[c].drop_nulls().to_list(), bins=25, alpha=0.8)
        ax.set_title(c)
    plt.tight_layout()
    plt.show()
    print(f"istogrammi salvati per: {num_cols[:k]}")
`,
  },
  {
    id: 'groupby',
    label: '🧮 Agruppa e media (bar chart)',
    description: 'Media di una colonna numerica raggruppata per categoria (top 15) + grafico a barre.',
    needsDataset: true,
    code: `# Group-by + media (generico: sceglie da solo la colonna categoriale)
import polars as pl
import matplotlib.pyplot as plt
num_cols = [c for c, t in df.schema.items() if t.is_numeric()]
cands = []
for c, t in df.schema.items():
    if str(t) in ("String", "Utf8"):
        u = df[c].drop_nulls().n_unique()
        if 2 <= u <= max(10, df.height // 4):  # colonne "categoria" (poche distinte non-null)
            cands.append((u, c))
if not cands or not num_cols:
    print("Nessuna combinazione colonna testuale-categorica x numerica trovata.")
else:
    g = min(cands)[1]  # la con meno valori distinti
    v = num_cols[0]
    agg = (
        df.group_by(g)
        .agg(pl.col(v).mean().alias(f"{v}_media"), pl.count().alias("n"))
        .filter(pl.col(g).is_not_null())  # polars raggruppa anche i null: li scartiamo
        .drop_nulls(subset=[f"{v}_media"])
        .sort(f"{v}_media", descending=True)
        .head(15)
    )
    if agg.height == 0:
        print(f"nessun gruppo con valori validi in '{v}'")
    else:
        print(f"media di '{v}' raggrupata per '{g}' (top 15):")
        print(agg)
        fig, ax = plt.subplots(figsize=(7, 4))
        ax.bar(agg[g].to_list(), agg[f"{v}_media"].to_list())
        ax.set_title(f"{v} (media) per {g}")
        ax.set_ylabel(f"{v} (media)")
        plt.xticks(rotation=45, ha="right")
        plt.tight_layout()
        plt.show()
`,
  },
  {
    id: 'temporale',
    label: '📅 Andamento temporale',
    description: "Se c'è una colonna data: linea temporale della prima colonna numerica.",
    needsDataset: true,
    code: `# Andamento temporale (generico: trova da solo la colonna data)
import polars as pl
import matplotlib.pyplot as plt
date_cols = [c for c, t in df.schema.items() if str(t).lower().startswith(("date", "datetime"))]
if not date_cols:
    # molte fonti conservano le date come stringhe YYYY-MM-DD: prova a convertirle
    for c, t in df.schema.items():
        if str(t) not in ("String", "Utf8"):
            continue
        non_null = df[c].drop_nulls()
        if len(non_null) == 0:
            continue
        if non_null.to_frame().filter(~pl.col(c).str.contains(r"^\\d{4}-\\d{2}-\\d{2}$")).height == 0:
            df = df.with_columns(pl.col(c).str.to_date().alias(c))
            date_cols = [c]
            print(f"colonna data convertita da testo: '{c}'")
            break
num_cols = [c for c, t in df.schema.items() if t.is_numeric()]
if not date_cols or not num_cols:
    print("Nessuna colonna data rilevata (o nessuna numerica).")
else:
    d, v = date_cols[0], num_cols[0]
    s = df.drop_nulls(subset=[d, v]).sort(d)
    print(f"serie: '{v}' su '{d}' — da {s[d].min()} a {s[d].max()} ({s.height} osservazioni)")
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(s[d].to_list(), s[v].to_list())
    ax.set_title(f"{v} nel tempo")
    ax.set_xlabel(d)
    ax.set_ylabel(v)
    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()
    plt.show()
`,
  },
  {
    id: 'qualita',
    label: '🩺 Qualità dati (mancanti + duplicati)',
    description: 'Conteggio missing per colonna, percentuale totale e righe duplicate — prima di analizzare.',
    needsDataset: true,
    code: `# Qualità dati (generico)
import polars as pl
total_cells = df.height * df.width
nulls = {c: df.filter(pl.col(c).is_null()).height for c in df.columns}
print(f"righe: {df.height} · colonne: {df.width} · celle totali: {total_cells}")
print("\\n— valori mancanti —")
for c, n in nulls.items():
    print(f"  {c}: {n} ({100.0 * n / df.height:.1f}%)")
tot = sum(nulls.values())
print(f"totale mancanti: {tot} ({100.0 * tot / total_cells:.1f}% delle celle)")
dup = df.height - df.unique().height
print(f"righe duplicate: {dup}")
`,
  },
];
