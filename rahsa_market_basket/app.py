"""
Rahsa Nusantara · Market Basket Analysis
Aplikasi Streamlit untuk menemukan produk yang dibeli bersamaan (satu Nomor PO = satu keranjang)
memakai 4 algoritma (Apriori, FP Growth, AIS, ARN) yang disatukan lewat konsensus berbasis lift.
"""

from __future__ import annotations

import math

import networkx as nx
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from mba import algorithms as A
from mba import consensus as C
from mba import data as D

st.set_page_config(page_title="Rahsa Nusantara · Market Basket", page_icon="🧺", layout="wide")

HIJAU, EMAS, ABU, TANAH = "#2F6B4F", "#C9A227", "#9AA5A0", "#8C5A3C"
WARNA_PRIORITAS = {"Prioritas Tinggi": HIJAU, "Prioritas Sedang": EMAS, "Pantau": ABU}
PALET_KLASTER = ["#2F6B4F", "#C9A227", "#8C5A3C", "#4F7CAC", "#B5543C", "#6B8E23", "#7E5A9B", "#3E8E8E"]
DEFAULT_MIN_COUNT = {"Harian": 2, "Mingguan": 3, "Bulanan": 5, "Seluruh periode": 20}
ALGO_INFO = {
    "Apriori": "Mencari kombinasi produk secara bertahap (2 produk, lalu 3 produk, dst). "
               "Kandidat yang salah satu subsetnya tidak sering muncul langsung dibuang (prune).",
    "FP Growth": "Memadatkan semua keranjang ke dalam struktur pohon (FP Tree), lalu menambang pola "
                 "tanpa membuat kandidat. Hasil itemset identik dengan Apriori namun jauh lebih cepat pada data besar.",
    "AIS": "Algoritma asosiasi pertama (Agrawal, Imielinski, Swami 1993). Kandidat dibentuk langsung saat membaca "
           "tiap keranjang. Sesuai rancangan aslinya, aturan hanya memiliki satu produk di sisi hasil.",
    "ARN": "Association Rule Network. Aturan satu produk hasil diuji signifikansinya (uji hipergeometrik), "
           "hanya asosiasi positif (lift di atas 1) yang lolos, lalu dirangkai menjadi jaringan produk "
           "untuk melihat produk penggerak (hub) dan klaster produk.",
}


def rp(x) -> str:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return ""
    return "Rp " + f"{x:,.0f}".replace(",", ".")


def rp_ringkas(x) -> str:
    """Format singkat untuk kartu KPI: Rp 287,7 jt / Rp 2,15 M."""
    if not x:
        return "Rp 0"
    if x >= 1e9:
        return "Rp " + f"{x / 1e9:.2f}".replace(".", ",") + " M"
    if x >= 1e6:
        return "Rp " + f"{x / 1e6:.1f}".replace(".", ",") + " jt"
    return rp(x)


# ===========================================================================
# Pemuatan data
# ===========================================================================
def secrets_ready() -> bool:
    try:
        return "gcp_service_account" in st.secrets and "gsheet" in st.secrets
    except Exception:
        return False


@st.cache_data(ttl=600, show_spinner="Mengambil data dari Google Sheets...")
def load_gsheet(spreadsheet: str, worksheet: str | None) -> pd.DataFrame:
    raw = D.read_google_sheet(st.secrets["gcp_service_account"], spreadsheet, worksheet)
    return D.add_periods(D.clean(raw))


@st.cache_data(show_spinner="Membaca file...")
def load_file(file_bytes: bytes, name: str) -> pd.DataFrame:
    import io

    buf = io.BytesIO(file_bytes)
    buf.name = name
    return D.add_periods(D.clean(D.read_uploaded(buf)))


@st.cache_data(show_spinner="Menjalankan Apriori, FP Growth, AIS dan ARN...")
def analyse(_df: pd.DataFrame, key: tuple, item_col: str, mode: str,
            min_count: int, max_len: int, min_conf: float, min_lift: float, alpha: float):
    tx = D.build_transactions(_df, item_col, mode)
    T = list(tx.values)
    res = A.run_all(T, min_count, max_len, min_conf, min_lift, alpha)
    cons = C.consensus_rules(res)
    return tx, res, cons


# ===========================================================================
# Sidebar
# ===========================================================================
st.sidebar.markdown("## 🧺 Rahsa Nusantara")
st.sidebar.caption("Market Basket Analysis untuk perancangan bundle")

df = None
source_label = ""
if secrets_ready():
    cfg = st.secrets["gsheet"]
    try:
        df = load_gsheet(cfg["spreadsheet"], cfg.get("worksheet") or None)
        source_label = "Google Sheets"
        st.sidebar.success("Terhubung ke Google Sheets", icon="✅")
    except Exception as e:  # tampilkan pesan yang jelas bila koneksi gagal
        st.sidebar.error(f"Gagal membaca Google Sheets: {e}")
    if st.sidebar.button("🔄 Muat ulang data", help="Ambil data terbaru dari Google Sheets"):
        st.cache_data.clear()
        st.rerun()
    with st.sidebar.expander("Pakai file lain (opsional)"):
        up = st.file_uploader("Upload Excel atau CSV", type=["xlsx", "xls", "csv"], key="up_override")
        if up is not None:
            df = load_file(up.getvalue(), up.name)
            source_label = f"File: {up.name}"
else:
    st.sidebar.info("Google Sheets belum dikonfigurasi. Sementara gunakan upload file.", icon="ℹ️")
    up = st.sidebar.file_uploader("Upload Excel atau CSV", type=["xlsx", "xls", "csv"])
    if up is not None:
        df = load_file(up.getvalue(), up.name)
        source_label = f"File: {up.name}"

if df is None or df.empty:
    st.title("Market Basket Analysis · Rahsa Nusantara")
    st.info("Hubungkan Google Sheets lewat menu Secrets atau upload file penjualan di sidebar untuk memulai.")
    st.stop()

st.sidebar.divider()
st.sidebar.markdown("### Filter")
levels = {k: v for k, v in D.ITEM_LEVELS.items() if k in df.columns}
item_col = st.sidebar.selectbox("Level produk", list(levels), format_func=levels.get,
                                help="Satuan produk yang dianalisis di dalam keranjang.")
mode_label = st.sidebar.radio(
    "Perlakuan bundle yang sudah ada",
    ["Perilaku organik", "Semua produk"],
    help=("Perilaku organik: listing bundle existing (satu SKU berisi 2 produk atau lebih) dihitung sebagai satu item "
          "sehingga yang terbaca adalah kombinasi yang dipilih customer sendiri. "
          "Semua produk: listing bundle dipecah menjadi produk penyusunnya."),
)
mode = "organik" if mode_label == "Perilaku organik" else "komponen"

if "Channel" in df.columns:
    channels = sorted(df["Channel"].dropna().unique())
    sel_ch = st.sidebar.multiselect("Channel", channels, default=channels)
    if not sel_ch:
        st.warning("Pilih minimal satu channel.")
        st.stop()
    df = df[df["Channel"].isin(sel_ch)]

st.sidebar.markdown("### Timeframe")
tf = st.sidebar.radio("Jenis analisa", ["Harian", "Mingguan", "Bulanan", "Seluruh periode"], index=2)
if tf == "Seluruh periode":
    dfp = df
    period_label = (f"{D.label_period(df['Tanggal'].min(), 'Harian')} s/d "
                    f"{D.label_period(df['Tanggal'].max(), 'Harian')}")
    period_key = "all"
else:
    pc = D.PERIOD_COL[tf]
    periods = sorted(df[pc].dropna().unique(), reverse=True)
    if not periods:
        st.warning("Tidak ada data untuk filter yang dipilih.")
        st.stop()
    sel_p = st.sidebar.selectbox("Pilih periode", periods,
                                 format_func=lambda p: D.label_period(pd.Timestamp(p), tf))
    dfp = df[df[pc] == sel_p]
    period_label = D.label_period(pd.Timestamp(sel_p), tf)
    period_key = str(sel_p)

with st.sidebar.expander("⚙️ Parameter algoritma", expanded=False):
    min_count = st.number_input(
        "Minimal keranjang (support)", min_value=1, value=DEFAULT_MIN_COUNT[tf], step=1, key=f"mc_{tf}",
        help="Kombinasi produk harus muncul minimal sebanyak ini dalam periode terpilih.")
    min_conf = st.slider("Minimal confidence", 0.0, 1.0, 0.10, 0.01)
    min_lift = st.slider("Minimal lift", 1.0, 5.0, 1.0, 0.1,
                         help="Lift di atas 1 berarti produk dibeli bersamaan lebih sering dari kebetulan.")
    max_len = st.slider("Maksimal produk per bundle", 2, 4, 3)
    alpha = st.select_slider("Tingkat signifikansi ARN", [0.01, 0.05, 0.10], value=0.05)

st.sidebar.caption(f"Sumber: {source_label}")

# ===========================================================================
# Analisa
# ===========================================================================
key = (source_label, len(df), str(df["Tanggal"].max()),
       float(df["Value_Sales"].sum()) if "Value_Sales" in df.columns else 0.0, tuple(sorted(df["Channel"].unique())) if "Channel" in df.columns else (),
       tf, period_key)
tx, res, cons = analyse(dfp, key, item_col, mode, int(min_count), max_len, min_conf, min_lift, alpha)
n_tx = len(tx)
prices = D.unit_prices(df, item_col)
bundles = C.bundle_table(cons, prices, n_tx)

st.title("Market Basket Analysis · Rahsa Nusantara")
st.caption(f"Analisa **{tf.lower()}** · periode **{period_label}** · level **{levels[item_col]}** · "
           f"mode **{mode_label.lower()}**")

sizes = tx.map(len)
multi = int((sizes > 1).sum())
k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Total keranjang (PO)", f"{n_tx:,}".replace(",", "."))
k2.metric("Keranjang multi produk", f"{multi:,}".replace(",", "."),
          f"{multi / n_tx:.0%} dari total" if n_tx else None, delta_color="off")
k3.metric("Rata rata produk / keranjang", f"{sizes.mean():.2f}".replace(".", ",") if n_tx else "0")
k4.metric("Nilai penjualan", rp_ringkas(dfp["Value_Sales"].sum()) if "Value_Sales" in dfp.columns else "",
          help=rp(dfp["Value_Sales"].sum()) if "Value_Sales" in dfp.columns else None)
k5.metric("Kandidat bundle", len(bundles))

if multi < 30:
    st.warning(f"Hanya ada {multi} keranjang multi produk pada periode ini. Hasil bersifat indikatif; "
               "gunakan timeframe lebih panjang untuk keputusan bundle.", icon="⚠️")

tabs = st.tabs(["🎁 Rekomendasi Bundle", "🤝 Konsensus Aturan", "🔬 Detail Algoritma",
                "🕸️ Jaringan ARN", "📈 Tren Antar Periode", "🧺 Profil Keranjang", "📘 Metodologi"])

# 1. Rekomendasi bundle =======================================================
with tabs[0]:
    if bundles.empty:
        st.info("Belum ada kombinasi produk yang lolos parameter. Coba turunkan minimal keranjang atau confidence.")
    else:
        st.subheader("Top rekomendasi")
        for line in C.narrative(bundles, top=3):
            st.markdown(f"🎯 {line}")

        top = bundles.head(15).iloc[::-1]
        fig = px.bar(top, x="lift", y="bundle", orientation="h", color="prioritas",
                     color_discrete_map=WARNA_PRIORITAS,
                     hover_data={"arah_terkuat": True, "confidence": ":.1%", "jumlah_keranjang": True,
                                 "suara": True, "bundle": False},
                     labels={"lift": "Lift", "bundle": "", "prioritas": "Prioritas"})
        fig.add_vline(x=1, line_dash="dot", line_color=ABU)
        fig.update_layout(height=max(360, 28 * len(top) + 90), margin=dict(l=10, r=10, t=90, b=10),
                          legend=dict(orientation="h", y=1.02, yanchor="bottom", x=0, title_text=""),
                          title=dict(text="Lift 15 kandidat bundle teratas", y=0.98, yanchor="top"),
                          yaxis=dict(categoryorder="array", categoryarray=list(top["bundle"])))
        st.plotly_chart(fig)

        show = bundles.drop(columns=["_ante", "_cons"]).copy()
        st.dataframe(
            show,
            column_config={
                "bundle": "Bundle",
                "jumlah_produk": st.column_config.NumberColumn("Produk", format="%d"),
                "arah_terkuat": "Arah terkuat (jika → maka)",
                "lift": st.column_config.NumberColumn("Lift", format="%.2f"),
                "confidence": st.column_config.NumberColumn("Confidence", format="percent"),
                "jumlah_keranjang": st.column_config.NumberColumn("Keranjang", format="%d"),
                "support": st.column_config.NumberColumn("Support", format="percent"),
                "suara": st.column_config.NumberColumn("Suara algoritma", format="%d / 4"),
                "skor_konsensus": st.column_config.ProgressColumn(
                    "Skor konsensus", format="%.2f", min_value=0,
                    max_value=float(show["skor_konsensus"].max())),
                "harga_normal_gabungan": st.column_config.NumberColumn("Harga normal gabungan", format="Rp %.0f"),
                "prioritas": "Prioritas",
            },
        )
        st.download_button("⬇️ Unduh rekomendasi bundle (CSV)", show.to_csv(index_label="peringkat").encode(),
                           file_name=f"bundle_{tf.lower()}_{period_key[:10]}.csv", mime="text/csv")
        st.caption("Harga normal gabungan = jumlah harga jual rata rata per unit tiap produk "
                   "(Value_Sales dibagi Jumlah) sebagai acuan menentukan harga bundle.")

# 2. Konsensus aturan =========================================================
with tabs[1]:
    if cons.empty:
        st.info("Tidak ada aturan yang lolos parameter.")
    else:
        min_votes = st.segmented_control("Tampilkan aturan dengan suara minimal", [1, 2, 3, 4], default=1,
                                         format_func=lambda v: f"{v} dari 4")
        vc = cons["suara"].value_counts().reindex([4, 3, 2, 1], fill_value=0)
        c1, c2, c3, c4 = st.columns(4)
        for col, v in zip([c1, c2, c3, c4], [4, 3, 2, 1]):
            col.metric(f"Disepakati {v} algoritma", int(vc[v]))
        view = cons[cons["suara"] >= (min_votes or 1)].copy()
        cols = ["jika", "maka", "lift", "confidence", "jumlah_keranjang", "support", "suara",
                "skor_konsensus", *C.ALGOS]
        if "p_value" in view.columns:
            cols.append("p_value")
        st.dataframe(
            view[cols],
            hide_index=True,
            column_config={
                "jika": "Jika membeli", "maka": "Cenderung membeli",
                "lift": st.column_config.NumberColumn("Lift", format="%.2f"),
                "confidence": st.column_config.NumberColumn("Confidence", format="percent"),
                "jumlah_keranjang": st.column_config.NumberColumn("Keranjang", format="%d"),
                "support": st.column_config.NumberColumn("Support", format="percent"),
                "suara": st.column_config.NumberColumn("Suara", format="%d / 4"),
                "skor_konsensus": st.column_config.NumberColumn("Skor konsensus", format="%.2f"),
                **{a: st.column_config.CheckboxColumn(a) for a in C.ALGOS},
                "p_value": st.column_config.NumberColumn("p value (ARN)", format="%.4f"),
            },
        )
        st.download_button("⬇️ Unduh semua aturan (CSV)", view[cols].to_csv(index=False).encode(),
                           file_name=f"aturan_konsensus_{tf.lower()}_{period_key[:10]}.csv", mime="text/csv")

# 3. Detail algoritma =========================================================
with tabs[2]:
    summary = pd.DataFrame({
        "Algoritma": C.ALGOS,
        "Itemset frequent": [len(res[a]["itemsets"]) for a in C.ALGOS],
        "Aturan lolos filter": [len(res[a]["rules"]) for a in C.ALGOS],
        "Lift tertinggi": [res[a]["rules"]["lift"].max() if len(res[a]["rules"]) else None for a in C.ALGOS],
        "Lift rata rata": [res[a]["rules"]["lift"].mean() if len(res[a]["rules"]) else None for a in C.ALGOS],
    })
    st.dataframe(summary, hide_index=True,
                 column_config={"Lift tertinggi": st.column_config.NumberColumn(format="%.2f"),
                                "Lift rata rata": st.column_config.NumberColumn(format="%.2f")})
    same = len({frozenset(res[a]["itemsets"].items()) for a in C.ALGOS}) == 1
    if same:
        st.success("Validasi: keempat algoritma menghasilkan itemset frequent yang identik, "
                   "artinya implementasi konsisten. Perbedaan muncul di tahap pembentukan dan penyaringan aturan.",
                   icon="✅")

    keys = {a: set(zip(res[a]["rules"]["antecedent"], res[a]["rules"]["consequent"])) for a in C.ALGOS}
    mat = [[(len(keys[a] & keys[b]) / len(keys[a] | keys[b])) if (keys[a] | keys[b]) else 0
            for b in C.ALGOS] for a in C.ALGOS]
    hm = px.imshow(mat, x=C.ALGOS, y=C.ALGOS, text_auto=".0%", zmin=0, zmax=1,
                   color_continuous_scale=["#F3F1EA", HIJAU], aspect="auto",
                   title="Kemiripan himpunan aturan antar algoritma (Jaccard)")
    hm.update_layout(height=360, margin=dict(l=10, r=10, t=50, b=10), coloraxis_showscale=False)
    st.plotly_chart(hm)

    algo = st.segmented_control("Lihat hasil algoritma", C.ALGOS, default="Apriori")
    algo = algo or "Apriori"
    st.markdown(f"**{algo}.** {ALGO_INFO[algo]}")
    r = res[algo]["rules"].copy()
    if r.empty:
        st.info("Tidak ada aturan yang lolos parameter.")
    else:
        r.insert(0, "jika", r.pop("antecedent").map(C.fmt_set))
        r.insert(1, "maka", r.pop("consequent").map(C.fmt_set))
        st.dataframe(r, hide_index=True, column_config={
            "jika": "Jika membeli", "maka": "Cenderung membeli",
            "lift": st.column_config.NumberColumn("Lift", format="%.2f"),
            "confidence": st.column_config.NumberColumn("Confidence", format="percent"),
            "support": st.column_config.NumberColumn("Support", format="percent"),
            "jumlah_keranjang": st.column_config.NumberColumn("Keranjang", format="%d"),
            "leverage": st.column_config.NumberColumn("Leverage", format="%.4f"),
            "conviction": st.column_config.NumberColumn("Conviction", format="%.2f"),
            "p_value": st.column_config.NumberColumn("p value", format="%.4f"),
        })

# 4. Jaringan ARN =============================================================
with tabs[3]:
    item_sup = {next(iter(s)): c for s, c in res["ARN"]["itemsets"].items() if len(s) == 1}
    g = A.build_arn_graph(res["ARN"]["rules"], item_sup)
    hubs, clusters = A.arn_network_summary(g)
    if g.number_of_edges() == 0:
        st.info("Jaringan ARN kosong untuk parameter ini.")
    else:
        pos = nx.spring_layout(g.to_undirected(), seed=7, k=1.2 / math.sqrt(max(g.number_of_nodes(), 1)))
        cl = dict(zip(hubs["produk"], hubs["klaster"]))
        prank = dict(zip(hubs["produk"], hubs["pagerank"]))
        ex, ey = [], []
        for u, v in g.edges:
            ex += [pos[u][0], pos[v][0], None]
            ey += [pos[u][1], pos[v][1], None]
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=ex, y=ey, mode="lines", line=dict(color="#C8C8C0", width=1),
                                 hoverinfo="skip", showlegend=False))
        ann = []
        for u, v, d in g.edges(data=True):
            ann.append(dict(ax=pos[u][0], ay=pos[u][1], x=pos[v][0], y=pos[v][1], xref="x", yref="y",
                            axref="x", ayref="y", showarrow=True, arrowhead=2, arrowsize=1,
                            arrowwidth=max(1, min(d["lift"] / 2, 4)), arrowcolor="rgba(120,120,110,0.45)",
                            standoff=12))
        pr_max = max(prank.values())
        nodes = list(g.nodes)
        fig.add_trace(go.Scatter(
            x=[pos[n][0] for n in nodes], y=[pos[n][1] for n in nodes], mode="markers+text",
            text=nodes, textposition="top center",
            marker=dict(size=[16 + 34 * prank[n] / pr_max for n in nodes],
                        color=[PALET_KLASTER[(cl.get(n, 1) - 1) % len(PALET_KLASTER)] for n in nodes],
                        line=dict(color="white", width=1.5)),
            hovertext=[f"{n}<br>PageRank {prank[n]:.3f}<br>Klaster {cl.get(n)}<br>"
                       f"Dibeli di {g.nodes[n].get('support', 0)} keranjang" for n in nodes],
            hoverinfo="text", showlegend=False))
        fig.update_layout(annotations=ann, height=560, margin=dict(l=10, r=10, t=40, b=10),
                          xaxis=dict(visible=False), yaxis=dict(visible=False),
                          title="Jaringan aturan (panah: jika → maka, tebal panah mengikuti lift)")
        st.plotly_chart(fig)

        c1, c2 = st.columns([1, 1])
        with c1:
            st.markdown("**Produk penggerak (hub)**")
            st.caption("PageRank tinggi = produk yang paling sering menjadi tujuan asosiasi. "
                       "Cocok dijadikan produk jangkar (anchor) dalam bundle.")
            st.dataframe(hubs, hide_index=True, column_config={
                "produk": "Produk", "pagerank": st.column_config.NumberColumn("PageRank", format="%.3f"),
                "masuk": "Panah masuk", "keluar": "Panah keluar", "klaster": "Klaster"})
        with c2:
            st.markdown("**Klaster produk**")
            st.caption("Kelompok produk yang saling terhubung kuat. Kandidat bundle tematik atau paket hemat.")
            for i, c in enumerate(clusters, 1):
                st.markdown(f"Klaster {i}: " + " · ".join(f"`{x}`" for x in c))

# 5. Tren antar periode =======================================================
with tabs[4]:
    gran = "Bulanan" if tf == "Seluruh periode" else tf
    last_n = {"Harian": 30, "Mingguan": 16, "Bulanan": 12}[gran]
    st.caption(f"Lift arah terkuat dari 10 bundle teratas pada tiap periode {gran.lower()} "
               f"({last_n} periode terakhir, dengan filter channel dan mode yang sama). "
               "Sel kosong berarti kombinasi tidak muncul pada periode tersebut.")
    if bundles.empty:
        st.info("Belum ada bundle untuk dilacak.")
    else:
        pcol = D.PERIOD_COL[gran]
        tx_all = D.build_transactions(df, item_col, mode)
        po_period = df.groupby("Nomor_PO")[pcol].first()
        periods_all = sorted(po_period.unique())[-last_n:]
        topb = bundles.head(10)
        rows = []
        for p in periods_all:
            T = tx_all[po_period.reindex(tx_all.index) == p]
            n = len(T)
            for _, b in topb.iterrows():
                a, c = b["_ante"], b["_cons"]
                ca = sum(1 for t in T if a <= t)
                cc = sum(1 for t in T if c <= t)
                cab = sum(1 for t in T if (a | c) <= t)
                lift = (cab / ca) / (cc / n) if ca and cc and cab else None
                rows.append({"periode": D.label_period(pd.Timestamp(p), gran), "bundle": b["bundle"],
                             "lift": lift, "keranjang": cab})
        tr = pd.DataFrame(rows)
        order = [D.label_period(pd.Timestamp(p), gran) for p in periods_all]
        piv = tr.pivot(index="bundle", columns="periode", values="lift").reindex(columns=order) \
                .reindex(topb["bundle"])
        cnt = tr.pivot(index="bundle", columns="periode", values="keranjang").reindex(columns=order) \
                .reindex(topb["bundle"])
        fig = go.Figure(go.Heatmap(
            z=piv.values, x=[o.split(" · ")[0] for o in order], y=piv.index,
            colorscale=[[0, "#F3F1EA"], [0.5, EMAS], [1, HIJAU]], zmin=1,
            customdata=cnt.values, hovertemplate="%{y}<br>%{x}<br>Lift %{z:.2f}<br>%{customdata} keranjang<extra></extra>",
            colorbar=dict(title="Lift")))
        fig.update_layout(height=80 + 36 * len(piv), margin=dict(l=10, r=10, t=30, b=10),
                          yaxis=dict(autorange="reversed"))
        st.plotly_chart(fig)
        stab = (piv.notna().sum(axis=1) / len(order)).rename("konsistensi")
        st.dataframe(pd.DataFrame({"Muncul di periode": stab}).style.format("{:.0%}"))
        st.caption("Bundle yang muncul konsisten di banyak periode lebih aman dijadikan bundle permanen; "
                   "yang hanya muncul sesekali cocok untuk promo musiman.")

# 6. Profil keranjang =========================================================
with tabs[5]:
    c1, c2 = st.columns(2)
    with c1:
        freq = pd.Series([i for t in tx for i in t]).value_counts().head(20).iloc[::-1]
        fig = px.bar(x=freq.values, y=freq.index, orientation="h", labels={"x": "Jumlah keranjang", "y": ""},
                     title="20 item paling sering dibeli", color_discrete_sequence=[HIJAU])
        fig.update_layout(height=520, margin=dict(l=10, r=10, t=40, b=10))
        st.plotly_chart(fig)
    with c2:
        dist = sizes.value_counts().sort_index()
        fig = px.bar(x=dist.index.astype(str), y=dist.values, labels={"x": "Jumlah item berbeda", "y": "Keranjang"},
                     title="Distribusi ukuran keranjang", color_discrete_sequence=[TANAH])
        fig.update_layout(height=250, margin=dict(l=10, r=10, t=40, b=10))
        st.plotly_chart(fig)
        if "Channel" in dfp.columns:
            ch = dfp.groupby("Channel")["Nomor_PO"].nunique().sort_values(ascending=False)
            fig = px.bar(x=ch.values, y=ch.index, orientation="h", labels={"x": "Keranjang", "y": ""},
                         title="Keranjang per channel", color_discrete_sequence=[EMAS])
            fig.update_layout(height=250, margin=dict(l=10, r=10, t=40, b=10), yaxis=dict(autorange="reversed"))
            st.plotly_chart(fig)

# 7. Metodologi ===============================================================
with tabs[6]:
    st.markdown("""
### Definisi keranjang
Satu **Nomor PO** dianggap satu keranjang belanja. Produk yang berada di Nomor PO yang sama berarti dibeli bersamaan.

### Metrik
* **Support**: porsi keranjang yang memuat kombinasi produk.
* **Confidence**: dari keranjang yang berisi produk *jika*, berapa persen juga berisi produk *maka*.
* **Lift** (metrik utama): confidence dibagi peluang dasar produk *maka*. Lift 1 berarti tidak ada hubungan,
  lift 2 berarti customer dua kali lebih mungkin membeli produk *maka* bila sudah membeli produk *jika*.

### Empat algoritma
""")
    for a in C.ALGOS:
        st.markdown(f"* **{a}**: {ALGO_INFO[a]}")
    st.markdown("""
### Konsensus
1. Keempat algoritma dijalankan dengan parameter yang sama (minimal keranjang, confidence, lift).
2. Setiap aturan diberi **suara** sesuai jumlah algoritma yang menemukannya.
3. **Skor konsensus = Lift x (Suara / 4)**. Lift tetap penentu utama, namun aturan yang hanya didukung sebagian
   algoritma otomatis turun peringkat.
4. Aturan dirangkum menjadi **kandidat bundle**. Prioritas:
   * **Prioritas Tinggi**: suara minimal 3 dan lift minimal 2.
   * **Prioritas Sedang**: suara minimal 3 dan lift minimal 1,2, atau suara 2 dengan lift minimal 2.
   * **Pantau**: sisanya.

### Catatan penting
* Apriori, FP Growth, AIS dan ARN menemukan **itemset** yang sama (semuanya algoritma eksak). Perbedaannya ada pada
  bentuk aturan: AIS dan ARN hanya membentuk aturan dengan satu produk hasil, dan ARN menambahkan uji signifikansi.
  Karena itu aturan yang disepakati 4 algoritma adalah aturan satu produk hasil yang signifikan secara statistik.
* Lift sangat tinggi pada kombinasi yang jarang (misalnya hanya 2 keranjang) perlu dibaca hati hati. Perhatikan kolom
  **Keranjang** dan tab **Tren** sebelum memutuskan bundle permanen.
* Mode **Perilaku organik** disarankan untuk mencari ide bundle baru karena pasangan produk yang muncul hanya
  karena listing bundle existing tidak ikut terhitung.
""")
