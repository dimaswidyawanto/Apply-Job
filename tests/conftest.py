"""Pengaturan bersama untuk seluruh tes.

Tes tidak boleh menyentuh `jobstreet_auto.db` milik pengguna: semua modul
memakai satu objek `database.db`, jadi cukup mengarahkan `db_path` ke berkas
sementara. Dengan begitu menjalankan tes tidak pernah mengubah data asli
(kuota, riwayat lamaran, tabel sesi).
"""

import pytest

import database


@pytest.fixture(autouse=True)
def _database_sementara(tmp_path, monkeypatch):
    """Arahkan database ke berkas sementara untuk setiap tes."""
    asli = database.db.db_path
    sementara = tmp_path / "tes.db"

    monkeypatch.setattr(database.db, "db_path", str(sementara))
    database.db._conn = None
    database.db._init_db()

    yield

    with database.db._lock:
        if database.db._conn is not None:
            database.db._conn.close()
            database.db._conn = None

    database.db.db_path = asli
    database.db._init_db()
