"""Dashboard: data nyata dari database + kontrol yang benar-benar bekerja."""

import json
import threading
import urllib.error
import urllib.request

import pytest

import dashboard
import kendali
import laporan
from database import Database


@pytest.fixture
def siap(monkeypatch, tmp_path):
    basis = Database(str(tmp_path / "dash.db"))
    monkeypatch.setattr(dashboard, "db", basis)
    monkeypatch.setattr(laporan, "db", basis)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(dashboard.log_aktivitas, "FOLDER", tmp_path / "logs")
    return basis


@pytest.fixture
def server(siap):
    srv = dashboard.buat_server(0, "127.0.0.1")
    utas = threading.Thread(target=srv.serve_forever, daemon=True)
    utas.start()
    yield srv, f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()
    srv.server_close()


def _get(url):
    with urllib.request.urlopen(url, timeout=5) as jawab:
        return json.loads(jawab.read().decode("utf-8"))


def _post(url):
    permintaan = urllib.request.Request(url, method="POST")
    try:
        with urllib.request.urlopen(permintaan, timeout=5) as jawab:
            return jawab.status, json.loads(jawab.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


# ---------------------------------------------------------------- status ---
def test_api_status_berisi_angka_nyata(server, siap):
    siap.add_job({
        "job_id": "indeed:1", "title": "Inventory Staff",
        "company": "PT A", "location": "Bandung",
        "url": "https://x/1", "has_logo": True,
    })
    _, dasar = server

    data = _get(f"{dasar}/api/status")

    assert data["ringkasan"]["lowongan_tersimpan"] == 1
    assert data["ringkasan"]["status_antrean"]["found"] == 1
    assert data["kuota"]["batas"] is not None
    assert data["sesi"]["berjalan"] is False


def test_halaman_dashboard_bisa_dibuka(server):
    _, dasar = server

    with urllib.request.urlopen(f"{dasar}/", timeout=5) as jawab:
        isi = jawab.read().decode("utf-8")

    assert "Dashboard Lamar Otomatis" in isi
    assert "api/status" in isi


# ---------------------------------------------------------------- kontrol --
def test_pause_dan_lanjut_menulis_perintah(server):
    _, dasar = server

    kode, hasil = _post(f"{dasar}/api/aksi?aksi=pause")
    assert kode == 200 and hasil["ok"] is True
    assert kendali.baca(".") == "jeda"

    kode, _ = _post(f"{dasar}/api/aksi?aksi=lanjut")
    assert kode == 200
    assert kendali.baca(".") == "lanjut"


def test_stop_menulis_perintah_stop(server):
    _, dasar = server

    _post(f"{dasar}/api/aksi?aksi=stop")

    assert kendali.baca(".") == "stop"


def test_clear_butuh_konfirmasi(server, siap):
    siap.add_job({
        "job_id": "indeed:2", "title": "Stok", "company": "PT B",
        "location": "Bandung", "url": "https://x/2", "has_logo": True,
    })
    _, dasar = server

    kode, hasil = _post(f"{dasar}/api/aksi?aksi=clear")
    assert kode == 400 and hasil["ok"] is False
    assert siap.get_job("indeed:2") is not None

    kode, hasil = _post(f"{dasar}/api/aksi?aksi=clear&konfirmasi=1")
    assert kode == 200 and hasil["ok"] is True
    assert siap.get_job("indeed:2") is None


def test_clear_tidak_menghapus_yang_sudah_dilamar(server, siap):
    siap.add_job({
        "job_id": "indeed:3", "title": "Stok", "company": "PT C",
        "location": "Bandung", "url": "https://x/3", "has_logo": True,
    })
    siap.record_application("indeed:3", "applied", "Terkirim")
    _, dasar = server

    _post(f"{dasar}/api/aksi?aksi=clear&konfirmasi=1")

    assert siap.get_job("indeed:3") is not None


def test_retry_mengembalikan_lowongan_gagal(server, siap):
    siap.add_job({
        "job_id": "indeed:4", "title": "Stok", "company": "PT D",
        "location": "Bandung", "url": "https://x/4", "has_logo": True,
    })
    siap.set_status_antrean("indeed:4", "failed", "Timeout")
    _, dasar = server

    kode, hasil = _post(f"{dasar}/api/aksi?aksi=retry")

    assert kode == 200 and hasil["ok"] is True
    assert siap.get_job("indeed:4")["status_antrean"] == "qualified"


def test_aksi_tidak_dikenal_ditolak(server):
    _, dasar = server

    kode, hasil = _post(f"{dasar}/api/aksi?aksi=hapus-semua")

    assert kode == 400
    assert "tidak dikenal" in hasil["pesan"]


# ---------------------------------------------------------------- laporan --
def test_laporan_menghitung_dan_memberi_saran(siap, monkeypatch):
    monkeypatch.setattr(laporan.config, "cv_path", "", raising=False)
    siap.add_job({
        "job_id": "indeed:5", "title": "Inventory", "company": "PT E",
        "location": "Bandung", "url": "https://x/5", "has_logo": True,
    })
    siap.set_status_antrean(
        "indeed:5", "review_required", "Logo tidak dapat dipastikan"
    )
    siap.record_application("indeed:5", "applied", "Terkirim")

    data = laporan.ringkasan()
    saran = laporan.saran(data)

    assert data["lamaran_terkirim"] == 1
    assert data["per_lokasi"][0]["lokasi"] == "Bandung"
    assert any("REVIEW_REQUIRED" in s for s in saran)
    assert any("CV_PATH" in s for s in saran)


# ------------------------------------------- detail, riwayat, konfigurasi ---
def test_api_detail_lowongan_dan_riwayat(server, siap):
    siap.add_job({
        "job_id": "js-77", "title": "PPIC Staff", "company": "PT Detail",
        "location": "Bandung", "url": "https://x/77", "has_logo": True,
    })
    siap.set_status_antrean("js-77", "applied")
    siap.record_application("js-77")
    _, dasar = server

    detail = _get(f"{dasar}/api/lowongan?job_id=js-77")
    assert detail["ok"] is True
    assert detail["lowongan"]["title"] == "PPIC Staff"
    assert detail["sudah_dilamar"] is True
    assert len(detail["riwayat"]) == 1

    riwayat = _get(f"{dasar}/api/riwayat?limit=5")
    assert riwayat["riwayat"][0]["title"] == "PPIC Staff"


def test_api_detail_lowongan_tidak_ada(server):
    _, dasar = server

    with pytest.raises(urllib.error.HTTPError) as info:
        _get(f"{dasar}/api/lowongan?job_id=tidak-ada")

    assert info.value.code == 404
    pesan = json.loads(info.value.read().decode("utf-8"))["pesan"]
    assert "tidak ada" in pesan


def _post_json(url, data):
    badan = json.dumps(data).encode("utf-8")
    permintaan = urllib.request.Request(
        url, data=badan, method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(permintaan, timeout=5) as jawab:
            return jawab.status, json.loads(jawab.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def test_konfigurasi_tersimpan_dengan_validasi(server, tmp_path, monkeypatch):
    berkas_env = tmp_path / ".env"
    berkas_env.write_text("MIN_SALARY=4500000\n", encoding="utf-8")
    monkeypatch.setattr(dashboard, "PATH_ENV", berkas_env)
    _, dasar = server

    kode, hasil = _post_json(
        f"{dasar}/api/konfigurasi",
        {
            "pasangan": {
                "MAX_APPLY_PER_DAY": "50",
                "PRIORITAS_LOKASI": "Bandung,Cikarang",
            }
        },
    )

    assert kode == 200 and hasil["ok"] is True
    isi = berkas_env.read_text(encoding="utf-8")
    assert "MAX_APPLY_PER_DAY=50" in isi
    assert "PRIORITAS_LOKASI=Bandung,Cikarang" in isi


def test_konfigurasi_menolak_kunci_dan_nilai_salah(server, tmp_path, monkeypatch):
    berkas_env = tmp_path / ".env"
    berkas_env.write_text("MIN_SALARY=4500000\n", encoding="utf-8")
    monkeypatch.setattr(dashboard, "PATH_ENV", berkas_env)
    _, dasar = server

    kode, hasil = _post_json(
        f"{dasar}/api/konfigurasi", {"pasangan": {"CV_PATH": "D:/lain.docx"}}
    )
    assert kode == 400 and "tidak boleh diubah" in hasil["pesan"]

    kode, hasil = _post_json(
        f"{dasar}/api/konfigurasi", {"pasangan": {"MIN_SALARY": "-5"}}
    )
    assert kode == 400
    # Nilai lama tidak berubah saat input ditolak.
    assert "MIN_SALARY=4500000" in berkas_env.read_text(encoding="utf-8")


def test_halaman_memuat_kontrol_baru():
    for bagian in ("api/riwayat", "api/lowongan", "api/konfigurasi",
                   "Simpan konfigurasi", "Detail lowongan"):
        assert bagian in dashboard.HALAMAN


# ------------------------------------------------------------ skrip halaman --
def _skrip() -> str:
    import re

    return re.search(r"<script>(.*)</script>", dashboard.HALAMAN, re.S).group(1)


def _galat_kutip(js: str) -> list:
    """Cari string JS yang terputus baris (bug yang membuat halaman kosong)."""
    galat = []
    kutip = None
    for nomor, baris in enumerate(js.splitlines(), 1):
        i = 0
        while i < len(baris):
            huruf = baris[i]
            if kutip:
                if huruf == "\\":
                    i += 2
                    continue
                if huruf == kutip:
                    kutip = None
            elif huruf in "'\"`":
                kutip = huruf
            i += 1
        if kutip in ("'", '"'):
            galat.append((nomor, baris.strip()))
            kutip = None
    return galat


def test_skrip_halaman_tidak_punya_string_terputus():
    galat = _galat_kutip(_skrip())

    assert not galat, f"String JS terputus di baris: {galat}"


def test_id_yang_dipakai_skrip_ada_di_halaman():
    import re

    js = _skrip()
    dipakai = set(re.findall(r"getElementById\('([^']+)'\)", js))
    js = js.replace('\\"', '"')
    for nama in dipakai:
        assert f'id="{nama}"' in dashboard.HALAMAN, f'tidak ada id="{nama}"'


def test_join_baris_memakai_nl():
    js = _skrip()

    assert "const NL=String.fromCharCode(10);" in dashboard.HALAMAN
    assert ".join(NL)" in js
    # String literal berisi escape newline tidak dipakai lagi.
    assert ".join('\\n')" not in js


def test_status_memuat_konfigurasi_untuk_form(siap):
    data = dashboard.status()

    konf = data["konfigurasi"]
    assert set(konf) == {
        "MIN_SALARY", "MAX_APPLY_PER_DAY", "MAX_AGE_DAYS",
        "LOCATIONS", "PRIORITAS_LOKASI",
    }
    assert isinstance(konf["MIN_SALARY"], int)
    assert isinstance(konf["LOCATIONS"], str)


def test_port_terpakai_diberi_pesan_jelas(capsys):
    """Port bentrok tidak boleh membuat pengguna menunggu tanpa penjelasan."""
    penjaga = dashboard.buat_server(0, "127.0.0.1")
    try:
        dashboard.jalankan(penjaga.server_port, "127.0.0.1", buka_browser=False)
    finally:
        penjaga.server_close()

    pesan = capsys.readouterr().out
    assert "sedang dipakai" in pesan
    assert "--port" in pesan


def test_aksi_menerima_nama_alternatif():
    """Nama tombol versi Inggris/Indonesia sama-sama dikenali."""
    import dashboard as dashboard_modul

    for nama in ("resume", "continue"):
        hasil = dashboard_modul.aksi(nama)
        assert hasil["ok"] is True, nama
        assert "lanjut" in hasil["pesan"], nama
