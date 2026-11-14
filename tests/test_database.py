import pytest

from database import TITLE_FALLBACK, Database


@pytest.fixture
def database(tmp_path):
    return Database(str(tmp_path / "test.db"))


def make_job(**overrides):
    job = {
        "job_id": "123",
        "title": "Inventory Control",
        "company": "PT Contoh",
        "location": "Bandung",
        "salary": "Rp 8.000.000",
        "description": "Deskripsi",
        "url": "https://id.jobstreet.com/job/123",
        "date_posted": "Hari ini",
    }
    job.update(overrides)
    return job


def test_add_job_menolak_data_tidak_lengkap(database):
    assert database.add_job(make_job(title="")) is False
    assert database.add_job(make_job(url="")) is False
    assert database.add_job(make_job(job_id="")) is False
    assert database.get_stats()["total_jobs_found"] == 0


def test_add_job_tidak_menduplikasi(database):
    assert database.add_job(make_job()) is True
    assert database.add_job(make_job()) is False
    assert database.get_stats()["total_jobs_found"] == 1


def test_record_application_tidak_dobel(database):
    database.add_job(make_job())
    database.record_application("123", "applied")
    database.record_application("123", "applied")
    database.record_application("123", "already_applied")

    assert database.get_stats()["total_applied"] == 1
    assert database.get_today_apply_count() == 1


def test_status_lama_already_applied_dihitung(database):
    database.add_job(make_job())
    database.record_application("123", "already_applied")

    assert database.is_already_applied("123") is True
    # Masuk statistik lamaran...
    assert database.get_stats()["total_applied"] == 1
    # ...tapi tidak memakan kuota harian (kuota hanya lamaran terkirim).
    assert database.get_today_apply_count() == 0


def test_kuota_harian_hanya_lamaran_terkirim(database):
    database.add_job(make_job(job_id="a"))
    database.add_job(make_job(job_id="b", url="https://contoh/b"))

    database.record_application("a", "applied")
    database.record_application("b", "already_applied")

    assert database.get_today_apply_count() == 1
    assert database.get_stats()["total_applied"] == 2


def test_status_ditolak_tidak_dihitung(database):
    database.add_job(make_job())
    database.record_application("123", "skipped")

    assert database.is_already_applied("123") is False
    assert database.get_today_apply_count() == 0


def test_is_already_applied_job_id_kosong(database):
    assert database.is_already_applied("") is False
    assert database.is_already_applied(None) is False


def test_repair_data(database):
    with database._get_conn() as conn:
        conn.execute(
            """
            INSERT INTO jobs (job_id, title, company, url)
            VALUES ('lama', '', '  ', 'https://contoh/lama')
            """
        )
        conn.execute(
            "INSERT INTO applications (job_id, status) VALUES ('lama', ' Applied ')"
        )
        conn.execute(
            "INSERT INTO applications (job_id, status) VALUES ('lama', 'applied')"
        )

    report = database.repair_data()

    assert report["empty_titles_fixed"] == 1
    assert report["empty_companies_fixed"] == 1
    assert report["statuses_normalized"] == 1
    assert report["duplicate_applications_removed"] == 1

    job = database.get_job("lama")
    assert job["title"] == TITLE_FALLBACK
    assert job["company"] == "Tidak diketahui"
    assert database.get_stats()["total_applied"] == 1


def test_riwayat_lamaran_tanpa_judul(database):
    with database._get_conn() as conn:
        conn.execute(
            """
            INSERT INTO jobs (job_id, title, company, url)
            VALUES ('kosong', '', '', 'https://contoh/kosong')
            """
        )
        conn.execute(
            "INSERT INTO applications (job_id, status) VALUES ('kosong', 'applied')"
        )

    rows = database.get_recent_applications()

    assert len(rows) == 1
    assert rows[0]["title"] == TITLE_FALLBACK
    assert rows[0]["company"] == "Tidak diketahui"


def test_blacklist(database):
    database.add_blacklist("PT Contoh", "tidak sesuai")
    database.add_blacklist("PT Contoh", "duplikat")

    assert database.is_blacklisted("PT Contoh") is True
    assert database.is_blacklisted("PT Lain") is False
    assert database.is_blacklisted("") is False


def test_blacklist_bisa_dilihat_dan_dihapus(database):
    """Blacklist harus bisa ditinjau balik, bukan sekali tambah langsung mati."""
    database.add_blacklist("PT Contoh", "tidak sesuai")
    database.add_blacklist("PT Lain", "outsourcing")

    daftar = database.get_blacklist()

    assert [item["company_name"] for item in daftar] == ["PT Contoh", "PT Lain"]
    assert daftar[0]["reason"] == "tidak sesuai"

    assert database.hapus_blacklist("PT Contoh") is True
    assert database.is_blacklisted("PT Contoh") is False
    assert [item["company_name"] for item in database.get_blacklist()] == ["PT Lain"]

    # Menghapus yang tidak ada: aman, tidak melempar galat.
    assert database.hapus_blacklist("PT Tidak Ada") is False
    assert database.hapus_blacklist("") is False


def test_migrasi_mengisi_status_dan_sumber(tmp_path):
    """Database lama tanpa kolom baru tetap terbaca dengan status 'found'."""
    import sqlite3

    from database import Database

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
        VALUES ('old-1', 'Inventory Staff', 'https://id.jobstreet.com/job/1');
        """
    )
    conn.commit()
    conn.close()

    basis = Database(str(jalur))
    job = basis.get_job("old-1")

    assert job["status_antrean"] == "found"
    assert job["sumber"] == "jobstreet"
    assert basis.hitung_status_antrean()["found"] == 1
    assert sum(basis.hitung_status_antrean().values()) == 1


def test_foreign_key_dipaksa_aktif(database):
    """E-5: koneksi harus memakai PRAGMA foreign_keys=ON.

    Skema sekarang belum memakai FOREIGN KEY, tetapi pengaturan ini mencegah
    baris yatim bila relasi ditambahkan di kemudian hari.
    """
    with database._get_conn() as conn:
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
