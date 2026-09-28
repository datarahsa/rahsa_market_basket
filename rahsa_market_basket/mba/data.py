"""Memuat data dari Google Sheets (atau file upload), membersihkan, dan membentuk keranjang."""

from __future__ import annotations

import pandas as pd

BULAN_ID = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli",
            "Agustus", "September", "Oktober", "November", "Desember"]
BULAN_SINGKAT = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]

REQUIRED = ["Nomor_PO", "Tanggal"]
ITEM_LEVELS = {
    "Item_Name": "Item (nama produk)",
    "Product": "Kode produk",
    "Kode": "Produk dan variasi",
    "Product_Group": "Grup produk",
}

READONLY_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]


# ===========================================================================
# Sumber data
# ===========================================================================
def read_google_sheet(service_account_info: dict, spreadsheet: str, worksheet: str | None) -> pd.DataFrame:
    import gspread

    gc = gspread.service_account_from_dict(dict(service_account_info), scopes=READONLY_SCOPES)
    sh = gc.open_by_url(spreadsheet) if spreadsheet.startswith("http") else gc.open_by_key(spreadsheet)
    ws = sh.worksheet(worksheet) if worksheet else sh.get_worksheet(0)
    # UNFORMATTED_VALUE: angka tetap angka (tidak terpengaruh format Rupiah / titik ribuan)
    # SERIAL_NUMBER: tanggal dikirim sebagai angka serial sehingga aman dari format lokal
    values = ws.get_all_values(value_render_option="UNFORMATTED_VALUE",
                               date_time_render_option="SERIAL_NUMBER")
    if not values:
        return pd.DataFrame()
    header = [str(h).strip() for h in values[0]]
    return pd.DataFrame(values[1:], columns=header)


def read_uploaded(file) -> pd.DataFrame:
    name = file.name.lower()
    if name.endswith((".xlsx", ".xls")):
        return pd.read_excel(file)
    return pd.read_csv(file)


# ===========================================================================
# Pembersihan
# ===========================================================================
def _to_datetime(s: pd.Series) -> pd.Series:
    if pd.api.types.is_datetime64_any_dtype(s):
        return s.dt.normalize()
    num = pd.to_numeric(s, errors="coerce")
    out = pd.to_datetime(num, unit="D", origin="1899-12-30", errors="coerce")
    rest = out.isna() & s.notna() & (s.astype(str).str.strip() != "")
    if rest.any():
        out.loc[rest] = pd.to_datetime(s[rest].astype(str), dayfirst=True, errors="coerce", format="mixed")
    return out.dt.normalize()


def _clean_code(v) -> str | None:
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    s = str(v).strip()
    return s or None


def clean(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise ValueError(f"Kolom wajib tidak ditemukan: {', '.join(missing)}")
    df = df.replace("", pd.NA)
    df["Nomor_PO"] = df["Nomor_PO"].map(_clean_code)
    df["Tanggal"] = _to_datetime(df["Tanggal"])
    for c in ["Jumlah", "Value_Sales", "Satuan", "Price", "Gross_Sales", "Voucher"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    for c in ["Channel", "SKU", *ITEM_LEVELS.keys()]:
        if c in df.columns:
            df[c] = df[c].map(_clean_code)
    df = df.dropna(subset=["Nomor_PO", "Tanggal"])
    return df


# ===========================================================================
# Periode waktu
# ===========================================================================
def add_periods(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    t = df["Tanggal"]
    df["p_harian"] = t
    df["p_mingguan"] = t - pd.to_timedelta(t.dt.weekday, unit="D")  # Senin sebagai awal minggu
    df["p_bulanan"] = t.dt.to_period("M").dt.to_timestamp()
    return df


def label_period(ts: pd.Timestamp, granularity: str) -> str:
    if granularity == "Harian":
        return f"{ts.day} {BULAN_SINGKAT[ts.month - 1]} {ts.year}"
    if granularity == "Mingguan":
        end = ts + pd.Timedelta(days=6)
        wk = ts.isocalendar().week
        return (f"Minggu {wk} · {ts.day} {BULAN_SINGKAT[ts.month - 1]} "
                f"s/d {end.day} {BULAN_SINGKAT[end.month - 1]} {end.year}")
    if granularity == "Bulanan":
        return f"{BULAN_ID[ts.month - 1]} {ts.year}"
    return "Seluruh periode"


PERIOD_COL = {"Harian": "p_harian", "Mingguan": "p_mingguan", "Bulanan": "p_bulanan"}


# ===========================================================================
# Keranjang belanja
# ===========================================================================
def build_transactions(df: pd.DataFrame, item_col: str, bundle_mode: str) -> pd.Series:
    """
    Satu Nomor PO = satu keranjang.

    bundle_mode:
      "komponen" : listing bundle marketplace dipecah menjadi produk penyusunnya.
      "organik"  : listing yang berisi 2 produk atau lebih dihitung sebagai SATU item
                   berlabel "[Bundle] A + B", sehingga pasangan produk yang muncul
                   hanya karena bundle existing tidak ikut dihitung sebagai perilaku organik.
    """
    cols = ["Nomor_PO", item_col] + (["SKU"] if "SKU" in df.columns else [])
    d = df[cols].dropna(subset=["Nomor_PO", item_col])
    if bundle_mode == "organik" and "SKU" in d.columns:
        d = d.copy()
        d["SKU"] = d["SKU"].fillna("tanpa_sku")
        comp = d.groupby(["Nomor_PO", "SKU"])[item_col].agg(lambda s: tuple(sorted(set(s))))
        tokens = comp.map(lambda c: f"[Bundle] {' + '.join(c)}" if len(c) > 1 else c[0])
        tx = tokens.groupby(level="Nomor_PO").agg(frozenset)
    else:
        tx = d.groupby("Nomor_PO")[item_col].agg(frozenset)
    return tx


def unit_prices(df: pd.DataFrame, item_col: str) -> dict:
    """Harga rata rata per unit (Value_Sales / Jumlah) untuk referensi harga bundle."""
    if not {"Value_Sales", "Jumlah"}.issubset(df.columns):
        return {}
    g = df.dropna(subset=[item_col]).groupby(item_col)[["Value_Sales", "Jumlah"]].sum()
    g = g[g["Jumlah"] > 0]
    return (g["Value_Sales"] / g["Jumlah"]).to_dict()
