"""
Mengubah file kunci JSON service account Google menjadi .streamlit/secrets.toml

Cara pakai (di folder proyek):
    python buat_secrets.py nama_file_kunci.json

Isi file secrets.toml yang dihasilkan juga bisa langsung ditempel ke
Streamlit Community Cloud pada menu Settings > Secrets.
"""

import json
import sys
from pathlib import Path

if len(sys.argv) < 2:
    sys.exit("Contoh: python buat_secrets.py kunci_service_account.json")

key = json.loads(Path(sys.argv[1]).read_text())
url = input("Tempel URL Google Sheets: ").strip()
tab = input("Nama tab/worksheet (kosongkan untuk tab pertama): ").strip()

lines = ["[gsheet]", f"spreadsheet = {json.dumps(url)}", f"worksheet = {json.dumps(tab)}", "",
         "[gcp_service_account]"]
for k, v in key.items():
    lines.append(f"{k} = {json.dumps(v)}")

out = Path(".streamlit") / "secrets.toml"
out.parent.mkdir(exist_ok=True)
out.write_text("\n".join(lines) + "\n")
print(f"Selesai. File tersimpan di {out}")
print(f"Jangan lupa bagikan Google Sheets ke email ini sebagai Viewer: {key.get('client_email')}")
