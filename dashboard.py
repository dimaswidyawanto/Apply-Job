# ruff: noqa: E501  (template HTML/CSS/JS ditulis apa adanya di dalam string)
"""Dashboard monitoring lokal (master prompt pasal 11).

Server HTTP kecil memakai pustaka standar — tanpa dependensi baru:

- `GET /`            halaman yang menyegarkan diri setiap 2 detik,
- `GET /api/status`  JSON statistik, antrean, log, dan status kendali,
- `GET /api/lowongan?job_id=`  detail satu lowongan + riwayatnya,
- `GET /api/riwayat?limit=`     riwayat lamaran terakhir,
- `POST /api/aksi`   kontrol yang benar-benar bekerja:
  `start`, `pause`, `lanjut`, `stop`, `clear`, `retry`, `hapus-log`,
- `POST /api/konfigurasi`  ubah `.env` dengan validasi (MIN_SALARY,
  MAX_APPLY_PER_DAY, MAX_AGE_DAYS, LOCATIONS, PRIORITAS_*).

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
from config import config
from database import db

PORT_BAKU = 8765
# Berkas .env yang diubah lewat dashboard (tes bisa menggantinya).
PATH_ENV = Path(__file__).resolve().parent / ".env"
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
        "konfigurasi": {
            "MIN_SALARY": config.min_salary,
            "MAX_APPLY_PER_DAY": config.max_apply_per_day,
            "MAX_AGE_DAYS": config.max_age_days,
            "LOCATIONS": ",".join(config.locations or []),
            "PRIORITAS_LOKASI": ",".join(
                getattr(config, "prioritas_lokasi", []) or []
            ),
        },
        "log": log_aktivitas.baris_terakhir(40),
    }


def detail_lowongan(job_id: str) -> dict:
    """Detail satu lowongan + riwayat lamarannya (pasal 11.5)."""
    job_id = str(job_id or "").strip()
    if not job_id:
        return {"ok": False, "pesan": "job_id kosong"}

    job = db.get_job(job_id)
    if not job:
        return {"ok": False, "pesan": f"Lowongan {job_id} tidak ada di database"}

    with db._get_conn() as conn:  # noqa: SLF001 (pembacaan langsung, aman)
        riwayat = [
            dict(baris)
            for baris in conn.execute(
                """
                SELECT applied_at, status, notes
                  FROM applications
                 WHERE job_id = ?
                 ORDER BY applied_at DESC, id DESC
                """,
                (job_id,),
            )
        ]

    return {
        "ok": True,
        "lowongan": job,
        "riwayat": riwayat,
        "sudah_dilamar": db.is_already_applied(job_id),
    }


def riwayat(batas: int = 30) -> dict:
    """Riwayat lamaran terakhir untuk ditampilkan di dashboard."""
    batas = max(1, min(200, int(batas or 30)))
    return {"ok": True, "riwayat": db.get_recent_applications(batas)}


# Nilai .env yang boleh diubah dari dashboard, beserta pemeriksanya.
_KONFIG_DIIZINKAN = {
    "MIN_SALARY": ("angka", 0, 1_000_000_000),
    "MAX_APPLY_PER_DAY": ("angka", 0, 1000),
    "MAX_AGE_DAYS": ("angka", 0, 365),
    "LOCATIONS": ("daftar", 1, 20),
    "PRIORITAS_LOKASI": ("daftar", 0, 20),
    "PRIORITAS_KATEGORI": ("daftar", 0, 30),
}


def _periksa_nilai(kunci: str, nilai) -> str:
    """Kembalikan nilai yang sudah dibersihkan; lempar ValueError bila salah."""
    jenis, minimal, maksimal = _KONFIG_DIIZINKAN[kunci]

    if jenis == "angka":
        teks = str(nilai).strip().replace(".", "").replace(",", "")
        if not teks.isdigit():
            raise ValueError(f"{kunci} harus angka, bukan {nilai!r}")
        angka = int(teks)
        if not minimal <= angka <= maksimal:
            raise ValueError(f"{kunci} harus {minimal}-{maksimal}, bukan {angka}")
        return str(angka)

    if isinstance(nilai, (list, tuple)):
        butir = [str(b).strip() for b in nilai]
    else:
        butir = [b.strip() for b in str(nilai).split(",")]

    butir = [b for b in butir if b]
    if not (minimal <= len(butir) <= maksimal):
        raise ValueError(
            f"{kunci} harus {minimal}-{maksimal} butir, bukan {len(butir)}"
        )
    if any(len(b) > 40 for b in butir):
        raise ValueError(f"{kunci} berisi nama yang terlalu panjang")
    return ",".join(butir)


def simpan_konfigurasi(pasangan: dict) -> dict:
    """Ubah nilai .env dari dashboard (dengan validasi + cadangan .env.bak)."""
    import env_tools

    if not isinstance(pasangan, dict) or not pasangan:
        return {"ok": False, "pesan": "Tidak ada nilai yang dikirim"}

    bersih = {}
    try:
        for kunci, nilai in pasangan.items():
            nama = str(kunci or "").strip().upper()
            if nama not in _KONFIG_DIIZINKAN:
                raise ValueError(f"{kunci} tidak boleh diubah dari dashboard")
            bersih[nama] = _periksa_nilai(nama, nilai)
    except ValueError as salah:
        return {"ok": False, "pesan": str(salah)}

    hasil = env_tools.atur_nilai(PATH_ENV, bersih)
    log_aktivitas.catat(
        "Konfigurasi diubah dari dashboard: "
        + ", ".join(f"{k}={v}" for k, v in bersih.items())
    )

    return {
        "ok": True,
        "pesan": "Konfigurasi disimpan. Mulai sesi baru agar berlaku.",
        "perubahan": hasil.get("perubahan") or [],
        "perlu_restart": True,
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
input{background:#0f172a;color:#e2e8f0;border:1px solid #334155;border-radius:6px;padding:6px 8px;font-size:13px;width:100%;box-sizing:border-box;margin-bottom:6px}
label{font-size:12px;color:#94a3b8;display:block;margin-bottom:2px}
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
  <section><h2>Riwayat lamaran</h2><table id="riwayat"></table></section>
  <section><h2>Detail lowongan</h2>
    <input id="jid" placeholder="job_id, mis. 88112233">
    <button onclick="cariDetail()">Lihat detail</button>
    <pre id="detail">(belum ada)</pre></section>
  <section><h2>Konfigurasi</h2>
    <label>MIN_SALARY</label><input id="k-MIN_SALARY" placeholder="4500000">
    <label>MAX_APPLY_PER_DAY</label><input id="k-MAX_APPLY_PER_DAY" placeholder="50">
    <label>MAX_AGE_DAYS</label><input id="k-MAX_AGE_DAYS" placeholder="30">
    <label>LOCATIONS (pisah koma)</label><input id="k-LOCATIONS" placeholder="Bandung,Jakarta">
    <label>PRIORITAS_LOKASI (pisah koma)</label><input id="k-PRIORITAS_LOKASI" placeholder="Bandung,Cikarang">
    <button class="w" onclick="simpanKonf()">Simpan konfigurasi</button>
    <pre id="konf-pesan"></pre></section>
</main>
<script>
const NL=String.fromCharCode(10);
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
  document.getElementById('log').textContent=d.log.join(NL)||'(belum ada aktivitas)';
  isiKonfigurasi(d.konfigurasi);
 }catch(e){document.getElementById('pesan').textContent='Gagal memuat: '+e}
}
async function aksi(nama,konfirmasi){
 const r=await fetch('api/aksi?aksi='+nama+(konfirmasi?'&konfirmasi=1':''),{method:'POST'});
 const d=await r.json();
 document.getElementById('pesan').textContent=d.pesan;
 segarkan();
}
function isiKonfigurasi(k){
 Object.entries(k||{}).forEach(([nama,nilai])=>{
  const el=document.getElementById('k-'+nama);
  if(el && !el.value) el.placeholder=nilai;
  if(el && !el.value && el.dataset.terisi!=='1'){el.value=nilai;el.dataset.terisi='1'}
 })}
async function muatRiwayat(){
 try{const r=await fetch('api/riwayat?limit=10');const d=await r.json();
  tabel('riwayat',d.riwayat||[],['applied_at','title','company','status']);
 }catch(e){}}
async function cariDetail(){
 const id=document.getElementById('jid').value.trim();
 if(!id)return;
 const r=await fetch('api/lowongan?job_id='+encodeURIComponent(id));
 const d=await r.json();
 const el=document.getElementById('detail');
 if(!d.ok){el.textContent=d.pesan||'Tidak ditemukan';return}
 const j=d.lowongan;
 el.textContent=[j.title,j.company,j.location,j.salary,
  'Status: '+j.status_antrean,'Alasan: '+(j.alasan||'-'),
  'Skor: '+(j.skor??'-'),'Logo: '+(j.has_logo??'-'),
  'URL: '+(j.url||'-'),'Dilamar: '+(d.sudah_dilamar?'ya':'belum'),
  'Riwayat: '+(d.riwayat.length?d.riwayat.map(x=>x.applied_at+' '+x.status).join('; '):'-')
 ].filter(x=>x!==undefined).join(NL);
}
async function simpanKonf(){
 const pasangan={};
 const isi=(id,k)=>{const v=document.getElementById(id).value.trim();
  if(v)pasangan[k]=v};
 ['MIN_SALARY','MAX_APPLY_PER_DAY','MAX_AGE_DAYS','LOCATIONS',
  'PRIORITAS_LOKASI'].forEach(k=>isi('k-'+k,k));
 if(!Object.keys(pasangan).length){
  document.getElementById('konf-pesan').textContent='Isi minimal satu nilai.';
  return}
 const r=await fetch('api/konfigurasi',{method:'POST',
  headers:{'Content-Type':'application/json'},
  body:JSON.stringify({pasangan})});
 const d=await r.json();
 document.getElementById('konf-pesan').textContent=d.pesan||'';
}
segarkan();muatRiwayat();setInterval(segarkan,2000);setInterval(muatRiwayat,10000);
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

        if alamat.path in ("/api/lowongan", "/api/riwayat"):
            kueri = parse_qs(alamat.query)
            try:
                if alamat.path == "/api/riwayat":
                    batas = int((kueri.get("limit") or ["30"])[0])
                    self._json(riwayat(batas))
                else:
                    job_id = (kueri.get("job_id") or [""])[0]
                    hasil = detail_lowongan(job_id)
                    self._json(hasil, 200 if hasil.get("ok") else 404)
            except Exception as exc:
                self._json({"galat": str(exc)}, 500)
            return

        self._json({"galat": "tidak ditemukan"}, 404)

    def _baca_json(self) -> dict:
        panjang = int(self.headers.get("Content-Length") or 0)
        if panjang <= 0:
            return {}
        mentah = self.rfile.read(panjang)
        try:
            data = json.loads(mentah.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def do_POST(self) -> None:  # noqa: N802
        alamat = urlparse(self.path)

        if alamat.path == "/api/konfigurasi":
            try:
                hasil = simpan_konfigurasi(self._baca_json().get("pasangan") or {})
            except Exception as exc:
                self._json({"ok": False, "pesan": str(exc)}, 500)
                return
            self._json(hasil, 200 if hasil.get("ok") else 400)
            return

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
