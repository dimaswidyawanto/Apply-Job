# ruff: noqa: E501  (template HTML/CSS/JS ditulis apa adanya di dalam string)
"""Dashboard monitoring lokal (master prompt pasal 11).

Server HTTP kecil memakai pustaka standar — tanpa dependensi baru:

- `GET /`            halaman yang menyegarkan diri setiap 2 detik,
- `GET /api/status`  JSON statistik, antrean, log, dan status kendali,
- `POST /api/aksi`   kontrol yang benar-benar bekerja:
  `start`, `pause`, `lanjut`, `stop`, `clear`, `retry`, `hapus-log`.

`start` menjalankan sesi lamar otomatis di proses terpisah
(`cli.py lamar --tanpa-perbarui`), `pause`/`lanjut`/`stop` menulis berkas
perintah yang diperiksa sesi di antara lowongan (`kendali.py`), `clear`
menghapus antrean yang belum pernah dilamar, `retry` mengembalikan lowongan
gagal ke antrean.
"""

import contextlib
import json
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import kendali
import kuota
import laporan
import log_aktivitas
from database import db

PORT_BAKU = 8765
_ANAK: dict = {"proses": None, "mulai": 0.0}


# --------------------------------------------------------------- bantuan ---
def sesi_berjalan() -> bool:
    proses = _ANAK.get("proses")
    return bool(proses and proses.poll() is None)


def status() -> dict:
    """Data untuk dashboard (juga dipakai tes)."""
    data = laporan.ringkasan()

    return {
        "waktu": log_aktivitas.waktu_sekarang(),
        "kuota": {
            "batas": kuota.batas(),
            "terpakai": kuota.terpakai(db),
            "sisa": kuota.sisa(db),
            "ringkasan": kuota.ringkasan(db),
        },
        "sesi": {
            "berjalan": sesi_berjalan(),
            "kendali": kendali.baca("."),
            "pid": getattr(_ANAK.get("proses"), "pid", None),
            "mulai": _ANAK.get("mulai") or None,
        },
        "ringkasan": data,
        "log": log_aktivitas.baris_terakhir(40),
    }


def aksi(nama: str, konfirmasi: bool = False) -> dict:
    """Jalankan satu kontrol dashboard. Hasil: {"ok": bool, "pesan": str}."""
    nama = str(nama or "").strip().lower()

    if nama == "start":
        if sesi_berjalan():
            return {"ok": False, "pesan": "Sesi sudah berjalan"}
        try:
            proses = subprocess.Popen(
                [sys.executable, "cli.py", "lamar", "--tanpa-perbarui"],
                cwd=str(Path(__file__).resolve().parent),
            )
        except OSError as exc:
            return {"ok": False, "pesan": f"Gagal memulai: {exc}"}

        _ANAK["proses"] = proses
        _ANAK["mulai"] = time.time()
        kendali.perintah("lanjut")
        log_aktivitas.catat(f"Sesi dimulai dari dashboard (PID {proses.pid})")
        return {"ok": True, "pesan": f"Sesi dimulai (PID {proses.pid})"}

    if nama in ("pause", "lanjut", "stop"):
        # "pause" di UI = "jeda" di berkas kendali.
        arahan = "jeda" if nama == "pause" else nama
        if not kendali.perintah(arahan):
            return {"ok": False, "pesan": f"Perintah {nama} gagal"}
        log_aktivitas.catat(f"Perintah dashboard: {nama}")
        if nama == "stop":
            proses = _ANAK.get("proses")
            if proses and proses.poll() is None:
                with contextlib.suppress(OSError):
                    proses.terminate()
        return {"ok": True, "pesan": f"Perintah {nama} dikirim"}

    if nama == "clear":
        if not konfirmasi:
            return {"ok": False, "pesan": "Butuh konfirmasi untuk menghapus"}
        jumlah = db.bersihkan_antrean()
        log_aktivitas.catat(f"Antrean dibersihkan: {jumlah} lowongan")
        return {"ok": True, "pesan": f"{jumlah} lowongan dihapus dari antrean"}

    if nama == "retry":
        jumlah = db.ulang_gagal()
        log_aktivitas.catat(f"Retry: {jumlah} lowongan gagal dikembalikan")
        return {"ok": True, "pesan": f"{jumlah} lowongan dikembalikan ke antrean"}

    if nama == "hapus-log":
        if not konfirmasi:
            return {"ok": False, "pesan": "Butuh konfirmasi"}
        log_aktivitas.kosongkan()
        return {"ok": True, "pesan": "Log dikosongkan"}

    return {"ok": False, "pesan": f"Aksi tidak dikenal: {nama}"}


# ------------------------------------------------------------------ HTML ---
HALAMAN = """<!doctype html>
<html lang="id"><head><meta charset="utf-8">
<title>Dashboard Lamar Otomatis</title>
<style>
body{font-family:system-ui,Segoe UI,Arial;margin:0;background:#0f172a;color:#e2e8f0}
header{padding:14px 20px;background:#1e293b;display:flex;gap:12px;align-items:center;flex-wrap:wrap}
h1{font-size:17px;margin:0;font-weight:600}
button{background:#334155;color:#e2e8f0;border:0;padding:8px 12px;border-radius:6px;cursor:pointer;font-size:13px}
button:hover{background:#475569}
button.p{background:#16a34a}button.d{background:#b91c1c}button.w{background:#b45309}
main{padding:16px 20px;display:grid;gap:14px;grid-template-columns:repeat(auto-fit,minmax(280px,1fr))}
section{background:#1e293b;border-radius:8px;padding:12px 14px}
h2{font-size:13px;text-transform:uppercase;letter-spacing:.04em;color:#94a3b8;margin:0 0 8px}
.k{display:flex;justify-content:space-between;padding:3px 0;font-size:14px}
.v{font-weight:600;color:#38bdf8}
table{width:100%;border-collapse:collapse;font-size:13px}
td,th{padding:3px 4px;text-align:left;border-bottom:1px solid #334155}
pre{white-space:pre-wrap;font-size:11.5px;line-height:1.45;margin:0;color:#cbd5e1;max-height:260px;overflow:auto}
#pesan{font-size:12.5px;color:#fbbf24}
</style></head><body>
<header>
  <h1>Lamar Otomatis — Dashboard</h1>
  <button class="p" onclick="aksi('start')">Start</button>
  <button class="w" onclick="aksi('pause')">Pause</button>
  <button onclick="aksi('lanjut')">Resume</button>
  <button class="d" onclick="aksi('stop')">Stop</button>
  <button onclick="aksi('retry')">Retry failed</button>
  <button class="d" onclick="if(confirm('Hapus antrean yang belum pernah dilamar?'))aksi('clear',1)">Clear queue</button>
  <span id="pesan"></span>
</header>
<main>
  <section><h2>Kuota harian</h2><div id="kuota"></div></section>
  <section><h2>Ringkasan</h2><div id="angka"></div></section>
  <section><h2>Status antrean</h2><div id="antrean"></div></section>
  <section><h2>Per lokasi</h2><table id="lokasi"></table></section>
  <section><h2>Per kategori</h2><table id="kategori"></table></section>
  <section><h2>Aktivitas</h2><pre id="log"></pre></section>
</main>
<script>
function baris(id,obj){document.getElementById(id).innerHTML=Object.entries(obj)
 .map(([k,v])=>`<div class="k"><span>${k}</span><span class="v">${v}</span></div>`).join('')}
function tabel(id,rows,kolom){const el=document.getElementById(id);
 el.innerHTML='<tr>'+kolom.map(k=>`<th>${k}</th>`).join('')+'</tr>'+
 rows.map(r=>'<tr>'+kolom.map(k=>`<td>${r[k]??''}</td>`).join('')+'</tr>').join('')}
async function segarkan(){
 try{const r=await fetch('api/status');const d=await r.json();
  baris('kuota',{Batas:d.kuota.batas,Terpakai:d.kuota.terpakai,
   Sisa:d.kuota.sisa,Sesi:d.sesi.berjalan?'berjalan':d.sesi.kendali});
  const g=d.ringkasan;
  baris('angka',{'Lowongan tersimpan':g.lowongan_tersimpan,
   'Lamaran terkirim':g.lamaran_terkirim,'Hari ini':g.lamaran_hari_ini,
   'Tingkat berhasil':g.tingkat_berhasil+'%'});
  baris('antrean',g.status_antrean);
  tabel('lokasi',g.per_lokasi,['lokasi','jumlah','dilamar']);
  tabel('kategori',g.per_kategori,['kategori','jumlah','dilamar']);
  document.getElementById('log').textContent=d.log.join('\\n')||'(belum ada aktivitas)';
 }catch(e){document.getElementById('pesan').textContent='Gagal memuat: '+e}
}
async function aksi(nama,konfirmasi){
 const r=await fetch('api/aksi?aksi='+nama+(konfirmasi?'&konfirmasi=1':''),{method:'POST'});
 const d=await r.json();
 document.getElementById('pesan').textContent=d.pesan;
 segarkan();
}
segarkan();setInterval(segarkan,2000);
</script></body></html>
"""


# ----------------------------------------------------------------- server ---
class PenanganDash(BaseHTTPRequestHandler):
    server_version = "DimastesDashboard/1.0"

    def _kirim(self, kode: int, isi: bytes, tipe: str) -> None:
        self.send_response(kode)
        self.send_header("Content-Type", tipe)
        self.send_header("Content-Length", str(len(isi)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        with contextlib.suppress(BrokenPipeError, ConnectionResetError):
            self.wfile.write(isi)

    def _json(self, data: dict, kode: int = 200) -> None:
        self._kirim(
            kode, json.dumps(data, ensure_ascii=False).encode("utf-8"),
            "application/json; charset=utf-8",
        )

    def do_GET(self) -> None:  # noqa: N802 (nama wajib dari http.server)
        alamat = urlparse(self.path)

        if alamat.path in ("/", "/index.html"):
            self._kirim(200, HALAMAN.encode("utf-8"), "text/html; charset=utf-8")
            return

        if alamat.path == "/api/status":
            try:
                self._json(status())
            except Exception as exc:
                self._json({"galat": str(exc)}, 500)
            return

        self._json({"galat": "tidak ditemukan"}, 404)

    def do_POST(self) -> None:  # noqa: N802
        alamat = urlparse(self.path)

        if alamat.path != "/api/aksi":
            self._json({"galat": "tidak ditemukan"}, 404)
            return

        kueri = parse_qs(alamat.query)
        nama = (kueri.get("aksi") or [""])[0]
        yakin = (kueri.get("konfirmasi") or ["0"])[0] in ("1", "true", "ya")

        hasil = aksi(nama, yakin)
        self._json(hasil, 200 if hasil.get("ok") else 400)

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        """Diam: log HTTP tidak perlu memenuhi konsol pengguna."""


def buat_server(port: int = PORT_BAKU, host: str = "0.0.0.0") -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), PenanganDash)


def jalankan(port: int = PORT_BAKU, host: str = "0.0.0.0",
             buka_browser: bool = True) -> None:
    """Jalankan dashboard sampai Ctrl+C."""
    import webbrowser

    server = buat_server(port, host)
    alamat = f"http://127.0.0.1:{port}/"

    print(f"Dashboard berjalan di {alamat}")
    print("Tekan Ctrl+C untuk berhenti.")
    log_aktivitas.catat("Dashboard dibuka")

    if buka_browser:
        threading.Timer(1.0, lambda: webbrowser.open(alamat)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nDashboard dihentikan.")
    finally:
        server.server_close()
