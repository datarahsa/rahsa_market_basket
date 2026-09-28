# Rahsa Nusantara · Market Basket Analysis

Aplikasi Streamlit untuk menemukan produk yang biasa dibeli bersamaan dalam satu Nomor PO, memakai
Apriori, FP Growth, AIS dan ARN yang disatukan lewat konsensus berbasis **lift**. Data dibaca langsung
dari Google Sheets dan aplikasi di hosting gratis di Streamlit Community Cloud lewat GitHub.

## Isi folder

* `app.py`: Tampilan aplikasi (sidebar, tab, grafik)
* `mba/data.py`: Membaca Google Sheets, membersihkan data, membentuk keranjang per Nomor PO
* `mba/algorithms.py`: Implementasi Apriori, FP Growth, AIS, ARN
* `mba/consensus.py`: Konsensus 4 algoritma dan tabel rekomendasi bundle
* `buat_secrets.py`: Pembantu mengubah kunci JSON Google menjadi `secrets.toml`
* `requirements.txt`: Daftar library yang diinstal otomatis oleh Streamlit Cloud
* `.streamlit/config.toml`: Tema warna aplikasi
* `.streamlit/secrets.toml.example`: Contoh format secrets
* `.gitignore`: Mencegah kunci dan file data ikut terupload ke GitHub

## Langkah 1 · Pindahkan data ke Google Sheets

1. Buka Google Drive, klik **Baru > Upload file**, pilih `Rahsa_Sales_2026.xlsx`.
2. Klik kanan file tersebut > **Buka dengan > Google Spreadsheet**, lalu **File > Simpan sebagai Google Spreadsheet**.
3. Ganti nama tab di bawah menjadi `Sales` (nama asli hasil export mengandung tanda baca yang rawan salah ketik).
4. Pastikan baris 1 berisi judul kolom persis seperti ini (huruf besar kecil berpengaruh):
   `Nomor_PO`, `Tanggal`, `Item_Name`, `Product`, `Kode`, `Product_Group`, `Channel`, `SKU`, `Jumlah`, `Value_Sales`.
   Wajib: `Nomor_PO` dan `Tanggal`. Sisanya dipakai bila ada.
5. Salin URL spreadsheet dari address bar.

Data baru cukup ditambahkan sebagai baris baru di tab yang sama.

## Langkah 2 · Buat Service Account Google (kunci akses baca)

1. Buka `console.cloud.google.com`, login dengan akun Google, lalu buat project baru (misal `rahsa mba`).
2. Menu **APIs & Services > Library**: cari dan klik **Enable** untuk **Google Sheets API** dan **Google Drive API**.
3. Menu **IAM & Admin > Service Accounts > Create service account**. Isi nama bebas, klik **Create and continue**,
   lewati pemberian role, klik **Done**.
4. Klik service account yang baru dibuat > tab **Keys > Add key > Create new key > JSON > Create**.
   File JSON akan terunduh. Simpan baik baik dan **jangan pernah diupload ke GitHub**.
5. Buka file JSON, salin nilai `client_email`.

## Langkah 3 · Bagikan Google Sheets ke Service Account

Di Google Sheets klik **Bagikan**, tempel `client_email` tadi, pilih akses **Viewer**, hilangkan centang
notifikasi, klik **Bagikan**. Tanpa langkah ini aplikasi akan gagal dengan pesan izin ditolak.

## Langkah 4 · Upload kode ke GitHub

1. Login ke `github.com` > **New repository**. Beri nama misal `rahsa_market_basket`, pilih **Private**
   (disarankan karena ini data penjualan perusahaan), klik **Create repository**.
2. Klik **uploading an existing file**, lalu seret semua isi folder ini termasuk folder `mba` dan `.streamlit`.
   Catatan Mac/Windows: folder `.streamlit` bisa tersembunyi. Bila tidak ikut, buat manual lewat
   **Add file > Create new file** dengan nama `.streamlit/config.toml` lalu tempel isinya.
3. Klik **Commit changes**.
4. Pastikan yang TIDAK ada di GitHub: file kunci JSON, `secrets.toml`, file Excel data.

## Langkah 5 · Uji di laptop (opsional tapi disarankan)

```bash
pip install streamlit pandas gspread networkx plotly scipy openpyxl
python buat_secrets.py nama_file_kunci.json
streamlit run app.py
```

`buat_secrets.py` akan menanyakan URL Google Sheets dan nama tab (`Sales`) lalu membuat `.streamlit/secrets.toml`.
Bila sidebar menampilkan **Terhubung ke Google Sheets**, koneksi sudah benar.

## Langkah 6 · Deploy ke Streamlit Community Cloud

1. Buka `share.streamlit.io`, login dengan akun GitHub. Bila repo private, izinkan Streamlit mengakses repo private
   saat diminta.
2. Klik **Create app** > pilih deploy dari GitHub.
3. Isi: Repository `username/rahsa_market_basket`, Branch `main`, Main file path `app.py`.
4. Buka **Advanced settings**: pilih Python 3.12, lalu pada kotak **Secrets** tempel SELURUH isi file
   `.streamlit/secrets.toml` hasil Langkah 5 (atau isi manual mengikuti `secrets.toml.example`).
5. Klik **Deploy**. Instalasi pertama sekitar 2 sampai 5 menit.
6. Setelah jalan, buka **Settings > Sharing** untuk membatasi siapa saja yang boleh membuka aplikasi
   (undang email tim Rahsa Nusantara).

Mengubah secrets di kemudian hari: **Manage app > Settings > Secrets**. Mengubah kode: edit file di GitHub,
aplikasi otomatis memperbarui diri.

## Cara memakai aplikasi

1. **Level produk**: `Item` (default), kode produk, produk dan variasi, atau grup produk.
2. **Perlakuan bundle yang sudah ada**
   * *Perilaku organik* (disarankan): listing bundle marketplace yang berisi 2 produk atau lebih dihitung sebagai satu item
     `[Bundle] A + B`, sehingga hasil mencerminkan kombinasi yang dipilih customer sendiri.
   * *Semua produk*: listing bundle dipecah ke produk penyusunnya.
3. **Timeframe**: Harian, Mingguan (Senin s/d Minggu), Bulanan, atau Seluruh periode, lalu pilih periodenya.
4. **Parameter algoritma**: minimal keranjang otomatis menyesuaikan timeframe (2 / 3 / 5 / 20), bisa diubah.
5. Baca tab **Rekomendasi Bundle**, cek stabilitasnya di tab **Tren Antar Periode**, lalu unduh CSV.

Data dari Google Sheets disimpan sementara 10 menit. Klik **Muat ulang data** untuk mengambil data terbaru saat itu juga.

## Masalah umum

* `SpreadsheetNotFound` atau `PERMISSION_DENIED`: Sheet belum dibagikan ke `client_email` (Langkah 3)
* `WorksheetNotFound`: Nama tab di secrets tidak sama dengan nama tab di Sheets
* `Kolom wajib tidak ditemukan`: Judul kolom baris 1 berbeda, cek ejaan dan spasi
* Error `private_key` / `Invalid JWT`: Isi `private_key` harus utuh termasuk tanda `\n`, paling aman pakai `buat_secrets.py`
* API belum aktif: Aktifkan Google Sheets API dan Google Drive API (Langkah 2)
* Aplikasi tertidur: App gratis tidur bila lama tidak dibuka, klik tombol bangunkan dan tunggu sebentar
