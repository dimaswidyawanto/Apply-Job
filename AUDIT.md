# Audit: Master Prompt vs Kondisi Kode Sekarang

Dibuat: 2026-11-06 · Cabang `arena/4ab2b9fa-dimastes`
Metode: pembacaan langsung kode (`config.py`, `job_filter.py`, `database.py`,
`main.py`, `glints.py`, `indeed.py`, `auto_apply.py`, `kuota.py`, `jawaban.py`),
bukan asumsi. Setiap baris menyebut letak buktinya.

Ringkasan: **fondasi pencarian–saring–peringkat–apply sudah ada dan berjalan**,
tetapi spesifikasi ini meminta beberapa lapisan yang **belum ada sama sekali**
(antrean 12 status, dashboard, pembacaan CV, skor berbobot persen, pembelajaran).

---

## 1. Konflik dengan aturan yang sudah ditetapkan lebih dulu

Tiga hal di spesifikasi ini **berlawanan langsung** dengan instruksi Anda
sebelumnya. Perlu keputusan Anda sebelum saya mengubah kode.

| # | Topik | Aturan Anda sebelumnya | Spesifikasi baru | Dampak bila diubah |
|---|---|---|---|---|
| K1 | Logo/gambar perusahaan | "Logo tidak dijadikan syarat; ada/tidaknya gambar tidak boleh menggagalkan lowongan" (diterapkan di JobStreet, Glints, Indeed) | Pasal 6.1: logo **wajib**; tanpa logo dikeluarkan dari klasifikasi; tidak pasti → `REVIEW_REQUIRED` | Lowongan tanpa logo kembali di-skip, termasuk di Indeed yang kartunya tidak memuat logo → nol lamaran di Indeed |
| K2 | Batas halaman riset | "Maksimal **5** halaman per kombinasi kata kunci × lokasi, tidak boleh lebih" (`config.MAKS_HALAMAN_RISET = 5`) | Pasal 3.2: maksimal **3** halaman | Riset turun ±40%, lowongan terkumpul lebih sedikit |
| K3 | Aturan gaji | `MIN_SALARY` (bawaan `0`), batas bawah rentang; `GLINTS_MIN_SALARY` sudah dihapus agar ketiga situs sama | Pasal 6.2: hanya gaji ≥ Rp4.500.000; rentang 4,0–6,0 jt **tidak** memenuhi | Bila `MIN_SALARY=4500000` diset, aturan berlaku otomatis tanpa ubah kode (sudah pakai batas bawah) |

---

## 2. Yang SUDAH ada dan berfungsi

| Pasal | Kebutuhan | Status | Bukti |
|---|---|---|---|
| 2.1 | Lokasi jamak lewat setelan | Ada | `config.locations`, `.env` `LOCATION` |
| 2.2 | Kategori dari daftar kata kunci | Sebagian | `config.keywords`, `title_keywords`, `research_keywords` |
| 3.1 | Urut terbaru | Ada | `sort=date` (Indeed), `sortmode=ListedDate` (JobStreet), "Baru Ditambahkan" (Glints) |
| 3.3 | Kumpulkan >50 tanpa batas | Ada | `research_max_jobs=0`; kuota hanya memotong saat apply (`kuota.py`) |
| 4.1 | Simpan data lowongan | Sebagian | tabel `jobs` (`database.py`:82) — tanpa kolom status antrean & alasan lolos/tidak |
| 4.2 | Status antrean | **Sebagian** | hanya status lamaran: `applied/already_applied/error/manual/failed`; belum ada FOUND→READY_TO_APPLY |
| 5 | Deteksi duplikat | Ada (dasar) | `kunci_duplikat` + `dedupe_jobs` (job_id, judul+perusahaan ternormalisasi) |
| 6.3 | Baca CV | **Belum** | tidak ada modul CV; profil diisi manual (`education_level`, `skill_keywords`, `max_experience`) |
| 7 | Skor kecocokan | Sebagian | 8 dimensi aditif (`job_filter.py`: skor posisi/lokasi/kualifikasi/pengalaman/pendidikan/keterampilan/tanggal/gaji), **bukan** 6 parameter berbobot persen |
| 8 | Ingatan formulir | Ada | `jawaban.py` (kunci normalisasi + `SequenceMatcher` 0.86, riwayat perubahan) |
| 9.1–9.2 | Batas 50/hari, lintas situs & lokasi | Ada | `kuota.py` (`MAX_APPLY_PER_DAY`), reset per tanggal lokal (`database.py`:363 `localtime` = WIB di PC Anda) |
| 9.3 | Verifikasi pengiriman | Sebagian | `auto_apply.py` mencocokkan teks sukses; ragu → `manual_required` |
| 9.4 | Isi formulir dari data valid | Ada | `auto_apply.py` + `jawaban.py` |
| 10 | Pemulihan otomatis | Sebagian | 4 percobaan driver, failover Chrome debug→profil, cek `already_applied` sebelum kirim |
| 13 | Keamanan data | Ada (dasar) | SQLite lokal, tanpa password tersimpan |
| 16.1 | Tes otomatis | Ada | `pytest` 452 tes hijau, `ruff` bersih |

---

## 3. Yang BELUM ada (pekerjaan baru)

| Pasal | Kebutuhan | Kondisi | Perkiraan usaha |
|---|---|---|---|
| 2.3 | Prioritas **lokasi × kategori** (tabel 5 baris contoh) | Tidak ada struktur data maupun urutan proses | Sedang — modul `prioritas.py` + dipakai 3 situs |
| 2.1 | Aktif/nonaktif lokasi tanpa hapus riwayat | Tidak ada | Kecil |
| 4.2 | 12 status antrean persisten | Tidak ada | Besar — tabel `queue` + migrasi + 3 situs |
| 4.3 | Antrean persisten, klaim worker, resume | Tidak ada | Besar |
| 5.1 | Fuzzy/similarity deskripsi untuk duplikat | Hanya exact/ternormalisasi | Sedang |
| 6.1 | `REVIEW_REQUIRED` untuk logo tak pasti | Tidak ada | Kecil (bila K1 diputuskan) |
| 7.1 | Skor 6 parameter berbobot 30/25/20/10/10/5 (0–100) | Skor aditif internal | Sedang–besar (ganti mesin skor, jaga filter wajib) |
| 7.2 | Kategori skor 90/80/70 | Tidak ada | Kecil |
| 7.3 | Alasan cocok/tidak per parameter | Sebagian (`_skor_rincian`) | Kecil |
| 11 | Dashboard real-time + kontrol Start/Pause/Stop/Clear/Retry | **Tidak ada** | Besar |
| 12 | Continuous improvement + laporan berkala | Tidak ada | Besar |
| 14 | Optimasi (async, worker, cache) | Sebagian (browser tunggal, tanpa cache) | Sedang |

---

## 4. Bug/risiko yang ditemukan saat audit

1. **Batas harian memakai `localtime`** (`database.py`:363). Benar selama PC di
   WIB; bila PC diubah ke zona lain, reset kuota ikut bergeser. Spesifikasi
   meminta WIB eksplisit → perlu `Asia/Jakarta` tetap, bukan zona PC.
2. **`jobs` tidak menyimpan alasan lolos/tidak** (pasal 4.1). Sekarang alasan
   hanya dicetak ke layar, hilang setelah sesi.
3. **Tidak ada kolom "tanggal publikasi asli" vs "diperbarui"** (pasal 3.1);
   hanya `age_days` hasil teks relatif.
4. **Tidak ada penanda proses berjalan** (pasal 4.3): dua peluncur yang dibuka
   bersamaan bisa mengklaim lowongan yang sama karena tidak ada lock.
5. **Dashboard tidak ada**, sehingga pasal 11.5 (kontrol nyata) belum bisa
   diuji.

---

## 5. Usulan urutan pengerjaan

Fase 1 — **Aturan & data inti** (tanpa UI):
- putuskan K1/K2/K3, lalu terapkan seragam di 3 situs;
- kolom `jobs`: alasan, status antrean, tanggal publikasi asli;
- lock proses (satu sesi) + reset kuota WIB eksplisit.

Fase 2 — **Antrean 12 status** + resume:
- tabel `queue`, migrasi aman, `READY_TO_APPLY`, `REVIEW_REQUIRED`, `EXPIRED`;
- klaim worker + lanjut dari progres terakhir.

Fase 3 — **Skor berbobot + CV**:
- pembacaan CV (PDF/DOCX) → profil terstruktur;
- skor 6 parameter berbobot, kategori 90/80/70, alasan per parameter.

Fase 4 — **Dashboard + pembelajaran**:
- dashboard lokal (kontrol Start/Pause/Resume/Stop/Clear/Retry);
- statistik per lokasi/kategori, laporan berkala, evaluasi strategi.

Fase 1 dan 2 wajib lebih dulu: dashboard tanpa status antrean hanya akan
menampilkan data yang tidak lengkap.

---

## 5a. Status pelaksanaan

Keputusan Anda: logo wajib di JobStreet & Glints (Indeed dikecualikan),
3 halaman per kombinasi, lowongan tanpa info gaji tetap boleh dilamar,
dan semua fase dikerjakan berurutan.

**Fase 1 — selesai (`96dc574` → commit sesudahnya):**
- Batas riset 5 → **3 halaman** (`config.MAKS_HALAMAN_RISET`), seragam 3 situs.
- Logo **wajib lagi** di JobStreet & Glints; Indeed tetap dikecualikan
  (`logo_diabaikan`).
- `MIN_SALARY` bawaan **4.500.000**; lowongan tanpa info gaji tetap layak.
- Kolom baru `jobs`: `status_antrean`, `alasan`, `posted_at`,
  `dikumpulkan_at`, `diperbarui_at`, `skor` + `set_status_antrean()` dan
  `hitung_status_antrean()`.
- Kuota harian memakai **batas hari WIB** eksplisit (`rentang_hari_wib`),
  bukan zona waktu komputer.
- **Kunci sesi tunggal** (`kunci.py`) mencegah dua peluncur melamar bersamaan.
- Tes: `tests/test_antrean.py` (12) + penyesuaian tes aturan; 465 tes hijau.

**Fase 2 — selesai (`7e448b2`):**
- `antrean.py`: pemetaan alasan → status, `klaim()` idempoten sebelum melamar,
  `selesai()` untuk applied/failed/review_required/expired.
- Dipakai di **ketiga** alur (`main.py`, `glints.py`, `indeed.py`), termasuk
  status penolakan, `applying` sebelum kirim, dan `expired` bila situs
  menyatakan lowongan tutup.
- `kendali.py`: berkas perintah `jeda`/`stop` yang diperiksa sesi di antara
  lowongan dan kata kunci — dasar tombol Pause/Stop dashboard.
- `REVIEW_REQUIRED` untuk logo yang **tidak dapat dipastikan** (pasal 6.1),
  bukan hanya tanpa logo.

**Fase 3 — selesai (`73f34b6`):**
- `cv.py`: baca `.docx` (zip+XML, tanpa dependensi), `.txt`/`.md`, dan `.pdf`
  (opsional lewat `pypdf`); profil berisi pengalaman, pendidikan, bidang,
  keterampilan, sertifikasi.
- `skor_cv.py`: skor 0–100 berbobot 30/25/20/10/10/5 + kategori 90/80/70 +
  rincian per parameter + alasan cocok/kurang. `MIN_SKOR_CV` memotong kandidat
  sebelum antrean apply. Tanpa CV, perilaku lama tidak berubah.

**Fase 4 — selesai:**
- `dashboard.py`: server HTTP pustaka standar (tanpa dependensi) di
  `http://127.0.0.1:8765`, JSON status, log aktivitas, dan kontrol nyata
  Start/Pause/Resume/Stop/Retry/Clear (Clear berkonfirmasi, dan tidak
  menghapus lowongan yang pernah dilamar). Diuji live di sandbox.
- `laporan.py` + `jalankan.bat laporan`: angka kinerja nyata dari database,
  sebaran status, per lokasi/kategori, alasan penolakan tersering, tingkat
  keberhasilan, serta saran yang **tidak** mengubah aturan otomatis.
- `log_aktivitas.py`: log harian WIB di `logs/aktivitas.log`.
- Perintah CLI baru: `cv`, `dashboard`, `laporan`, `antrean`; berkas
  `Dashboard.bat`.

**Uji 15 skenario wajib (pasal 14) — `tests/test_skenario_wajib.py`:**

| # | Skenario | Hasil |
|---|---|---|
| 1 | 200 lowongan sekaligus | 200 diproses & terurut, tanpa gagal |
| 2 | duplikat lintas sumber | digabung; satu baris per lowongan |
| 3 | tanpa logo | ditolak, kecuali Indeed |
| 4 | gaji Rp4,0 jt vs Rp4,5 jt | 4,0 jt ditolak (termasuk rentang 4,0–6,0 jt), 4,5 jt lolos |
| 5 | tanpa info gaji | tetap boleh dilamar |
| 6 | tidak relevan CV | tersaring `MIN_SKOR_CV` |
| 7 | batas 50/hari | dipotong tepat sesuai sisa kuota |
| 8 | kuota habis | berhenti, tidak melebihi batas |
| 9 | aplikasi dimatikan | sesi kedua ditolak; Stop menghentikan sesi |
| 10 | internet putus | dicatat `failed`, riwayat tetap, bisa diulang |
| 11 | resume setelah ditutup | status tersimpan & dibaca ulang |
| 12 | pertanyaan berulang | dijawab dari ingatan |
| 13 | bahasa berbeda | "Full Name" → jawaban "Nama Lengkap" |
| 14 | status kirim tidak pasti | `review_required`, bukan "berhasil" |
| 15 | klik dua kali | satu lamaran saja |

**Pelengkap setelah Fase 4 (revisi ini):**
- **Prioritas lokasi × kategori** (`PRIORITAS_LOKASI`, `PRIORITAS_KATEGORI`):
  mengatur urutan saat skor sama; tidak pernah menolak lowongan.
- **Dashboard lengkap**: detail satu lowongan + riwayat lamaran, tabel riwayat,
  dan edit konfigurasi dengan validasi (`.env` dicadangkan ke `.env.bak`,
  berlaku pada sesi berikutnya).
- **Backup & restore** database (`backup.py`, `jalankan.bat backup`): memakai
  API backup SQLite (aman saat sesi berjalan), `integrity_check` sebelum
  pemulihan, database lama disimpan `.db.bak`, 20 backup terbaru disimpan.
- **Laporan berkala**: `laporan.teks_markdown()` + `laporan.simpan()` menulis
  `reports/laporan-YYYY-MM-DD.md`, otomatis setelah sesi `lamar` selesai dan
  bisa dijadwalkan lewat Task Scheduler (`jalankan.bat laporan --simpan`).
- **Evaluasi kata kunci & sumber**: tabel `jobs` menyimpan `sumber` (dibaca
  dari URL, dengan pengisian otomatis untuk database lama) dan `kata_kunci`
  yang menemukan lowongan. Laporan, dashboard, dan berkas harian menampilkan
  jumlah lowongan + lamaran per kata kunci dan per sumber, lalu menyarankan
  kata kunci yang tidak produktif.

**Batas yang perlu diketahui (jujur):**
- Uji browser nyata (Selenium) tetap hanya bisa di PC Anda; semua tes di sini
  memakai bot/driver palsu.
- Atribusi kata kunci mencatat **kata kunci pertama** yang menemukan sebuah
  lowongan (bukan semua kata kunci yang juga menemukannya).
- Jumlah duplikat yang dibuang tercatat di konsol setiap riset, tetapi belum
  disimpan sebagai angka di laporan.
- Laporan berkala berbentuk berkas harian + panduan Task Scheduler; tidak ada
  penjadwal bawaan di dalam aplikasi.
- Uji end-to-end di browser sungguhan (JobStreet/Glints/Indeed) tetap harus
  dijalankan di PC pengguna.
- Klaim worker memakai status di database + kunci sesi tunggal, bukan antrean
  multi-mesin.

## 6. Yang TIDAK akan saya ubah tanpa persetujuan Anda

Sesuai pasal 12.5: batas gaji, batas 50/hari, kriteria logo, daftar lokasi,
daftar kategori, data pribadi/CV, dan ketentuan inti apply.
