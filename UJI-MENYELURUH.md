# Uji Menyeluruh — Seluruh Sistem

Dijalankan: **2026-11-07** · Komit awal `f74fe5a` · Lingkungan: sandbox Linux, Python 3.11
(Tanpa Chrome, tanpa Windows, tanpa sesi login JobStreet/Glints/Indeed.)

Perintah yang diuji: **22 subperintah CLI**, **6 endpoint dashboard**, **6 aksi dashboard**,
**6 skenario simulasi lamaran**, seluruh **berkas tes**.

---

## 1. Ringkasan hasil

| Pemeriksaan | Hasil |
|---|---|
| Berkas tes (`pytest`) | **579 passed, 1 skipped** (67,5 detik) |
| Gerbang gaya kode (`ruff --select E9,F,E501,I,B,SIM,ISC`) | **bersih** |
| Kompilasi seluruh modul (`compileall`) | **berhasil, tanpa galat** |
| Subperintah CLI | **22 dijalankan**, semuanya keluar dengan kode 0 (setelah 1 perbaikan, lihat bagian 4) |
| Endpoint dashboard | **6 diuji**, semua sesuai harapan (200/404 tepat) |
| Aksi dashboard | **6 diuji** (start, pause, lanjut, stop, retry, clear) |
| Simulasi alur lamaran | **6 skenario, semua "OK"** |
| Sesi nyata lewat dashboard | berjalan penuh sampai menulis laporan & menyimpan statistik sesi |

---

## 2. Subperintah CLI yang dijalankan

Semua memakai salinan database (`/tmp/uji/db.db`) supaya data asli tidak tersentuh.

| Perintah | Kode keluar | Ringkasan hasil |
|---|---|---|
| `config` | 0 | 7 lokasi, 14 kata kunci, logo wajib, gaji ≥ Rp4.500.000, kuota 50, riset 3 halaman, retry 2× |
| `stats` | 0 | 1 lowongan tersimpan, 0 lamaran |
| `simulasi` | 0 | 6 skenario lamaran sesuai harapan |
| `repair` | 0 | 0 data rusak (judul, perusahaan, status, lamaran ganda) |
| `laporan` | 0 | angka kinerja, status antrean, per lokasi/kata kunci/sumber |
| `laporan --simpan` | 0 | `reports/laporan-2026-11-06.md` ditulis |
| `antrean --limit 5` | 0 | sebaran status + daftar yang perlu ditinjau |
| `history --limit 5` | 0 | "Belum ada lamaran" (benar, belum ada lamaran) |
| `jawaban` | 0 | 4–5 ingatan jawaban beserta jumlah pemakaian |
| `jawaban --isi` | 0 | menambah jawaban manual |
| `blacklist` (tanpa argumen) | 0 | **baru:** menampilkan daftar blacklist |
| `blacklist --hapus` | 0 | **baru:** menghapus perusahaan dari blacklist |
| `backup` | 0 | berkas backup 64 KB dibuat |
| `backup --daftar` | 0 | 2 backup terdaftar |
| `cv` (tanpa CV) | 0 | pesan jelas: `CV_PATH` belum diisi |
| `cv --path …` | 0 | pengalaman **8 tahun**, pendidikan S1, 12 keterampilan, alat, sertifikasi |
| `perbarui-env` | 0 | 11 kunci disegarkan dari `.env.example` |
| `set-env MAX_APPLY_PER_DAY=50` | 0 | `.env` diubah + cadangan `.env.bak` |
| `performa` | 0 | DB 0 ms, tulis 1 MB 2 ms, dashboard 38 ms, jaringan 3 situs 13–14 ms |
| `run`, `glints`, `indeed`, `cek-logo`, `uji-lamar`, `perbaiki-chrome`, `lamar`, `dashboard` | 0 | bantuan perintah tampil benar (butuh Chrome untuk benar-benar jalan) |

## 3. Dashboard (live, port 8765)

| Permintaan | Status | Catatan |
|---|---|---|
| `GET /` | 200 · 7.178 B | halaman + panel Sesi terakhir |
| `GET /api/status` | 200 | kuota, ringkasan, `sesi_terakhir`, `statistik_sesi`, log |
| `GET /api/riwayat?limit=5` | 200 | riwayat lamaran |
| `GET /api/lowongan?job_id=…` | 200 | detail lowongan + riwayatnya |
| `GET /api/lowongan?job_id=tidak-ada` | 404 | pesan jelas |
| `GET /api/tidak-ada` | 404 | pesan jelas |
| `POST /api/aksi?aksi=pause` | ok | berkas kendali berisi `jeda` |
| `POST /api/aksi?aksi=lanjut` | ok | sesi lanjut |
| `POST /api/aksi?aksi=retry` | ok | 0 lowongan gagal dikembalikan |
| `POST /api/aksi?aksi=clear` | ditolak | benar: butuh konfirmasi |
| `POST /api/aksi?aksi=clear&konfirmasi=1` | ok | 1 lowongan dihapus |
| `POST /api/konfigurasi` | ok | `MIN_SALARY` tersimpan, `.env.bak` dibuat |
| `POST /api/aksi?aksi=start` | ok | sesi dijalankan penuh (lihat bagian 5) |

## 4. Empat cacat yang ditemukan saat menjalankan — sudah diperbaiki

Menjalankan seluruh sistem menemukan empat hal yang tidak terlihat dari tes saja:

| # | Temuan | Dampak bagi Anda | Perbaikan |
|---|---|---|---|
| 1 | `blacklist` tanpa argumen berhenti dengan galat argparse | daftar hitam tidak bisa ditinjau; salah masuk = tidak bisa dibatalkan dari terminal | `blacklist` tanpa argumen menampilkan tabel; ada `--hapus "Nama PT"`; metode `hapus_blacklist()` |
| 2 | Pengalaman CV hanya terbaca dari tulisan "N tahun", bukan rentang tanggal | CV Indonesia umumnya menulis "2020-2024" → skor 6 parameter tidak memakai pengalaman | `pengalaman_dari_rentang()`: menggabungkan rentang (anti-hitung-ganda), mengenali "sekarang/present", mengabaikan baris pendidikan. CV contoh: **0 → 8 tahun** |
| 3 | Nama aplikasi (SAP, Excel) ditampilkan sebagai "Sertifikasi" | profil CV menyesatkan saat ditinjau | dipisah: **Alat / software** (SAP, ERP, Excel, WMS) vs **Sertifikasi** (ISO, Six Sigma, K3, BNSP); "k3"/"ahli k3" tidak dobel |
| 4 | Aksi API `resume` ditolak (hanya `lanjut` yang sah) | integrasi/otomatisasi pihak ketiga membingungkan | alias diterima: `resume`, `continue`, `mulai`, `jeda`, `berhenti`, `ulangi`, `bersihkan` |

Tes baru: **8** (`test_blacklist_bisa_dilihat_dan_dihapus`, 6 tes CV, 1 tes aksi dashboard) → total **579**.

## 5. Bukti sesi nyata (bukan tiruan)

Tombol **Start** dashboard benar-benar menjalankan `cli.py lamar` sebagai proses terpisah.
Di sandbox tidak ada Chrome, jadi sesi berhenti dengan pesan jujur:

```
Unable to obtain driver for chrome ...
Total terkirim sesi ini: 0
Kuota harian: 0 sudah dilamar hari ini, sisa 50 dari 50.
Laporan harian disimpan: reports/laporan-2026-11-06.md
```

Yang penting: jalur lengkapnya terbukti bekerja — kuota diperiksa, antrean diproses,
kegagalan dicatat, laporan ditulis, dan **statistik sesi tersimpan ke database**:

| Situs | Ditemukan | Dilamar | Gagal | Diulang | Durasi |
|---|---|---|---|---|---|
| jobstreet | 0 | 0 | 1 | 0 | 0,1 dtk |
| jobstreet | 0 | 0 | 2 | 0 | 0,3 dtk |

## 6. Batas yang tetap jujur

- **Chrome/Selenium sungguhan, login, dan Cloudflare** hanya bisa diuji di PC Anda.
- **Windows**: `.bat` sudah diverifikasi strukturnya (14 berkas, 100% CRLF, `tarik.bat` tanpa `goto`), tetapi eksekusinya tidak bisa dijalankan di Linux.
- **Task Scheduler** untuk laporan harian belum dipasang otomatis (masih satu langkah manual di README).
- Angka di atas berasal dari sandbox dengan database salinan; hasil di PC Anda akan berbeda isinya, bukan berbeda perilakunya.
