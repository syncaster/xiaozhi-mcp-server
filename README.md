# Xiaozhi MCP – Materi Kuliah, Musik Indonesia, dan Pencarian Web

Proyek ini menghubungkan **AI Xiaozhi** (ESP32) dengan **server MCP lokal** yang bisa:

- membaca, mencari, dan meringkas materi kuliah berformat PDF (termasuk PDF hasil scan lewat OCR),
- memutar **lagu Indonesia** (viral / berdasarkan judul) lewat speaker perangkat,
- mencari informasi terbaru di internet dengan **hasil Google** (berita, jadwal, skor, dll).

```
Xiaozhi (ESP32)  <──WebSocket──>  mcp_pipe.py  <──stdio──>  kb_search.py ──> folder PDF materi
      │                                ▲                        ├─ music_id.py  ──> music_server.py (YouTube -> Opus)
      │                         mcp_config.json + .env          └─ web_google.py ─> Serper.dev (hasil Google)
      └── HTTP ──> music_server.py  (stream musik langsung ke perangkat)
```

| File                                                | Fungsi                                                                   |
| --------------------------------------------------- | ------------------------------------------------------------------------ |
| `mcp_pipe.py`                                       | Jembatan: menyambungkan stdio server MCP ke endpoint WebSocket Xiaozhi   |
| `mcp_config.json`                                   | Daftar server MCP yang dijalankan oleh `mcp_pipe.py`                     |
| `kb_search.py`                                      | Server MCP lokal: baca / cari / ringkas PDF + OCR otomatis               |
| `web_google.py`                                     | Tool MCP `cari_web_google`: pencarian internet berbasis Google (+ cache) |
| `music_id.py`, `music_common.py`, `music_server.py` | Tool & server musik Indonesia (lihat bagian 10)                          |
| `.env`                                              | Menyimpan rahasia & pengaturan (token endpoint, API key, URL musik)      |

---

## 1. Struktur folder

```
proyek/
├── .env                    # buat sendiri (jangan di-commit!)
├── mcp_pipe.py
├── mcp_config.json
├── kb_search.py
├── web_google.py           # pencarian web (bagian 11)
├── music_id.py             # tool musik (bagian 10)
├── music_common.py
├── music_server.py
├── modul-pbo/              # PDF materi PBO
│   ├── 01 Pengantar PBO.pdf
│   └── ...
├── modul-weblanjut/        # PDF materi Web Lanjut
│   ├── 01 Pengantar Laravel.pdf
│   └── ...
├── .ocr_cache/             # dibuat otomatis (hasil OCR)
└── mcp_chat_log.json       # dibuat otomatis (riwayat pertanyaan)
```

> Jalankan semua perintah dari **folder proyek ini**. `mcp_pipe.py` mencari `mcp_config.json`
> di folder kerja saat ini, dan `python -m kb_search` hanya bisa menemukan `kb_search.py`
> jika dijalankan dari folder yang sama.

---

## 2. Instalasi

Butuh Python 3.10 atau lebih baru.

```bash
pip install websockets python-dotenv fastmcp pypdf pymupdf rapidocr-onnxruntime requests
```

Tambahan untuk fitur lain (lihat bagian 10 dan 11):

```bash
pip install flask yt-dlp        # musik Indonesia
pip install ddgs                # opsional: cadangan pencarian web tanpa API key
```

Hanya jika memakai server remote bertipe `sse` / `http` di `mcp_config.json`:

```bash
pip install mcp-proxy
```

| Paket                             | Dipakai untuk                                   |
| --------------------------------- | ----------------------------------------------- |
| `websockets`, `python-dotenv`     | `mcp_pipe.py`                                   |
| `fastmcp`, `pypdf`                | `kb_search.py` (server MCP & baca teks PDF)     |
| `pymupdf`, `rapidocr-onnxruntime` | OCR untuk PDF scan                              |
| `requests`                        | `web_google.py` (memanggil Serper.dev)          |
| `flask`, `yt-dlp`                 | `music_server.py` (musik)                       |
| `ddgs`                            | Cadangan pencarian web tanpa API key (opsional) |
| `mcp-proxy`                       | Server MCP remote (opsional)                    |

---

## 3. `.env`

Buat file bernama `.env` di folder proyek (satu folder dengan `mcp_pipe.py`).
`mcp_pipe.py` membacanya otomatis saat start.

```env
MCP_ENDPOINT=wss://api.xiaozhi.me/mcp/?token=ISI_TOKEN_ANDA
# MCP_CONFIG=D:/path/lain/mcp_config.json

# Pencarian web Google (bagian 11)
SERPER_API_KEY=ISI_API_KEY_SERPER

# Musik Indonesia (bagian 10)
MUSIC_PUBLIC_URL=http://192.168.100.7:8765
```

| Variabel           | Wajib       | Keterangan                                                                            |
| ------------------ | ----------- | ------------------------------------------------------------------------------------- |
| `MCP_ENDPOINT`     | Ya          | Alamat WebSocket MCP dari akun/perangkat Xiaozhi Anda (berisi token)                  |
| `MCP_CONFIG`       | Tidak       | Path config lain. Jika kosong, dipakai `./mcp_config.json`                            |
| `SERPER_API_KEY`   | Tidak\*     | API key Serper.dev untuk `cari_web_google`. \*Tanpa ini dipakai DuckDuckGo (cadangan) |
| `MUSIC_PUBLIC_URL` | Untuk musik | Alamat `music_server.py` yang bisa dijangkau ESP32 (lihat bagian 10)                  |

Variabel `.env` diteruskan otomatis ke server MCP (`kb_search.py`, `web_google.py`, `music_id.py`).
Jika `MCP_ENDPOINT` belum diisi, program berhenti dengan pesan:
`Please set the MCP_ENDPOINT environment variable`.

**Keamanan:** token di `MCP_ENDPOINT` bersifat rahasia. Jika memakai Git, tambahkan ke `.gitignore`:

```
.env
.ocr_cache/
mcp_chat_log.json
```

---

## 4. `mcp_config.json`

Mendefinisikan server MCP apa saja yang akan disambungkan ke Xiaozhi.

```json
{
  "mcpServers": {
    "local-stdio-kb": {
      "type": "stdio",
      "command": "python",
      "args": ["-m", "kb_search"]
    },
    "remote-sse-server": {
      "type": "sse",
      "url": "https://api.example.com/sse",
      "disabled": true
    },
    "remote-http-server": {
      "type": "http",
      "url": "https://api.example.com/mcp",
      "disabled": true
    }
  }
}
```

### Field yang didukung

| Field                         | Berlaku untuk | Keterangan                                          |
| ----------------------------- | ------------- | --------------------------------------------------- |
| `type` (atau `transportType`) | semua         | `stdio` (default), `sse`, `http` / `streamablehttp` |
| `command`                     | `stdio`       | Perintah yang dijalankan, mis. `python`             |
| `args`                        | `stdio`       | Argumen perintah, mis. `["-m", "kb_search"]`        |
| `env`                         | semua         | Variabel lingkungan tambahan untuk proses server    |
| `url`                         | `sse`, `http` | Alamat server remote (dijalankan lewat `mcp_proxy`) |
| `headers`                     | `sse`, `http` | Header HTTP, mis. `{"Authorization": "Bearer xxx"}` |
| `disabled`                    | semua         | `true` = server dilewati                            |

### Contoh: menambah server lain

```json
"server-lain": {
  "type": "stdio",
  "command": "python",
  "args": ["server_lain.py"],
  "env": { "API_KEY": "rahasia" }
}
```

Server dengan `"disabled": true` tidak akan dijalankan. Ubah ke `false` (atau hapus barisnya)
untuk mengaktifkan.

---

## 5. `mcp_pipe.py`

Menjalankan server MCP sebagai proses anak, lalu meneruskan pesan dua arah antara
proses tersebut dan WebSocket Xiaozhi. Jika koneksi putus, ia otomatis mencoba lagi
dengan jeda yang makin lama (1 detik hingga maksimal 10 menit).

### Menjalankan

```bash
# Jalankan SEMUA server yang aktif di mcp_config.json (cara utama)
python mcp_pipe.py

# Jalankan satu skrip Python saja (tanpa config)
python mcp_pipe.py path/ke/server.py
```

> Argumen yang diterima hanya **path file skrip Python**. Nama server dari config
> (mis. `local-stdio-kb`) tidak bisa dipakai sebagai argumen; untuk memakai config,
> jalankan tanpa argumen.

### Log

Level log saat ini `DEBUG`, jadi setiap pesan dari/ke Xiaozhi tampil di terminal.
Untuk log lebih ringkas, buka `mcp_pipe.py` lalu ubah:

```python
level=logging.DEBUG,   # ganti menjadi logging.INFO
```

### Tanda berhasil

```
Starting servers: local-stdio-kb
[local-stdio-kb] Successfully connected to WebSocket server
[local-stdio-kb] Started server process: python -m kb_search
```

Berhenti dengan `Ctrl+C`.

---

## 6. `kb_search.py`

Server MCP (transport stdio) yang membaca PDF materi. Biasanya **tidak dijalankan manual**;
`mcp_pipe.py` yang memanggilnya sesuai `mcp_config.json`.

### 6.1 Tool yang tersedia untuk Xiaozhi

| Tool                    | Fungsi                                      | Contoh ucapan                            |
| ----------------------- | ------------------------------------------- | ---------------------------------------- |
| `list_documents`        | Daftar PDF + jumlah halaman per mata kuliah | "Materi web lanjut apa saja?"            |
| `read_document`         | Baca isi satu PDF per rentang halaman       | "Bacakan pertemuan 4 halaman 1 sampai 3" |
| `summarize_document`    | Ringkas satu PDF (atau halaman tertentu)    | "Ringkas materi model factories"         |
| `summarize_course`      | Ringkas seluruh PDF satu mata kuliah        | "Ringkas semua materi PBO"               |
| `search_knowledge_base` | Cari kata/frasa di semua PDF                | "Apa itu polymorphism?"                  |

Selain lima tool materi di atas, server `kb_search.py` yang sama juga membawa tool musik
(`lagu_viral_indonesia`, `cari_lagu_indonesia`; bagian 10) dan tool pencarian web
(`cari_web_google`; bagian 11), sehingga cukup **satu** koneksi MCP.

Nama dokumen boleh sebagian saja (mis. `blade engine`) atau nomor pertemuan (mis. `4`).
Hasil dibatasi `MAX_CHARS` per panggilan; jika masih ada lanjutan, Xiaozhi memanggil lagi
dari halaman berikutnya.

### 6.2 Menambah / mengubah mata kuliah

Edit `MATERI_FOLDERS` di bagian atas `kb_search.py`:

```python
MATERI_FOLDERS = {
    "modul-pbo": {
        "label": "Pemrograman Berorientasi Objek (PBO)",
        "alias": ["pbo", "oop"],
    },
    "modul-basisdata": {                      # <- contoh mata kuliah baru
        "label": "Basis Data",
        "alias": ["basis data", "basdat", "sql"],
    },
}
```

Langkah: buat foldernya, taruh PDF di dalamnya, lalu daftarkan di `MATERI_FOLDERS`.
`alias` membantu Xiaozhi mengenali mata kuliah dari ucapan Anda. Folder yang tidak
terdaftar (mis. `skripsi/`, `templates/`) diabaikan.

**Tips penamaan file:** awali dengan nomor urut (`01 Judul.pdf`, `02 Judul.pdf`)
agar terurut dan bisa dipanggil dengan "pertemuan 2".

### 6.3 Pengaturan lain (bagian atas file)

| Konstanta       | Default         | Fungsi                                                      |
| --------------- | --------------- | ----------------------------------------------------------- |
| `MAX_CHARS`     | `3500`          | Batas teks per panggilan tool (agar ringan untuk perangkat) |
| `STRIP_WORDS`   | `{"pemweblan"}` | Kata yang dibuang saat mencocokkan nama file                |
| `OCR_ENABLED`   | `True`          | Aktif/nonaktifkan OCR otomatis                              |
| `OCR_MIN_CHARS` | `30`            | Halaman dengan teks lebih sedikit dari ini di-OCR           |
| `OCR_DPI`       | `200`           | Ketajaman render untuk OCR (150 cepat, 250 lebih akurat)    |

### 6.4 OCR untuk PDF scan

Jika sebuah halaman tidak punya teks (hasil scan atau PDF yang diubah dari gambar),
`kb_search.py` otomatis:

1. merender halaman menjadi gambar (PyMuPDF),
2. membaca teksnya dengan RapidOCR,
3. menyimpan hasilnya di `.ocr_cache/` sehingga tiap halaman hanya di-OCR **sekali**.

OCR lambat (beberapa detik per halaman). Jalankan **sekali** secara manual sebelum
memakai Xiaozhi:

```bash
python kb_search.py --prewarm
```

Perintah ini memproses semua PDF, menyimpan cache, lalu selesai. Setelahnya, Xiaozhi
langsung bisa membaca dokumen scan tanpa menunggu.

- Cache otomatis dibuat ulang jika file PDF diubah.
- Folder `.ocr_cache/` aman dihapus kapan saja (OCR akan diulang).
- Jika hasil OCR kurang akurat untuk bahasa Indonesia, pertimbangkan beralih ke
  Tesseract (`pytesseract`, `lang="ind+eng"`) dengan mengganti isi fungsi `_ocr_page`.

### 6.5 Log pertanyaan

Setiap pemanggilan tool dicatat ke `mcp_chat_log.json` (waktu, pertanyaan, jawaban sistem).
Hapus file ini kapan saja jika sudah terlalu besar.

---

## 6b. Ringkasan seluruh tool

| Tool                    | Berasal dari                 | Fungsi                                       |
| ----------------------- | ---------------------------- | -------------------------------------------- |
| `list_documents`        | `kb_search.py`               | Daftar PDF materi                            |
| `read_document`         | `kb_search.py`               | Baca PDF per halaman                         |
| `summarize_document`    | `kb_search.py`               | Ringkas satu PDF                             |
| `summarize_course`      | `kb_search.py`               | Ringkas semua PDF satu mata kuliah           |
| `search_knowledge_base` | `kb_search.py`               | Cari kata/frasa di semua PDF                 |
| `lagu_viral_indonesia`  | `music_id.py` (MCP PC)       | Daftar lagu viral + `stream_url`             |
| `cari_lagu_indonesia`   | `music_id.py` (MCP PC)       | Cari lagu berdasarkan judul/artis            |
| `cari_web_google`       | `web_google.py`              | Pencarian internet berbasis Google (+ cache) |
| `self.music.play_url`   | firmware (`music_player.cc`) | Putar lagu dari `stream_url`                 |
| `self.music.stop`       | firmware                     | Hentikan lagu                                |

---

## 7. Alur pemakaian lengkap

1. Taruh PDF di `modul-pbo/` dan `modul-weblanjut/`.
2. Isi `.env` dengan `MCP_ENDPOINT`.
3. `pip install ...` (lihat bagian 2).
4. Jika ada PDF scan: `python kb_search.py --prewarm`.
5. Jalankan: `python mcp_pipe.py`.
6. Tunggu muncul `Successfully connected to WebSocket server`, lalu bicara ke Xiaozhi.
7. Untuk musik: jalankan juga `python music_server.py` (bagian 10). Untuk pencarian web: isi
   `SERPER_API_KEY` (bagian 11).

---

## 8. Pemecahan masalah

| Gejala                                                 | Penyebab / solusi                                                                                                        |
| ------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------ |
| `Please set the MCP_ENDPOINT environment variable`     | `.env` belum dibuat, salah nama, atau tidak di folder yang sama dengan `mcp_pipe.py`                                     |
| `No enabled mcpServers found in config`                | Semua server di `mcp_config.json` ber-`disabled: true`, atau config tidak ditemukan (cek folder kerja / `MCP_CONFIG`)    |
| `No module named kb_search`                            | Perintah dijalankan dari folder yang salah                                                                               |
| `Folder materi tidak ditemukan`                        | Nama folder tidak cocok dengan `MATERI_FOLDERS`                                                                          |
| Xiaozhi bilang dokumen tidak bisa dibaca / "perlu OCR" | PDF berupa gambar: pastikan paket OCR terpasang lalu jalankan `--prewarm`                                                |
| `OCR gagal untuk ...` di log                           | `pymupdf` / `rapidocr-onnxruntime` belum terinstal, atau tidak ada wheel untuk versi Python Anda (coba Python 3.10–3.12) |
| Respon Xiaozhi lambat pertama kali                     | PDF sedang dimuat/di-OCR di latar belakang; jalankan `--prewarm` terlebih dulu                                           |
| Koneksi terus terputus & mencoba ulang                 | Token di `MCP_ENDPOINT` salah/kedaluwarsa, atau jaringan bermasalah                                                      |
| Dokumen tidak ditemukan padahal ada                    | Cek ejaan nama, atau sebutkan nomor pertemuan; nama mata kuliah bisa ditambahkan di `alias`                              |

---

## 9. Daftar perintah singkat

```bash
python mcp_pipe.py                  # jalankan semua server aktif
python mcp_pipe.py server.py        # jalankan satu skrip saja
python kb_search.py --prewarm       # OCR & muat semua PDF lebih dulu, lalu selesai
python music_server.py              # server stream musik untuk ESP32
python music_common.py              # uji daftar lagu viral tanpa Xiaozhi
```

---

## 10. Musik Indonesia (lagu viral)

Firmware Xiaozhi standar (`78/xiaozhi-esp32`) tidak punya pemutar musik; musik dari Tiongkok
berasal dari fitur cloud xiaozhi.me. Karena itu kita menambah tiga bagian sendiri:

| File                                      | Peran                                                                                                      |
| ----------------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| `music_id.py`                             | Tool MCP **lagu viral Indonesia** & cek judul/artis. **Digabung ke `kb_search.py`**, bukan server terpisah |
| `music_server.py`                         | Server HTTP lokal: mencari di YouTube dan **mengalirkan audio ke ESP32**                                   |
| `music_common.py`                         | Kode bersama kedua file di atas (jangan dihapus)                                                           |
| `firmware/main/music/music_player.{h,cc}` | Kode C++ di perangkat: tool `self.music.play_url` / `self.music.stop`                                      |

```
"Putar lagu viral" -> AI memanggil lagu_viral_indonesia (music_id.py) -> daftar judul + stream_url
                   -> AI memanggil self.music.play_url(stream_url) di perangkat
                   -> perangkat mengambil stream Opus dari music_server.py -> lagu diputar
```

### A. Sisi PC

```bash
pip install flask yt-dlp
```

Install **ffmpeg yang menyertakan libopus** (build "full" dari gyan.dev atau BtbN untuk Windows;
cek dengan `ffmpeg -encoders | findstr opus`). Jaga `yt-dlp` tetap baru (`pip install -U yt-dlp`).

Isi `.env`:

```env
MUSIC_PUBLIC_URL=http://192.168.100.7:8765
```

(ganti dengan IP PC Anda; sebaiknya dibuat tetap lewat DHCP reservation di router).

Jalankan server musik dan biarkan terbuka:

```bash
python music_server.py
```

Izinkan Python lewat Windows Firewall saat diminta. Uji di browser:
`http://192.168.100.7:8765/stream_pcm?song=hati hati di jalan&artist=tulus` harus mengembalikan JSON.

### B. Sisi firmware (folder `xiaozhi-esp32`)

1. Salin folder `firmware/main/music/` ke `main/music/` di proyek firmware.
2. Di `main/CMakeLists.txt`, tambahkan `"music/music_player.cc"` ke daftar `SOURCES`.
   Jika muncul error `esp_http_client.h: No such file`, tambahkan `esp_http_client` ke `REQUIRES`.
3. Di file board Anda (yang berisi `InitializeTools()`, tempat tool cuaca Anda didaftarkan),
   tambahkan:

```cpp
#include "music/music_player.h"
// ... di dalam InitializeTools():
MusicPlayer::GetInstance().RegisterTools();
```

4. Build dan flash: `idf.py build flash monitor`.

Cara kerja di perangkat: `music_player.cc` menunggu AI selesai bicara (state `speaking` berakhir),
lalu **mengakhiri sesi `listening` lewat `StopListening()`** agar perangkat kembali **Idle**, baru
lagu dimulai. Tanpa langkah ini perangkat tetap di `listening` dan lagu dibatalkan. Batas tunggu
45 detik (`kWaitIdleMs`). Lagu otomatis berhenti jika Anda memanggil AI lagi.

Jika build error karena `StopListening` tidak ada di versi firmware Anda, cek `main/application.h`
lalu ganti baris di `music_player.cc` dengan salah satu:

```cpp
app.Schedule([]() { Application::GetInstance().ToggleChatState(); });
app.Schedule([]() { Application::GetInstance().SetDeviceState(kDeviceStateIdle); });
```

### Kontrol tombol: hentikan bacaan AI dan musik

Di `InitializeButtons()` pada file board (mis. `compact_wifi_board_lcd.cc`), ganti handler tombol Boot:

```cpp
#include "music/music_player.h"

boot_button_.OnClick([this]() {
    auto& app = Application::GetInstance();
    auto state = app.GetDeviceState();

    if (state == kDeviceStateStarting) {
        EnterWifiConfigMode();
        return;
    }
    // AI sedang membacakan teks -> hentikan bacaan sekarang juga
    if (state == kDeviceStateSpeaking) {
        app.AbortSpeaking(kAbortReasonNone);
        return;
    }
    app.ToggleChatState();
});

// Klik dua kali: hentikan bacaan AI / musik, lalu kembali ke standby (Idle)
boot_button_.OnDoubleClick([]() {
    auto& app = Application::GetInstance();
    auto& player = MusicPlayer::GetInstance();
    if (player.IsPlaying()) {
        player.Stop();
    }
    if (app.GetDeviceState() == kDeviceStateSpeaking) {
        app.AbortSpeaking(kAbortReasonNone);
    }
    app.Schedule([]() {
        auto& a = Application::GetInstance();
        if (a.GetDeviceState() == kDeviceStateListening) {
            a.StopListening();
        }
    });
});
```

| Aksi                                 | Hasil                                                   |
| ------------------------------------ | ------------------------------------------------------- |
| Wake word / klik sekali saat musik   | Musik berhenti, perangkat masuk `listening`             |
| Klik sekali saat AI membaca teks     | Bacaan berhenti, perangkat siap mendengarkan            |
| Klik dua kali                        | Bacaan dan musik berhenti, perangkat kembali ke standby |
| Ucapkan "stop musik" saat sesi aktif | AI memanggil `self.music.stop`                          |

Catatan: saat AI berbicara, suara hanya bisa memotongnya lewat **wake word**. Jika wake word tidak
aktif di board Anda, gunakan tombol. Jika `AbortSpeaking` atau `OnDoubleClick` tidak ada di versi
firmware Anda, cek `main/application.h` dan library `Button`; di cabang `speaking` bisa diganti
`app.ToggleChatState();`, dan blok double-click boleh dihapus.

### C. Aktifkan tool pencarian & atur role

Tool musik sudah **digabung ke `kb_search.py`**: satu server MCP (`local-stdio-kb`) kini berisi
tool materi kuliah _dan_ tool musik, jadi `mcp_config.json` **tidak perlu diubah** dan tidak boleh
ada server kedua untuk musik (satu endpoint Xiaozhi umumnya hanya melayani satu koneksi).
Jalankan ulang `python mcp_pipe.py`; di log harus muncul
`Tool musik Indonesia aktif: lagu_viral_indonesia, cari_lagu_indonesia`.
Pastikan `music_common.py` dan `music_id.py` berada di folder yang sama dengan `kb_search.py`.

Lalu tambahkan ke instruksi role di xiaozhi.me:

```
Jika user meminta lagu viral/trending/rekomendasi lagu Indonesia, panggil tool
lagu_viral_indonesia, lalu putar lagunya dengan self.music.play_url memakai stream_url persis
dari daftar tersebut. Jika user menyebut judul yang kurang jelas, gunakan cari_lagu_indonesia
dahulu. Untuk menghentikan musik gunakan self.music.stop. Jangan memakai search_music.
```

### Pengaturan opsional (`.env`)

| Variabel             | Default | Fungsi                                                                        |
| -------------------- | ------- | ----------------------------------------------------------------------------- |
| `MUSIC_PUBLIC_URL`   | kosong  | **Wajib**: alamat `music_server.py` yang bisa dijangkau ESP32                 |
| `VIRAL_PLAYLIST_URL` | kosong  | URL playlist YouTube pilihan Anda; jika diisi, daftar viral diambil dari sini |
| `MUSIC_PORT`         | `8765`  | Port `music_server.py`                                                        |
| `MUSIC_OPUS_BITRATE` | `48k`   | Kualitas stream ke ESP32. Turunkan ke `32k` jika putus-putus                  |

Cek daftar viral tanpa Xiaozhi: `python music_common.py`

### Pemecahan masalah musik

| Gejala                                                        | Solusi                                                                                                                                                                                                                                       |
| ------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `yt-dlp tidak bisa dimuat oleh Python ini (...)`              | Install di Python yang sama dengan yang tertera di pesan: `"<path>" -m pip install -U yt-dlp`                                                                                                                                                |
| Lagu tidak ditemukan                                          | Jalankan `python music_common.py`; jika error, perbarui `yt-dlp`                                                                                                                                                                             |
| Log perangkat: `Tidak bisa terhubung ke server musik`         | Cek `MUSIC_PUBLIC_URL`, WiFi yang sama, dan firewall PC                                                                                                                                                                                      |
| Log perangkat: `Pemutaran dibatalkan (perangkat tidak Idle)`  | Perangkat tidak kembali Idle dalam 45 detik. Pastikan `music_player.cc` versi terbaru (memanggil `StopListening()`), lalu flash ulang. Log normal: `speaking -> listening`, `mengakhiri sesi listening`, `listening -> idle`, `Memutar: ...` |
| AI menjawab lagu "versi Cina"                                 | AI masih memakai pencarian musik bawaan cloud. Pastikan instruksi role (langkah C) sudah disimpan di xiaozhi.me dan log MCP menampilkan tool `lagu_viral_indonesia`                                                                          |
| Hasil tool berisi `peringatan: MUSIC_PUBLIC_URL belum diatur` | Isi `MUSIC_PUBLIC_URL` di `.env`, lalu jalankan ulang `mcp_pipe.py`                                                                                                                                                                          |
| AI tidak memanggil `self.music.play_url`                      | Periksa instruksi role (langkah C) dan pastikan tool muncul di log MCP                                                                                                                                                                       |
| Server error 502 / ffmpeg error                               | Perbarui `yt-dlp`; pastikan ffmpeg punya libopus                                                                                                                                                                                             |
| Lagu putus-putus                                              | Turunkan `MUSIC_OPUS_BITRATE`, atau dekatkan ESP32 ke router                                                                                                                                                                                 |

> Catatan: memutar musik dari YouTube untuk pemakaian pribadi sebaiknya tetap memperhatikan
> ketentuan layanan YouTube dan hak cipta di negara Anda.

---

## 11. Pencarian web Google (`cari_web_google`)

Tool `web_search` yang muncul di log Xiaozhi (`% web_search...`) adalah fitur **bawaan cloud
xiaozhi.me**, bukan bagian kode proyek ini, sehingga mesin pencarinya tidak bisa diganti dari
sisi Anda. Hasilnya sering kurang cocok untuk informasi lokal Indonesia (mis. jadwal MPL, berita
hari ini). Karena itu proyek ini menambah tool sendiri, `cari_web_google`, di `web_google.py`.

> Google Custom Search JSON API resmi sudah **ditutup untuk pelanggan baru** (Januari 2026) dan
> berhenti total pada 1 Januari 2027, jadi tidak dipakai. `web_google.py` memakai **Serper.dev**,
> layanan yang mengembalikan hasil Google asli.

### A. Pemasangan

1. Daftar di [serper.dev](https://serper.dev) (tanpa kartu kredit), ambil API key, lalu isi `.env`:

   ```env
   SERPER_API_KEY=isi_api_key_anda
   ```

2. Taruh `web_google.py` satu folder dengan `kb_search.py`, lalu `pip install requests`.
3. Di `kb_search.py`, tambahkan di bawah blok `import music_id`:

   ```python
   try:
       import web_google
       web_google.register(mcp)
   except Exception as e:
       logger.warning(f"Tool web google tidak aktif: {type(e).__name__}: {e}")
   ```

4. Jalankan ulang `python mcp_pipe.py`. Di log harus muncul
   `Tool cari_web_google aktif (mesin: Google/Serper)`.

Tanpa `SERPER_API_KEY`, tool otomatis memakai **DuckDuckGo** (`pip install ddgs`) sebagai cadangan.
Itu bukan Google, jadi hasilnya bisa berbeda; log akan menampilkan `mesin: DuckDuckGo`.

### B. Parameter tool

| Parameter | Tipe   | Default | Keterangan                                                                         |
| --------- | ------ | ------- | ---------------------------------------------------------------------------------- |
| `query`   | string | wajib   | Kata kunci singkat, mis. `jadwal final MPL ID season 18`                           |
| `berita`  | bool   | `false` | `true` untuk mencari berita terbaru                                                |
| `waktu`   | string | kosong  | Batasi hasil: `jam`, `hari`, `minggu`, `bulan`, `tahun` (untuk "hari ini": `hari`) |

Hasil dipersingkat (maksimal 5 hasil, cuplikan ±220 karakter) supaya enak dibacakan lewat speaker,
dan wilayah/bahasa pencarian diset ke Indonesia (`gl=id`, `hl=id`).

### C. Instruksi role di xiaozhi.me

`web_search` bawaan cloud tidak bisa dimatikan, jadi arahkan AI lewat instruksi role:

```
Untuk mencari informasi di internet (berita, jadwal, skor, harga, peristiwa terbaru), selalu
gunakan tool cari_web_google, jangan memakai web_search. Untuk hal yang terjadi "hari ini",
isi parameter waktu dengan "hari". Rangkum hasilnya dengan singkat dalam bahasa Indonesia.
```

### D. Cache dan kuota

- Hasil sukses disimpan di memori **15 menit** (`CACHE_TTL`, maksimal `CACHE_MAX` = 100 entri).
  Pertanyaan yang sama (huruf kecil / spasi diabaikan) tidak memakai kredit lagi; log menampilkan
  `Cache hit: '...'`. Turunkan `CACHE_TTL` (mis. `3 * 60`) untuk skor yang berubah cepat.
- Hasil gagal tidak di-cache. Cache hilang jika `mcp_pipe.py` di-restart.
- Tier gratis Serper: **2.500 query sekali pakai** (bukan per bulan). Satu pencarian biasa = 1
  kredit; meminta 11–100 hasil = 2 kredit, jadi biarkan `MAX_RESULTS = 5`. Cek sisa kredit dan harga
  terbaru di dashboard Serper.

### E. Contoh penggunaan

| Ucapan ke Xiaozhi                      | Yang terjadi                                                           |
| -------------------------------------- | ---------------------------------------------------------------------- |
| "Carikan jadwal final MPL hari ini"    | `cari_web_google(query="jadwal final MPL ID", waktu="hari")`           |
| "Ada berita apa soal timnas hari ini?" | `cari_web_google(query="timnas Indonesia", berita=true, waktu="hari")` |
| "Berapa kurs dolar sekarang?"          | `cari_web_google(query="kurs dolar rupiah hari ini")`                  |
| "Siapa juara Liga 1 musim lalu?"       | `cari_web_google(query="juara Liga 1 musim lalu")`                     |

Di terminal server akan muncul `Xiaozhi mencari web: '...'`. Jika yang muncul di terminal
perangkat tetap `% web_search`, AI masih memilih tool bawaan: periksa instruksi role (langkah C).

### F. Pemecahan masalah pencarian web

| Gejala                                  | Solusi                                                                                   |
| --------------------------------------- | ---------------------------------------------------------------------------------------- |
| AI masih memakai `web_search` bawaan    | Simpan instruksi role (langkah C); pastikan tool `cari_web_google` muncul di log MCP     |
| Log: `Tool web google tidak aktif: ...` | `web_google.py` tidak satu folder dengan `kb_search.py`, atau `requests` belum terinstal |
| Log menampilkan `mesin: DuckDuckGo`     | `SERPER_API_KEY` kosong / tidak terbaca; cek `.env` lalu restart `mcp_pipe.py`           |
| `Pencarian internet gagal: HTTPError`   | API key salah, kredit habis (401/403), atau terlalu banyak permintaan (429)              |
| `Tidak ada hasil untuk '...'`           | Perpendek kata kunci, atau longgarkan `waktu` (mis. dari `hari` ke `minggu`)             |
| Hasil terasa lama / kurang baru         | Cache 15 menit; turunkan `CACHE_TTL` atau restart `mcp_pipe.py`                          |
