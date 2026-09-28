"""
Konsensus 4 algoritma dengan lift sebagai metrik utama.

Cara kerja:
* Setiap aturan (Jika membeli X maka cenderung membeli Y) dari keempat algoritma digabung.
* Suara = berapa algoritma yang menemukan aturan tersebut (1 sampai 4).
* Skor Konsensus = Lift x (Suara / 4).
  Lift tetap menjadi penentu utama, tetapi aturan yang hanya didukung sedikit algoritma
  otomatis tertahan peringkatnya.
* Aturan kemudian dirangkum menjadi kandidat BUNDLE (gabungan produk tanpa arah).
"""

from __future__ import annotations

import pandas as pd

ALGOS = ["Apriori", "FP Growth", "AIS", "ARN"]


def fmt_set(s) -> str:
    return " + ".join(sorted(s))


def consensus_rules(results: dict) -> pd.DataFrame:
    frames = []
    for name in ALGOS:
        r = results[name]["rules"]
        if r.empty:
            continue
        r = r.copy()
        r["algoritma"] = name
        frames.append(r)
    if not frames:
        return pd.DataFrame()
    allr = pd.concat(frames, ignore_index=True)
    allr["jika"] = allr["antecedent"].map(fmt_set)
    allr["maka"] = allr["consequent"].map(fmt_set)

    metric_cols = ["jumlah_keranjang", "support", "confidence", "lift", "leverage", "conviction"]
    agg = allr.groupby(["jika", "maka"], as_index=False).agg(
        antecedent=("antecedent", "first"),
        consequent=("consequent", "first"),
        **{c: (c, "mean") for c in metric_cols},
        suara=("algoritma", "nunique"),
    )
    found = allr.groupby(["jika", "maka"])["algoritma"].apply(set)
    for name in ALGOS:
        agg[name] = [name in found[(j, m)] for j, m in zip(agg["jika"], agg["maka"])]
    if "p_value" in allr.columns:
        pv = allr.dropna(subset=["p_value"]).groupby(["jika", "maka"])["p_value"].min()
        agg["p_value"] = [pv.get((j, m)) for j, m in zip(agg["jika"], agg["maka"])]

    agg["skor_konsensus"] = agg["lift"] * agg["suara"] / len(ALGOS)
    agg["tingkat_kesepakatan"] = agg["suara"].map(
        {4: "Konsensus penuh (4/4)", 3: "Mayoritas (3/4)", 2: "Sebagian (2/4)", 1: "Tunggal (1/4)"}
    )
    return agg.sort_values(["skor_konsensus", "confidence"], ascending=False).reset_index(drop=True)


def _priority(votes: int, lift: float) -> str:
    if votes >= 3 and lift >= 2:
        return "Prioritas Tinggi"
    if (votes >= 3 and lift >= 1.2) or (votes >= 2 and lift >= 2):
        return "Prioritas Sedang"
    return "Pantau"


def bundle_table(cons: pd.DataFrame, unit_price: dict, n_tx: int) -> pd.DataFrame:
    """Meringkas aturan menjadi kandidat bundle (himpunan produk tanpa arah)."""
    if cons.empty:
        return pd.DataFrame()
    c = cons.copy()
    c["bundle_set"] = [a | b for a, b in zip(c["antecedent"], c["consequent"])]
    c["bundle"] = c["bundle_set"].map(fmt_set)
    c = c.sort_values(["skor_konsensus", "confidence"], ascending=False)

    rows = []
    for bundle, g in c.groupby("bundle", sort=False):
        best = g.iloc[0]
        items = sorted(best["bundle_set"])
        harga = sum(unit_price.get(i, 0) for i in items)
        rows.append({
            "bundle": bundle,
            "jumlah_produk": len(items),
            "arah_terkuat": f"{best['jika']} → {best['maka']}",
            "lift": best["lift"],
            "confidence": best["confidence"],
            "jumlah_keranjang": int(round(best["jumlah_keranjang"])),
            "support": best["support"],
            "suara": int(g["suara"].max()),
            "skor_konsensus": g["skor_konsensus"].max(),
            "harga_normal_gabungan": harga if harga > 0 else None,
            "_ante": best["antecedent"],
            "_cons": best["consequent"],
        })
    out = pd.DataFrame(rows)
    out["prioritas"] = [_priority(v, l) for v, l in zip(out["suara"], out["lift"])]
    out = out.sort_values(["skor_konsensus", "confidence"], ascending=False).reset_index(drop=True)
    out.index = out.index + 1
    return out


def narrative(bundles: pd.DataFrame, top: int = 3) -> list[str]:
    """Kalimat rekomendasi siap baca untuk tim bisnis."""
    lines = []
    for _, r in bundles.head(top).iterrows():
        ante, cons = fmt_set(r["_ante"]), fmt_set(r["_cons"])
        lines.append(
            f"**{r['bundle']}** ({r['prioritas']}). Customer yang membeli **{ante}** "
            f"{r['lift']:.2f}x lebih mungkin juga membeli **{cons}** dibanding rata rata; "
            f"{r['confidence']:.0%} keranjang berisi {ante} juga memuat {cons}. "
            f"Terjadi pada {r['jumlah_keranjang']} keranjang, disepakati {r['suara']} dari 4 algoritma."
        )
    return lines
