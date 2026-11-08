# kb_search.py
# MCP server (stdio) untuk materi kuliah berformat PDF.
# Dijalankan lewat mcp_pipe.py, dan dipanggil oleh AI Xiaozhi.
#
# Hanya folder yang terdaftar di MATERI_FOLDERS yang dibaca
# (folder lain seperti skripsi/, templates/, trash/ diabaikan).
#
# Tool:
#   - list_documents          : daftar PDF per mata kuliah
#   - read_document           : baca isi satu PDF per rentang halaman
#   - summarize_document      : ringkasan satu PDF (atau satu bab/halaman)
#   - summarize_course        : ringkasan seluruh PDF dalam satu mata kuliah
#   - search_knowledge_base   : cari kata/frasa di semua PDF materi
#   - lagu_viral_indonesia    : lagu viral Indonesia   (dari music_id.py)
#   - cari_lagu_indonesia     : cari judul/artis lagu  (dari music_id.py)
import difflib
import hashlib
import json
import logging
import os
import re
import sys
import threading
from collections import Counter
from datetime import datetime

from fastmcp import FastMCP
from pypdf import PdfReader

# ---------------------------------------------------------------- konfigurasi
logging.basicConfig(level=logging.INFO, stream=sys.stderr, format='%(message)s')
logger = logging.getLogger('KBSearch')

if sys.platform == 'win32':
    sys.stderr.reconfigure(encoding='utf-8')
    sys.stdout.reconfigure(encoding='utf-8')

mcp = FastMCP("Dynamic Knowledge Base Bot")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Folder materi (relatif terhadap folder kb_search.py).
# "alias" membantu AI menemukan mata kuliah dari ucapan user ("web lanjut", "pbo", dst).
MATERI_FOLDERS = {
    "modul-pbo": {
        "label": "Pemrograman Berorientasi Objek (PBO)",
        "alias": ["pbo", "pemrograman berorientasi objek", "berorientasi objek", "oop"],
    },
    "modul-weblanjut": {
        "label": "Pemrograman Web Lanjut",
        "alias": ["web lanjut", "weblanjut", "pemrograman web lanjut", "pemweb lanjut",
                  "pemweblan", "laravel"],
    },
}

# Kata yang dibuang saat mencocokkan nama file (akhiran nama mata kuliah di nama file)
STRIP_WORDS = {"pemweblan"}

MAX_CHARS = 3500   # batas teks per panggilan tool (agar ringan untuk perangkat)
SKIP_DIRS = {'__pycache__', '.git', 'venv', '.venv', '.idea', 'node_modules'}

# OCR otomatis untuk halaman PDF tanpa teks (hasil scan / gambar).
# Hasil OCR disimpan di folder .ocr_cache, jadi tiap halaman hanya di-OCR sekali.
OCR_ENABLED = True
OCR_MIN_CHARS = 30      # halaman dengan teks kurang dari ini dianggap perlu OCR
OCR_DPI = 200           # makin besar makin akurat, tapi makin lambat
OCR_CACHE_DIR = os.path.join(BASE_DIR, ".ocr_cache")

_pages_cache = {}            # path PDF -> list teks per halaman
_load_lock = threading.Lock()
_warned_folders = set()

# ---------------------------------------------------------------- daftar dokumen
def _norm(s):
    return " ".join(re.sub(r"[^a-z0-9]+", " ", s.lower()).split())


def _doc_number(name):
    m = re.match(r"\s*(\d{1,2})\b", name)
    return int(m.group(1)) if m else None


def _stem_norm(name):
    return _norm(os.path.splitext(name)[0])


def _core(name):
    """Nama inti: tanpa nomor urut di depan dan tanpa akhiran mata kuliah."""
    n = re.sub(r"^\d{1,2}\s+", "", _stem_norm(name))
    return " ".join(w for w in n.split() if w not in STRIP_WORDS)


def _get_docs():
    """Semua PDF di folder yang terdaftar di MATERI_FOLDERS (urut menurut nomor)."""
    docs = []
    for folder, meta in MATERI_FOLDERS.items():
        base = os.path.join(BASE_DIR, folder)
        if not os.path.isdir(base):
            if folder not in _warned_folders:
                logger.warning(f"Folder materi tidak ditemukan: {base}")
                _warned_folders.add(folder)
            continue
        for root, dirs, files in os.walk(base):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for f in files:
                if f.lower().endswith(".pdf"):
                    docs.append({"path": os.path.join(root, f), "folder": folder,
                                 "mk": meta["label"], "name": f})
    docs.sort(key=lambda d: (d["folder"],
                             _doc_number(d["name"]) if _doc_number(d["name"]) is not None else 999,
                             d["name"].lower()))
    return docs


def _filter_mk(docs, mata_kuliah):
    """Saring dokumen berdasarkan mata kuliah (nama folder, label, atau alias)."""
    q = _norm(mata_kuliah or "")
    if not q:
        return docs
    keep = set()
    for folder, meta in MATERI_FOLDERS.items():
        names = [_norm(folder), _norm(meta["label"])] + [_norm(a) for a in meta["alias"]]
        if any(n and (n in q or (len(q) >= 3 and q in n)) for n in names):
            keep.add(folder)
    return [d for d in docs if d["folder"] in keep]


def _names(docs, limit=12):
    return ", ".join(d["name"] for d in docs[:limit]) + (" ..." if len(docs) > limit else "")


def _course_names():
    return ", ".join(f"{m['label']} ({f})" for f, m in MATERI_FOLDERS.items())


def _resolve(nama_file, mata_kuliah=""):
    """Cari satu dokumen dari nama (boleh sebagian / nomor). Return (doc, pesan_error)."""
    all_docs = _get_docs()
    if not all_docs:
        folders = ", ".join(MATERI_FOLDERS)
        return None, f"Tidak ada file PDF yang ditemukan di folder materi ({folders})."

    docs = _filter_mk(all_docs, mata_kuliah)
    if not docs:
        return None, f"Mata kuliah '{mata_kuliah}' tidak dikenali. Yang tersedia: {_course_names()}."

    q = _norm(nama_file or "")
    if not q:
        if len(docs) == 1:
            return docs[0], None
        return None, f"Sebutkan nama dokumennya. Yang tersedia: {_names(docs)}"

    num = re.fullmatch(r"(?:pertemuan|modul|materi|bab|minggu|ke)?\s*(\d{1,2})", q)
    toks = q.split()
    tiers = [
        [d for d in docs if _stem_norm(d["name"]) == q],                      # nama persis
        [d for d in docs if _core(d["name"]) == q],                           # nama inti persis
    ]
    if num:
        n = int(num.group(1))
        tiers.append([d for d in docs if _doc_number(d["name"]) == n])        # nomor pertemuan
    tiers.append([d for d in docs if q in _stem_norm(d["name"])])             # mengandung
    tiers.append([d for d in docs if all(t in _stem_norm(d["name"]) for t in toks)])

    for matches in tiers:
        if len(matches) == 1:
            return matches[0], None
        if len(matches) > 1:
            return None, (f"Ada beberapa dokumen yang cocok: {_names(matches)}. "
                          "Sebutkan salah satunya dengan lebih jelas.")

    # Mungkin yang disebut adalah nama mata kuliah, bukan nama dokumen
    by_course = _filter_mk(docs, nama_file)
    if len(by_course) == 1:
        return by_course[0], None
    if len(by_course) > 1:
        return None, (f"'{nama_file}' adalah mata kuliah dengan {len(by_course)} dokumen: "
                      f"{_names(by_course)}. Sebutkan dokumennya, atau minta ringkasan seluruh mata kuliah.")

    # Terakhir: cocokkan mirip (salah ucap / salah ketik)
    cores = {}
    for d in docs:
        cores.setdefault(_core(d["name"]), d)
    close = difflib.get_close_matches(q, list(cores), n=1, cutoff=0.72)
    if close:
        return cores[close[0]], None

    return None, f"Dokumen '{nama_file}' tidak ditemukan. Yang tersedia: {_names(docs)}"

# ---------------------------------------------------------------- OCR
_ocr_engine = None


def _get_ocr():
    global _ocr_engine
    if _ocr_engine is None:
        from rapidocr_onnxruntime import RapidOCR
        _ocr_engine = RapidOCR()
    return _ocr_engine


def _ocr_page(fdoc, index):
    """Render satu halaman PDF menjadi gambar lalu baca teksnya dengan OCR."""
    pix = fdoc[index].get_pixmap(dpi=OCR_DPI)
    result, _ = _get_ocr()(pix.tobytes("png"))
    if not result:
        return ""
    return " ".join(item[1] for item in result)


def _ocr_cache_file(path):
    st = os.stat(path)
    key = hashlib.md5(f"{path}|{st.st_size}|{int(st.st_mtime)}".encode("utf-8")).hexdigest()
    return os.path.join(OCR_CACHE_DIR, key + ".json")


def _save_ocr_cache(cache_file, cache):
    os.makedirs(OCR_CACHE_DIR, exist_ok=True)
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False)


def _ocr_fill(path, pages):
    """Isi halaman yang kosong (hasil scan) dengan teks hasil OCR."""
    if not OCR_ENABLED:
        return pages
    kosong = [i for i, t in enumerate(pages) if len(t) < OCR_MIN_CHARS]
    if not kosong:
        return pages

    cache_file = _ocr_cache_file(path)
    cache = {}
    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                cache = json.load(f)
        except Exception:
            cache = {}

    todo = [i for i in kosong if str(i) not in cache]
    if todo:
        try:
            import fitz  # PyMuPDF
            logger.info(f"-> OCR {os.path.basename(path)}: {len(todo)} halaman (hanya sekali)...")
            fdoc = fitz.open(path)
            for n, i in enumerate(todo, 1):
                cache[str(i)] = " ".join(_ocr_page(fdoc, i).split())
                logger.info(f"   OCR hal {i + 1} selesai ({n}/{len(todo)})")
                if n % 5 == 0:
                    _save_ocr_cache(cache_file, cache)
            fdoc.close()
            _save_ocr_cache(cache_file, cache)
        except Exception as e:
            logger.error(f"OCR gagal untuk {path}: {e}")
            return pages

    for i in kosong:
        if cache.get(str(i)):
            pages[i] = cache[str(i)]
    return pages


# ---------------------------------------------------------------- baca PDF
def _load_pages(path):
    """Baca semua halaman PDF (sekali saja, lalu disimpan di cache)."""
    if path in _pages_cache:
        return _pages_cache[path]
    with _load_lock:
        if path in _pages_cache:
            return _pages_cache[path]
        logger.info(f"-> Mempelajari: {os.path.basename(path)} "
                    f"(folder {os.path.basename(os.path.dirname(path))})")
        pages = []
        try:
            reader = PdfReader(path)
            if reader.is_encrypted:
                try:
                    reader.decrypt("")
                except Exception:
                    pass
            for page in reader.pages:
                try:
                    text = page.extract_text() or ""
                except Exception:
                    text = ""
                pages.append(" ".join(text.split()))
            pages = _ocr_fill(path, pages)
        except Exception as e:
            logger.error(f"Gagal membaca {path}: {e}")
            return None
        _pages_cache[path] = pages
        return pages


def _page_count(path):
    if path in _pages_cache:
        return len(_pages_cache[path])
    try:
        return len(PdfReader(path).pages)
    except Exception:
        return None


def _warm_cache():
    """Baca seluruh PDF materi di latar belakang agar panggilan pertama tidak lambat."""
    try:
        docs = _get_docs()
        for d in docs:
            _load_pages(d["path"])
        total = sum(len(_pages_cache.get(d["path"], [])) for d in docs)
        logger.info(f"Selesai! {len(docs)} dokumen PDF ({total} halaman) siap dipakai.")
    except Exception as e:
        logger.error(f"Gagal memuat dokumen: {e}")


def _page_range(total, mulai, akhir):
    try:
        mulai = int(mulai or 1)
        akhir = int(akhir or 0)
    except (TypeError, ValueError):
        mulai, akhir = 1, 0
    mulai = max(1, mulai)
    if mulai > total:
        return None
    if akhir <= 0 or akhir > total:
        akhir = total
    if akhir < mulai:
        akhir = mulai
    return mulai, akhir


SCAN_MSG = ("Dokumen ini tidak memiliki teks yang bisa dibaca (kemungkinan hasil scan/gambar). "
            "Perlu OCR terlebih dahulu.")

# ---------------------------------------------------------------- peringkasan
STOPWORDS = set("""
yang dan di ke dari untuk pada dengan adalah ini itu atau dalam juga akan dapat tidak oleh
sebagai karena agar jika maka saat para serta lebih sangat sudah telah bisa harus antara
setiap suatu sebuah tersebut yaitu yakni bahwa kita kami anda mereka dia ia nya pun lagi
the and for are was were with that this from have has had not but you your can will
of to in is it as by on at an be or if we they their its
""".split())

_SENT_SPLIT = re.compile(r'(?<=[.!?])\s+(?=[A-Z0-9"(])')
_BULLETS = re.compile(r'[•●▪■◦○➢➤✓✔]')


def _tokens(s):
    return [w for w in re.findall(r"[a-zA-Z]{3,}", s.lower()) if w not in STOPWORDS]


def _split_sentences(text, minimal):
    sents = []
    for s in _SENT_SPLIT.split(text):
        s = s.strip()
        letters = len(re.findall(r"[A-Za-z]", s))
        if 40 <= len(s) <= 320 and letters > len(s) * 0.5:
            sents.append(s)
    if len(sents) >= minimal:
        return sents

    # Cadangan untuk materi bergaya slide (banyak poin tanpa titik)
    pieces = []
    for part in _BULLETS.split(text):
        words = part.split()
        for i in range(0, len(words), 28):
            seg = " ".join(words[i:i + 28]).strip()
            if len(seg) >= 40:
                pieces.append(seg)
    return pieces if len(pieces) > len(sents) else sents


def _summarize_text(text, jumlah_poin):
    sents = _split_sentences(text, jumlah_poin)
    if not sents:
        return [], []

    all_tokens, sent_tokens = [], []
    for s in sents:
        t = _tokens(s)
        sent_tokens.append(t)
        all_tokens.extend(t)
    freq = Counter(all_tokens)

    scores = []
    for t in sent_tokens:
        scores.append(sum(freq[w] for w in set(t)) / (len(t) ** 0.6) if t else 0.0)

    # Satu kalimat terbaik di tiap bagian dokumen, supaya seluruh isi terwakili
    n = min(jumlah_poin, len(sents))
    size = len(sents) / n
    chosen = []
    for b in range(n):
        lo = int(b * size)
        hi = max(int((b + 1) * size), lo + 1)
        bucket = range(lo, min(hi, len(sents)))
        chosen.append(max(bucket, key=lambda i: scores[i]))
    chosen = sorted(set(chosen))

    kata_kunci = [w for w, _ in freq.most_common(30) if len(w) >= 4][:8]
    return [sents[i] for i in chosen], kata_kunci

# ---------------------------------------------------------------- log lokal
def simpan_ke_log_lokal(query, result):
    log_file = os.path.join(BASE_DIR, "mcp_chat_log.json")
    try:
        data = []
        if os.path.exists(log_file):
            with open(log_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

        data.append({
            "waktu": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "pertanyaan": query,
            "jawaban_sistem": result
        })

        with open(log_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Gagal menyimpan log: {e}")

# ---------------------------------------------------------------- logika tool
def _list_documents(mata_kuliah):
    docs = _filter_mk(_get_docs(), mata_kuliah)
    if not docs:
        if mata_kuliah:
            return {"success": False,
                    "result": f"Mata kuliah '{mata_kuliah}' tidak dikenali. Yang tersedia: {_course_names()}."}
        return {"success": False, "result": "Tidak ada file PDF yang ditemukan di folder materi."}

    grup = {}
    for d in docs:
        grup.setdefault(d["mk"], []).append({"nama": d["name"], "jumlah_halaman": _page_count(d["path"])})
    return {"success": True, "jumlah_dokumen": len(docs),
            "mata_kuliah": [{"nama": mk, "dokumen": items} for mk, items in grup.items()]}


def _read_document(nama_file, halaman_mulai, halaman_akhir, mata_kuliah):
    doc, err = _resolve(nama_file, mata_kuliah)
    if err:
        return {"success": False, "result": err}
    pages = _load_pages(doc["path"])
    if pages is None:
        return {"success": False, "result": f"Gagal membaca file {doc['name']}."}
    if not any(pages):
        return {"success": False, "result": SCAN_MSG}

    rng = _page_range(len(pages), halaman_mulai, halaman_akhir)
    if rng is None:
        return {"success": False,
                "result": f"Halaman {halaman_mulai} melebihi jumlah halaman ({len(pages)})."}
    mulai, akhir = rng

    out, used, last, terpotong = [], 0, mulai - 1, False
    for n in range(mulai, akhir + 1):
        t = pages[n - 1]
        if not t:
            last = n
            continue
        chunk = f"[Hal {n}] {t}"
        if used + len(chunk) > MAX_CHARS:
            if not out:  # satu halaman saja sudah melebihi batas
                chunk = chunk[:MAX_CHARS] + "..."
                out.append(chunk)
                last = n
                terpotong = True
            break
        out.append(chunk)
        used += len(chunk)
        last = n

    hasil = {
        "success": True,
        "mata_kuliah": doc["mk"],
        "sumber": doc["name"],
        "total_halaman": len(pages),
        "halaman_dibaca": f"{mulai}-{last}",
        "teks": " ".join(out),
        "masih_ada_lanjutan": last < akhir,
    }
    if last < akhir:
        hasil["lanjut_dari_halaman"] = last + 1
    if terpotong:
        hasil["catatan"] = "Teks halaman ini terlalu panjang dan dipotong."
    return hasil


def _summarize_doc(doc, halaman_mulai, halaman_akhir, jumlah_poin):
    pages = _load_pages(doc["path"])
    if pages is None:
        return {"success": False, "result": f"Gagal membaca file {doc['name']}."}
    if not any(pages):
        return {"success": False, "result": SCAN_MSG}

    rng = _page_range(len(pages), halaman_mulai, halaman_akhir)
    if rng is None:
        return {"success": False,
                "result": f"Halaman {halaman_mulai} melebihi jumlah halaman ({len(pages)})."}
    mulai, akhir = rng

    try:
        jumlah_poin = max(3, min(10, int(jumlah_poin)))
    except (TypeError, ValueError):
        jumlah_poin = 6

    poin, kata_kunci = _summarize_text(" ".join(pages[mulai - 1:akhir]), jumlah_poin)
    if not poin:
        return {"success": False, "result": "Teks pada halaman tersebut terlalu sedikit untuk diringkas."}

    return {
        "success": True,
        "mata_kuliah": doc["mk"],
        "sumber": doc["name"],
        "halaman": f"{mulai}-{akhir}",
        "total_halaman": len(pages),
        "kata_kunci": kata_kunci,
        "poin_ringkasan": poin,
        "petunjuk": ("Ini ringkasan otomatis berupa kalimat-kalimat penting dari dokumen. "
                     "Sampaikan kembali dengan bahasa Indonesia yang singkat dan natural, "
                     "jangan menambah informasi yang tidak ada di poin ini."),
    }


def _summarize_document(nama_file, halaman_mulai, halaman_akhir, jumlah_poin, mata_kuliah):
    doc, err = _resolve(nama_file, mata_kuliah)
    if err:
        return {"success": False, "result": err}
    return _summarize_doc(doc, halaman_mulai, halaman_akhir, jumlah_poin)


def _summarize_course(mata_kuliah, poin_per_dokumen):
    docs = _filter_mk(_get_docs(), mata_kuliah)
    if not docs:
        return {"success": False,
                "result": f"Mata kuliah '{mata_kuliah}' tidak dikenali. Yang tersedia: {_course_names()}."}
    if len(docs) == 1:  # satu dokumen saja: ringkas lebih rinci
        return _summarize_doc(docs[0], 1, 0, 6)

    try:
        poin_per_dokumen = max(1, min(3, int(poin_per_dokumen)))
    except (TypeError, ValueError):
        poin_per_dokumen = 1

    items = []
    for d in docs[:15]:
        pages = _load_pages(d["path"])
        if not pages or not any(pages):
            items.append({"dokumen": d["name"], "ringkas": [], "catatan": "tidak ada teks terbaca"})
            continue
        poin, kata = _summarize_text(" ".join(pages), poin_per_dokumen)
        items.append({"dokumen": d["name"], "kata_kunci": kata[:4],
                      "ringkas": [p if len(p) <= 200 else p[:197] + "..." for p in poin]})
    return {
        "success": True,
        "mata_kuliah": docs[0]["mk"],
        "jumlah_dokumen": len(docs),
        "ringkasan_per_dokumen": items,
        "petunjuk": ("Rangkum per pertemuan secara singkat dan natural dalam bahasa Indonesia. "
                     "Untuk detail satu dokumen, gunakan summarize_document."),
    }


def _search(query, mata_kuliah):
    docs = _filter_mk(_get_docs(), mata_kuliah)
    if not docs:
        return None
    q = query.lower().strip()
    words = [w for w in re.findall(r"[a-z0-9]{3,}", q) if w not in STOPWORDS]

    def snippet_at(text, idx):
        start = max(0, idx - 100)
        end = min(len(text), idx + 300)
        s = text[start:end]
        return ("..." if start > 0 else "") + s + ("..." if end < len(text) else "")

    exact, loose = [], []
    for d in docs:
        pages = _load_pages(d["path"])
        if not pages:
            continue
        for i, teks in enumerate(pages):
            low = teks.lower()
            idx = low.find(q) if q else -1
            if idx >= 0:
                exact.append(f"[{d['name']} - Hal {i + 1}]: {snippet_at(teks, idx)}")
            elif words and all(w in low for w in words):
                loose.append(f"[{d['name']} - Hal {i + 1}]: {snippet_at(teks, low.find(words[0]))}")
    return (exact or loose)[:4]

# ---------------------------------------------------------------- tool MCP
@mcp.tool()
def list_documents(mata_kuliah: str = "") -> dict:
    """
    Tampilkan daftar dokumen PDF materi kuliah beserta jumlah halamannya, dikelompokkan
    per mata kuliah (Pemrograman Berorientasi Objek / PBO dan Pemrograman Web Lanjut).
    mata_kuliah: kosong = semua, atau isi misalnya "pbo" / "web lanjut".
    Gunakan saat user bertanya materi apa saja yang ada.
    """
    logger.info(f"Xiaozhi meminta daftar dokumen ({mata_kuliah or 'semua'})")
    return _list_documents(mata_kuliah)


@mcp.tool()
def read_document(nama_file: str = "", halaman_mulai: int = 1, halaman_akhir: int = 0,
                  mata_kuliah: str = "") -> dict:
    """
    Baca isi satu dokumen PDF materi kuliah per rentang halaman.
    nama_file: nama dokumen, boleh sebagian saja (mis. "blade engine", "view data"), atau
    nomor pertemuan (mis. "4"). Boleh kosong jika mata_kuliah hanya punya satu dokumen.
    halaman_mulai: halaman awal (default 1). halaman_akhir: 0 berarti sampai akhir dokumen.
    mata_kuliah: opsional ("pbo" atau "web lanjut") untuk mempersempit pencarian dokumen.
    Hasil dibatasi panjangnya; jika masih ada lanjutan, panggil lagi dengan
    halaman_mulai = lanjut_dari_halaman.
    """
    logger.info(f"Xiaozhi membaca: '{nama_file}' hal {halaman_mulai}-{halaman_akhir}")
    hasil = _read_document(nama_file, halaman_mulai, halaman_akhir, mata_kuliah)
    simpan_ke_log_lokal(f"read_document: {nama_file} {halaman_mulai}-{halaman_akhir}",
                        "berhasil" if hasil.get("success") else hasil.get("result", "gagal"))
    return hasil


@mcp.tool()
def summarize_document(nama_file: str = "", halaman_mulai: int = 1, halaman_akhir: int = 0,
                       jumlah_poin: int = 6, mata_kuliah: str = "") -> dict:
    """
    Ringkas SATU dokumen PDF materi kuliah menjadi poin-poin penting beserta kata kunci.
    Gunakan saat user meminta ringkasan, inti, atau poin penting suatu materi/pertemuan.
    nama_file: nama dokumen (boleh sebagian, mis. "model factories") atau nomor pertemuan.
    halaman_mulai / halaman_akhir: batasi ke bab atau halaman tertentu (0 = sampai akhir).
    jumlah_poin: 3 sampai 10 (default 6).
    mata_kuliah: opsional ("pbo" atau "web lanjut").
    Setelah menerima hasilnya, sampaikan ringkasan dengan bahasa singkat dan natural.
    """
    logger.info(f"Xiaozhi meringkas: '{nama_file}' hal {halaman_mulai}-{halaman_akhir}")
    hasil = _summarize_document(nama_file, halaman_mulai, halaman_akhir, jumlah_poin, mata_kuliah)
    simpan_ke_log_lokal(f"summarize_document: {nama_file} {halaman_mulai}-{halaman_akhir}",
                        f"{len(hasil.get('poin_ringkasan', []))} poin"
                        if hasil.get("success") else hasil.get("result", "gagal"))
    return hasil


@mcp.tool()
def summarize_course(mata_kuliah: str, poin_per_dokumen: int = 1) -> dict:
    """
    Ringkas SELURUH dokumen PDF dalam satu mata kuliah sekaligus (satu bagian singkat per
    pertemuan/dokumen). Gunakan saat user meminta ringkasan seluruh materi mata kuliah,
    misalnya "ringkas semua materi web lanjut". Untuk satu dokumen saja gunakan
    summarize_document.
    mata_kuliah: "pbo" atau "web lanjut".
    poin_per_dokumen: 1 sampai 3 (default 1).
    """
    logger.info(f"Xiaozhi meringkas seluruh mata kuliah: '{mata_kuliah}'")
    hasil = _summarize_course(mata_kuliah, poin_per_dokumen)
    simpan_ke_log_lokal(f"summarize_course: {mata_kuliah}",
                        "berhasil" if hasil.get("success") else hasil.get("result", "gagal"))
    return hasil


@mcp.tool()
def search_knowledge_base(query: str, mata_kuliah: str = "") -> dict:
    """
    Gunakan tool ini untuk mencari materi, definisi, atau informasi dari semua modul perkuliahan/dokumen.
    mata_kuliah: opsional ("pbo" atau "web lanjut") untuk membatasi pencarian.
    """
    logger.info(f"Xiaozhi sedang mencari: '{query}' ({mata_kuliah or 'semua mata kuliah'})")

    results = _search(query, mata_kuliah)
    if results is None:
        pesan = "Basis pengetahuan kosong atau mata kuliah tidak dikenali."
        simpan_ke_log_lokal(query, pesan)
        return {"success": False, "result": pesan}

    if results:
        hasil_akhir = f"Informasi ditemukan: {' | '.join(results)}"
        simpan_ke_log_lokal(query, hasil_akhir)
        return {"success": True, "result": hasil_akhir}

    pesan_gagal = f"Maaf, tidak ditemukan informasi mengenai '{query}' di dalam semua modul."
    simpan_ke_log_lokal(query, pesan_gagal)
    return {"success": False, "result": pesan_gagal}


# ---------------------------------------------------------------- tool musik (digabung)
# Tool lagu_viral_indonesia & cari_lagu_indonesia ada di music_id.py. Digabung ke server ini
# agar Xiaozhi hanya perlu satu koneksi MCP. Jika modulnya bermasalah, tool materi tetap jalan.
try:
    import music_id
    music_id.register(mcp)
    logger.info("Tool musik Indonesia aktif: lagu_viral_indonesia, cari_lagu_indonesia")
except Exception as e:
    logger.warning(f"Tool musik tidak aktif: {type(e).__name__}: {e}")

try:
    import web_google
    web_google.register(mcp)
except Exception as e:
    logger.warning(f"Tool web google tidak aktif: {type(e).__name__}: {e}")

if __name__ == "__main__":
    if "--prewarm" in sys.argv:
        # Jalankan sekali secara manual: python kb_search.py --prewarm
        # Semua PDF scan di-OCR dan disimpan ke .ocr_cache, lalu program selesai.
        _warm_cache()
        sys.exit(0)
    ditemukan = _get_docs()
    logger.info(f"Folder materi: {', '.join(MATERI_FOLDERS)} ({len(ditemukan)} file PDF ditemukan)")
    threading.Thread(target=_warm_cache, daemon=True).start()  # muat semua PDF di latar belakang
    mcp.run(transport="stdio")