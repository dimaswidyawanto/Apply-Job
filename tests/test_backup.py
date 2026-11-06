"""Backup & pemulihan database (master prompt pasal 12)."""

import pytest

import backup
from database import Database


@pytest.fixture
def db_berisi(tmp_path):
    jalur = tmp_path / "data.db"
    database = Database(str(jalur))
    database.add_job(
        {
            "job_id": "js-1",
            "title": "Inventory Control",
            "company": "PT Contoh",
            "url": "https://id.jobstreet.com/job/1",
        }
    )
    database.record_application("js-1")
    return database, jalur


def test_backup_membuat_salinan_dan_daftar(db_berisi, tmp_path):
    database, jalur = db_berisi
    folder = tmp_path / "backups"

    berkas = backup.buat(str(jalur), folder)

    assert berkas.exists()
    assert berkas.name.startswith(backup.AWALAN)
    assert berkas.stat().st_size > 0

    isi = backup.daftar(folder)
    assert len(isi) == 1
    assert isi[0]["nama"] == berkas.name
    assert isi[0]["ukuran"] > 0


def test_database_belum_ada_ditolak(tmp_path):
    with pytest.raises(FileNotFoundError):
        backup.buat(str(tmp_path / "tidak-ada.db"), tmp_path / "backups")


def test_pulihkan_mengembalikan_data(db_berisi, tmp_path):
    database, jalur = db_berisi
    folder = tmp_path / "backups"
    berkas = backup.buat(str(jalur), folder)

    # Data setelah backup "hilang" karena kerusakan/penghapusan.
    database.add_job(
        {
            "job_id": "js-2",
            "title": "Staf Gudang",
            "company": "PT Lain",
            "url": "https://id.jobstreet.com/job/2",
        }
    )
    jalur.unlink()

    sasaran = backup.pulihkan(berkas.name, str(jalur), folder)

    assert sasaran == jalur
    pulih = Database(str(jalur))
    assert pulih.get_job("js-1") is not None
    # Data yang dibuat SETELAH backup tidak ikut kembali.
    assert pulih.get_job("js-2") is None


def test_database_lama_disimpan_sebagai_bak(db_berisi, tmp_path):
    _, jalur = db_berisi
    folder = tmp_path / "backups"
    berkas = backup.buat(str(jalur), folder)

    backup.pulihkan(berkas.name, str(jalur), folder)

    assert jalur.with_suffix(jalur.suffix + ".bak").exists()


def test_nama_bukan_database_ditolak(db_berisi, tmp_path):
    _, jalur = db_berisi
    folder = tmp_path / "backups"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "palsu.db").write_text("bukan database", encoding="utf-8")

    with pytest.raises(ValueError):
        backup.pulihkan("palsu.db", str(jalur), folder)


def test_nama_tidak_ditemukan(db_berisi, tmp_path):
    _, jalur = db_berisi

    with pytest.raises(FileNotFoundError):
        backup.pulihkan("tidak-ada.db", str(jalur), tmp_path / "backups")


def test_nama_berisi_path_tidak_bisa_keluar_folder(db_berisi, tmp_path):
    _, jalur = db_berisi
    folder = tmp_path / "backups"
    berkas = backup.buat(str(jalur), folder)

    # "../<nama>" dirapikan menjadi nama berkas saja DI DALAM folder backup,
    # jadi berkas di luar folder tidak pernah tersentuh.
    luar = tmp_path / berkas.name
    luar.write_text("jangan dipakai", encoding="utf-8")

    backup.pulihkan(f"../{berkas.name}", str(jalur), folder)

    assert luar.read_text(encoding="utf-8") == "jangan dipakai"


def test_backup_lama_dipangkas(db_berisi, tmp_path, monkeypatch):
    _, jalur = db_berisi
    folder = tmp_path / "backups"
    monkeypatch.setattr(backup, "MAKS_SIMPAN", 2)

    for _ in range(4):
        backup.buat(str(jalur), folder)

    assert len(backup.daftar(folder)) == 2
