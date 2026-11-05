"""Akses database SQLite untuk lowongan, lamaran, dan blacklist."""

import sqlite3
import threading
from contextlib import contextmanager, suppress

from config import config

# Status yang dianggap "lowongan sudah pernah dilamar".
APPLIED_STATUSES = ("applied", "already_applied")

# Status yang memakan kuota harian (hanya lamaran yang dikirim alat ini).
QUOTA_STATUSES = ("applied",)

TITLE_FALLBACK = "(judul tidak tersedia)"


def _nilai_logo(nilai) -> int | None:
    """True/False -> 1/0; tidak diketahui (mis. dari situs lain) -> NULL."""
    if nilai is None:
        return None
    return 1 if nilai else 0


class Database:
    def __init__(self, db_path: str | None = None):
        # Path absolut supaya database tidak "hilang" ketika program
        # dijalankan dari folder kerja yang berbeda.
        self.db_path = str(db_path or config.db_path)
        self._conn = None
        self._lock = threading.Lock()
        self._init_db()
        self._aktifkan_wal()

    def _aktifkan_wal(self):
        """WAL + synchronous NORMAL: tulis jauh lebih cepat, tetap aman.

        Tanpa ini setiap simpanan menunggu fsync penuh (puluhan ms), sehingga
        sesi dengan ratusan lowongan terasa lambat.
        """
        try:
            conn = self._koneksi()
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.commit()
        except sqlite3.Error:
            pass

    def _koneksi(self):
        """Satu koneksi yang dipakai ulang.

        Membuat koneksi baru untuk setiap query memakan ~1 ms per operasi —
        pada sesi berisi ratusan lowongan itu jadi beberapa detik terbuang.
        """
        if self._conn is None:
            self._conn = sqlite3.connect(
                self.db_path, check_same_thread=False
            )
            self._conn.row_factory = sqlite3.Row
        return self._conn

    @contextmanager
    def _get_conn(self):
        with self._lock:
            conn = self._koneksi()

            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise


    def _init_db(self):
        with self._get_conn() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT UNIQUE NOT NULL,
                    title TEXT NOT NULL,
                    company TEXT,
                    location TEXT,
                    salary TEXT,
                    description TEXT,
                    url TEXT NOT NULL,
                    date_posted TEXT,
                    has_logo INTEGER,
                    logo_src TEXT,
                    date_scraped TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS applications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL,
                    status TEXT DEFAULT 'applied',
                    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    response TEXT,
                    notes TEXT
                );

                CREATE TABLE IF NOT EXISTS blacklist (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    company_name TEXT UNIQUE NOT NULL,
                    reason TEXT,
                    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_applications_job_id
                    ON applications (job_id);
                CREATE INDEX IF NOT EXISTS idx_applications_status
                    ON applications (status);
                CREATE INDEX IF NOT EXISTS idx_applications_applied_at
                    ON applications (applied_at);
                """
            )
            self._migrate(conn)

    @staticmethod
    def _migrate(conn):
        """Menambahkan kolom yang belum ada pada database versi lama."""
        columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(applications)")
        }

        for column, definition in (
            ("response", "TEXT"),
            ("notes", "TEXT"),
        ):
            if column not in columns:
                conn.execute(
                    f"ALTER TABLE applications ADD COLUMN {column} {definition}"
                )

        # Kolom tambahan pada tabel lowongan (database versi lama belum punya).
        job_columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(jobs)")
        }

        for column, definition in (
            ("has_logo", "INTEGER"),
            ("logo_src", "TEXT"),
        ):
            if column not in job_columns:
                conn.execute(
                    f"ALTER TABLE jobs ADD COLUMN {column} {definition}"
                )

    # ------------------------------------------------------------------
    # Lowongan
    # ------------------------------------------------------------------
    def add_job(self, job_data: dict) -> bool:
        """Menyimpan lowongan. Data yang tidak lengkap ditolak."""
        job_id = str(job_data.get("job_id") or "").strip()
        title = str(job_data.get("title") or "").strip()
        url = str(job_data.get("url") or "").strip()

        # Jangan pernah menyimpan lowongan tanpa judul/URL/ID: baris
        # seperti itu tidak bisa dipakai dan hanya mengotori database.
        if not job_id or not title or not url:
            return False

        with self._get_conn() as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO jobs (
                        job_id, title, company, location,
                        salary, description, url, date_posted,
                        has_logo, logo_src
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        job_id,
                        title,
                        str(job_data.get("company") or ""),
                        str(job_data.get("location") or ""),
                        str(job_data.get("salary") or ""),
                        str(job_data.get("description") or ""),
                        url,
                        str(job_data.get("date_posted") or ""),
                        _nilai_logo(job_data.get("has_logo")),
                        str(job_data.get("logo_src") or ""),
                    ),
                )
                return True
            except sqlite3.IntegrityError:
                return False

    def get_job(self, job_id: str) -> dict | None:
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM jobs WHERE job_id = ? LIMIT 1", (job_id,)
            ).fetchone()

        return dict(row) if row else None

    # ------------------------------------------------------------------
    # Lamaran
    # ------------------------------------------------------------------
    def is_already_applied(self, job_id: str) -> bool:
        """Status 'applied' maupun 'already_applied' dihitung sudah melamar."""
        job_id = str(job_id or "").strip()

        if not job_id:
            return False

        placeholders = ", ".join("?" for _ in APPLIED_STATUSES)

        with self._get_conn() as conn:
            result = conn.execute(
                f"""
                SELECT 1
                FROM applications
                WHERE job_id = ? AND status IN ({placeholders})
                LIMIT 1
                """,
                (job_id, *APPLIED_STATUSES),
            ).fetchone()

            return result is not None

    def record_application(
        self,
        job_id: str,
        status: str = "applied",
        notes: str = "",
    ):
        """Mencatat lamaran tanpa membuat baris ganda untuk job yang sama."""
        job_id = str(job_id or "").strip()
        status = str(status or "applied").strip().lower() or "applied"

        if not job_id:
            return

        with self._get_conn() as conn:
            if status in APPLIED_STATUSES:
                # Job yang sama cukup dicatat sekali sebagai terkirim.
                placeholders = ", ".join("?" for _ in APPLIED_STATUSES)
                existing = conn.execute(
                    f"""
                    SELECT 1 FROM applications
                    WHERE job_id = ? AND status IN ({placeholders})
                    LIMIT 1
                    """,
                    (job_id, *APPLIED_STATUSES),
                ).fetchone()

                if existing:
                    return

            conn.execute(
                """
                INSERT INTO applications (job_id, status, notes)
                VALUES (?, ?, ?)
                """,
                (job_id, status, notes),
            )

    def get_today_apply_count(self) -> int:
        """Jumlah lamaran terkirim hari ini (dipakai untuk batas harian)."""
        placeholders = ", ".join("?" for _ in QUOTA_STATUSES)

        with self._get_conn() as conn:
            result = conn.execute(
                f"""
                SELECT COUNT(*) AS count
                FROM applications
                WHERE DATE(applied_at, 'localtime') = DATE('now', 'localtime')
                  AND status IN ({placeholders})
                """,
                QUOTA_STATUSES,
            ).fetchone()

            return int(result["count"])

    def get_recent_applications(self, limit: int = 50) -> list[dict]:
        """Riwayat lamaran; judul/perusahaan kosong diberi teks pengganti."""
        limit = max(1, int(limit))

        with self._get_conn() as conn:
            rows = conn.execute(
                """
                SELECT a.applied_at,
                       COALESCE(NULLIF(TRIM(j.title), ''), ?) AS title,
                       COALESCE(NULLIF(TRIM(j.company), ''), 'Tidak diketahui')
                           AS company,
                       a.status,
                       COALESCE(j.url, '') AS url
                FROM applications a
                LEFT JOIN jobs j ON a.job_id = j.job_id
                ORDER BY a.applied_at DESC, a.id DESC
                LIMIT ?
                """,
                (TITLE_FALLBACK, limit),
            ).fetchall()

        result = []
        for row in rows:
            item = dict(row)
            item["applied_at"] = str(item.get("applied_at") or "")
            result.append(item)

        return result

    # ------------------------------------------------------------------
    # Blacklist
    # ------------------------------------------------------------------
    def is_blacklisted(self, company_name: str) -> bool:
        company_name = str(company_name or "").strip()

        if not company_name:
            return False

        with self._get_conn() as conn:
            result = conn.execute(
                "SELECT 1 FROM blacklist WHERE company_name = ? LIMIT 1",
                (company_name,),
            ).fetchone()

            return result is not None

    def get_blacklist(self) -> list[dict]:
        """Semua perusahaan yang dikecualikan beserta alasannya."""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT company_name, reason FROM blacklist ORDER BY company_name"
            ).fetchall()

        return [dict(row) for row in rows]

    def add_blacklist(self, company_name: str, reason: str = ""):
        company_name = str(company_name or "").strip()

        if not company_name:
            return

        with self._get_conn() as conn, suppress(sqlite3.IntegrityError):
            conn.execute(
                """
                    INSERT INTO blacklist (company_name, reason)
                    VALUES (?, ?)
                    """,
                (company_name, reason),
            )

    # ------------------------------------------------------------------
    # Statistik & perbaikan data
    # ------------------------------------------------------------------
    def get_stats(self) -> dict:
        placeholders = ", ".join("?" for _ in APPLIED_STATUSES)

        with self._get_conn() as conn:
            total_jobs = conn.execute(
                "SELECT COUNT(*) AS count FROM jobs"
            ).fetchone()["count"]

            total_applied = conn.execute(
                f"""
                SELECT COUNT(*) AS count
                FROM applications
                WHERE status IN ({placeholders})
                """,
                APPLIED_STATUSES,
            ).fetchone()["count"]

            today_applied = conn.execute(
                f"""
                SELECT COUNT(*) AS count
                FROM applications
                WHERE DATE(applied_at, 'localtime') = DATE('now', 'localtime')
                  AND status IN ({placeholders})
                """,
                APPLIED_STATUSES,
            ).fetchone()["count"]

            return {
                "total_jobs_found": int(total_jobs),
                "total_applied": int(total_applied),
                "today_applied": int(today_applied),
            }

    def repair_data(self) -> dict:
        """Merapikan data lama tanpa menghapus lowongan.

        - Judul/perusahaan/lokasi kosong diisi teks pengganti.
        - Status lamaran dinormalkan (huruf kecil, tanpa spasi).
        - Baris lamaran ganda untuk job yang sama dihapus.
        """
        report = {
            "empty_titles_fixed": 0,
            "empty_companies_fixed": 0,
            "statuses_normalized": 0,
            "duplicate_applications_removed": 0,
        }

        with self._get_conn() as conn:
            cursor = conn.execute(
                """
                UPDATE jobs
                SET title = ?
                WHERE title IS NULL OR TRIM(title) = ''
                """,
                (TITLE_FALLBACK,),
            )
            report["empty_titles_fixed"] = cursor.rowcount

            cursor = conn.execute(
                """
                UPDATE jobs
                SET company = 'Tidak diketahui'
                WHERE company IS NULL OR TRIM(company) = ''
                """
            )
            report["empty_companies_fixed"] = cursor.rowcount

            cursor = conn.execute(
                """
                UPDATE applications
                SET status = LOWER(TRIM(status))
                WHERE status IS NOT NULL
                  AND status <> LOWER(TRIM(status))
                """
            )
            report["statuses_normalized"] = cursor.rowcount

            placeholders = ", ".join("?" for _ in APPLIED_STATUSES)
            cursor = conn.execute(
                f"""
                DELETE FROM applications
                WHERE status IN ({placeholders})
                  AND id NOT IN (
                      SELECT MIN(id) FROM applications
                      WHERE status IN ({placeholders})
                      GROUP BY job_id
                  )
                """,
                (*APPLIED_STATUSES, *APPLIED_STATUSES),
            )
            report["duplicate_applications_removed"] = max(0, cursor.rowcount)

        return report


db = Database()
