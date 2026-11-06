"""Evaluasi kata kunci & sumber (master prompt pasal 12.4).

Setiap lowongan mencatat situs asalnya dan kata kunci yang menemukannya,
sehingga laporan bisa menunjukkan mana yang produktif — tanpa mengubah
aturan apa pun secara otomatis.
"""

import pytest

import laporan
from database import Database, sumber_dari_url


@pytest.fixture
def db(tmp_path, monkeypatch):
    basis = Database(str(tmp_path / "eval.db"))
    monkeypatch.setattr(laporan, "db", basis)
    return basis


def tambah(db, job_id, url, kata_kunci="", status="found"):
    db.add_job({
        "job_id": job_id,
        "title": "Inventory Staff",
        "company": "PT Contoh",
        "location": "Bandung",
        "url": url,
        "kata_kunci": kata_kunci,
    })
    if status != "found":
        db.set_status_antrean(job_id, status)


def test_sumber_dibaca_dari_url():
    assert sumber_dari_url("https://id.jobstreet.com/job/1") == "jobstreet"
    assert sumber_dari_url("https://glints.com/id/x") == "glints"
    assert sumber_dari_url("https://id.indeed.com/viewjob?jk=1") == "indeed"
    assert sumber_dari_url("https://www.linkedin.com/jobs/1") == "linkedin"
    assert sumber_dari_url("") == "lainnya"


def test_add_job_menyimpan_sumber_dan_kata_kunci(db):
    tambah(db, "js-1", "https://id.jobstreet.com/job/1", "inventory")

    job = db.get_job("js-1")
    assert job["sumber"] == "jobstreet"
    assert job["kata_kunci"] == "inventory"


def test_statistik_kata_kunci_dan_sumber(db):
    tambah(db, "a", "https://id.jobstreet.com/job/a", "inventory", "applied")
    tambah(db, "b", "https://id.jobstreet.com/job/b", "inventory")
    tambah(db, "c", "https://glints.com/id/c", "ppic")
    tambah(db, "d", "https://id.indeed.com/viewjob?jk=d", "")

    kk = {i["kata_kunci"]: i for i in db.statistik_kata_kunci()}
    assert kk["inventory"]["jumlah"] == 2
    assert kk["inventory"]["dilamar"] == 1
    assert kk["ppic"]["jumlah"] == 1
    assert kk["(tidak dicatat)"]["jumlah"] == 1

    sumber = {i["sumber"]: i for i in db.statistik_sumber()}
    assert sumber["jobstreet"]["jumlah"] == 2
    assert sumber["jobstreet"]["dilamar"] == 1
    assert sumber["glints"]["jumlah"] == 1


def test_ringkasan_laporan_memuat_kata_kunci_dan_sumber(db):
    tambah(db, "a", "https://id.jobstreet.com/job/a", "inventory", "applied")
    tambah(db, "b", "https://glints.com/id/b", "ppic")

    data = laporan.ringkasan()

    assert data["per_kata_kunci"]
    assert data["per_sumber"]
    assert {i["sumber"] for i in data["per_sumber"]} == {"jobstreet", "glints"}


def test_markdown_memuat_bagian_baru(db):
    tambah(db, "a", "https://id.jobstreet.com/job/a", "inventory", "applied")
    tambah(db, "b", "https://glints.com/id/b", "ppic")

    teks = laporan.teks_markdown(laporan.ringkasan())

    assert "## Per kata kunci" in teks
    assert "| inventory | 1 | 1 |" in teks
    assert "## Per sumber" in teks
    assert "| glints | 1 | 0 |" in teks


def test_saran_menunjukkan_kata_kunci_tanpa_hasil(db):
    for i in range(5):
        tambah(db, f"x{i}", f"https://id.jobstreet.com/job/x{i}", "stok gudang")
    tambah(db, "y", "https://id.jobstreet.com/job/y", "inventory", "applied")

    saran = laporan.saran(laporan.ringkasan())

    assert any("Kata kunci tanpa hasil lamaran" in s for s in saran)
    assert any("paling produktif" in s and "inventory" in s for s in saran)


def test_lowongan_lama_mendapat_sumber_saat_migrasi(tmp_path):
    """Database lama (tanpa kolom sumber) diisi otomatis dari URL-nya."""
    import sqlite3

    jalur = tmp_path / "lama.db"
    conn = sqlite3.connect(str(jalur))
    conn.executescript(
        """
        CREATE TABLE jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT UNIQUE NOT NULL,
            title TEXT NOT NULL,
            url TEXT NOT NULL
        );
        INSERT INTO jobs (job_id, title, url)
        VALUES ('old-1', 'Inventory Staff', 'https://id.jobstreet.com/job/old-1');
        """
    )
    conn.commit()
    conn.close()

    basis = Database(str(jalur))
    job = basis.get_job("old-1")

    assert job["sumber"] == "jobstreet"
