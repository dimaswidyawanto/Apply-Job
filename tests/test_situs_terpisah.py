"""Pemisahan situs: JobStreet, Glints, dan Indeed tidak saling mengganggu.

Permintaan pemakai: mengerjakan Glints/Indeed tidak boleh mengubah data
JobStreet yang sudah selesai. Karena itu:

- `run` tanpa `--situs` tetap JobStreet saja (perilaku lama dipertahankan),
- `run --situs glints` hanya membuka Glints,
- riwayat/antrean/status bisa dilihat per situs.
"""

import pytest

from database import Database
from lamar_semua import NAMA_SITUS, situs_terpilih


# ------------------------------------------------------------ pilihan situs ---
@pytest.mark.parametrize(
    "teks, expected",
    [
        ("", ["jobstreet", "glints", "indeed"]),
        ("glints", ["glints"]),
        ("indeed", ["indeed"]),
        ("glints,indeed", ["glints", "indeed"]),
        ("semua", ["jobstreet", "glints", "indeed"]),
        ("glints,jobstreet", ["jobstreet", "glints"]),
        ("", None),
    ],
)
def test_pilihan_situs(monkeypatch, teks, expected):
    if expected is None:
        monkeypatch.setattr(
            "config.config.situs_aktif", "glints", raising=False
        )
        assert situs_terpilih("") == ["glints"]
        return

    assert situs_terpilih(teks) == expected


def test_situs_tak_dikenal_diabaikan():
    assert situs_terpilih("glints,tokopedia") == ["glints"]
    assert situs_terpilih("tokopedia") == []


def test_nama_situs_lengkap():
    assert NAMA_SITUS == {
        "jobstreet": "JobStreet",
        "glints": "Glints",
        "indeed": "Indeed",
    }


# -------------------------------------------------------- data per situs ---
@pytest.fixture
def database(tmp_path):
    return Database(str(tmp_path / "situs.db"))


def _job(nama_situs: str, job_id: str, status: str) -> dict:
    host = {
        "jobstreet": "https://id.jobstreet.com/job/",
        "glints": "https://glints.com/id/opportunities/jobs/x/",
        "indeed": "https://id.indeed.com/viewjob?jk=",
    }[nama_situs]
    return {
        "job_id": job_id,
        "title": f"{nama_situs} {job_id}",
        "company": "PT Contoh",
        "location": "Bandung",
        "salary": "",
        "description": "",
        "url": host + job_id,
        "date_posted": "Hari ini",
        "sumber": nama_situs,
        "status_antrean": status,
    }


def test_ringkasan_per_situs_dipisah(database):
    database.add_job(_job("jobstreet", "js1", "applied"))
    database.add_job(_job("jobstreet", "js2", "applied"))
    database.add_job(_job("glints", "gl1", "review_required"))
    database.add_job(_job("indeed", "in1", "applied"))

    ringkas = {baris["situs"]: baris for baris in database.ringkasan_per_situs()}

    assert ringkas["jobstreet"]["total"] == 2
    assert ringkas["jobstreet"]["terkirim"] == 2
    assert ringkas["glints"]["total"] == 1
    assert ringkas["glints"]["terkirim"] == 0
    assert ringkas["glints"]["perlu_manual"] == 1
    assert ringkas["indeed"]["total"] == 1
    assert ringkas["indeed"]["terkirim"] == 1


def test_situs_ditebak_dari_url_bila_kolom_kosong(database):
    job = _job("glints", "gl2", "applied")
    job["sumber"] = ""
    database.add_job(job)

    ringkas = {baris["situs"]: baris for baris in database.ringkasan_per_situs()}

    assert ringkas["glints"]["total"] == 1
    assert "jobstreet" not in ringkas


def test_hitung_status_antrean_per_situs(database):
    database.add_job(_job("jobstreet", "js1", "applied"))
    database.add_job(_job("glints", "gl1", "rejected"))

    semua = database.hitung_status_antrean()
    glints = database.hitung_status_antrean("glints")

    assert semua["applied"] == 1
    assert semua["rejected"] == 1
    assert glints["applied"] == 0
    assert glints["rejected"] == 1


def test_riwayat_lamaran_per_situs(database):
    database.add_job(_job("jobstreet", "js1", "applied"))
    database.add_job(_job("glints", "gl1", "applied"))
    database.record_application("js1", "applied", "uji")
    database.record_application("gl1", "applied", "uji")

    semua = database.get_recent_applications(10)
    glints = database.get_recent_applications(10, situs="glints")

    assert len(semua) == 2
    assert [baris["title"] for baris in glints] == ["glints gl1"]


# ------------------------------------------------------- perintah `run` ---
def test_run_bawaan_hanya_jobstreet(monkeypatch):
    import cli
    import main

    dipanggil = {}

    def palsu(fungsi, *a, **k):
        dipanggil["fungsi"] = fungsi

    monkeypatch.setattr(cli, "jalankan_terkunci", palsu)
    cli.jalankan_run()

    assert dipanggil["fungsi"] is main.main


def test_run_situs_glints_tidak_menyentuh_jobstreet(monkeypatch):
    import cli

    diminta = {}

    def palsu(situs, max_pages=0, batas=0, perbarui=True):
        diminta["situs"] = situs
        diminta["perbarui"] = perbarui

    monkeypatch.setattr(cli, "lamar_semua_situs", palsu)
    cli.jalankan_run("glints", 2)

    assert diminta == {"situs": "glints", "perbarui": False}


def test_run_situs_semua_diteruskan(monkeypatch):
    import cli

    diminta = {}
    monkeypatch.setattr(
        cli,
        "lamar_semua_situs",
        lambda situs, max_pages=0, batas=0, perbarui=True: diminta.update(
            situs=situs
        ),
    )
    cli.jalankan_run("semua")

    assert diminta["situs"] == "jobstreet,glints,indeed"


def test_run_situs_tak_dikenal_dihentikan(monkeypatch):
    import cli

    monkeypatch.setattr(
        cli, "lamar_semua_situs", lambda *a, **k: pytest.fail("tidak boleh jalan")
    )

    with pytest.raises(SystemExit):
        cli.jalankan_run("tokopedia")
