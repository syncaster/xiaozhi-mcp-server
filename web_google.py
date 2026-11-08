# web_google.py
# Tool pencarian internet berbasis hasil Google untuk Xiaozhi (MCP).
# Dipakai dari kb_search.py:
#     import web_google
#     web_google.register(mcp)
#
# Butuh di file .env:
#     SERPER_API_KEY=isi_api_key_dari_serper.dev
# (opsional, cadangan tanpa API key: pip install ddgs)
import logging
import os
import sys
import threading
import time

import requests

logger = logging.getLogger("WebGoogle")

SERPER_KEY = os.environ.get("SERPER_API_KEY", "").strip()
SERPER_URL = "https://google.serper.dev"
MAX_RESULTS = 5
MAX_SNIPPET = 220  # dipendekkan supaya enak dibacakan oleh perangkat

# Cache hasil di memori: pertanyaan yang sama dalam waktu singkat tidak memakai kredit lagi.
CACHE_TTL = 15 * 60      # detik (15 menit). Perkecil jika butuh berita yang sangat segar.
CACHE_MAX = 100          # jumlah maksimum entri yang disimpan
_cache = {}              # key -> (waktu_simpan, hasil)
_cache_lock = threading.Lock()


def _cache_key(query, berita, waktu):
    return (" ".join(query.lower().split()), bool(berita), waktu or "")


def _cache_get(key):
    with _cache_lock:
        item = _cache.get(key)
        if item and time.time() - item[0] < CACHE_TTL:
            return item[1]
        _cache.pop(key, None)
    return None


def _cache_put(key, hasil):
    with _cache_lock:
        if len(_cache) >= CACHE_MAX:
            # buang entri paling lama
            oldest = min(_cache, key=lambda k: _cache[k][0])
            _cache.pop(oldest, None)
        _cache[key] = (time.time(), hasil)


# parameter waktu Google (tbs)
_WAKTU = {"jam": "qdr:h", "hari": "qdr:d", "minggu": "qdr:w", "bulan": "qdr:m", "tahun": "qdr:y"}


def _cut(s, n=MAX_SNIPPET):
    s = " ".join((s or "").split())
    return s if len(s) <= n else s[: n - 3] + "..."


def _serper(query, berita, waktu):
    endpoint = "/news" if berita else "/search"
    payload = {"q": query, "gl": "id", "hl": "id", "num": MAX_RESULTS}
    if waktu in _WAKTU:
        payload["tbs"] = _WAKTU[waktu]
    r = requests.post(
        SERPER_URL + endpoint,
        headers={"X-API-KEY": SERPER_KEY, "Content-Type": "application/json"},
        json=payload,
        timeout=15,
    )
    r.raise_for_status()
    data = r.json()

    hasil = []
    box = data.get("answerBox") or {}
    jawaban = box.get("answer") or box.get("snippet")
    if jawaban:
        hasil.append({"judul": "Jawaban langsung", "ringkas": _cut(jawaban, 300)})

    for it in (data.get("news") if berita else data.get("organic")) or []:
        item = {"judul": _cut(it.get("title"), 120), "ringkas": _cut(it.get("snippet"))}
        if it.get("date"):
            item["tanggal"] = it["date"]
        if it.get("source"):
            item["sumber"] = it["source"]
        hasil.append(item)
    return hasil[: MAX_RESULTS + 1]


def _ddg(query, berita, waktu):
    from ddgs import DDGS  # cadangan tanpa API key

    t = {"hari": "d", "minggu": "w", "bulan": "m", "tahun": "y"}.get(waktu)
    with DDGS() as d:
        rows = (d.news(query, region="id-id", timelimit=t, max_results=MAX_RESULTS)
                if berita else
                d.text(query, region="id-id", timelimit=t, max_results=MAX_RESULTS))
    return [{"judul": _cut(x.get("title"), 120),
             "ringkas": _cut(x.get("body")),
             **({"tanggal": x["date"]} if x.get("date") else {})} for x in rows]


def cari(query, berita=False, waktu=""):
    query = (query or "").strip()
    if not query:
        return {"success": False, "result": "Kata kunci pencarian kosong."}

    key = _cache_key(query, berita, waktu)
    tersimpan = _cache_get(key)
    if tersimpan is not None:
        logger.info(f"Cache hit: '{query}' (tanpa memakai kredit)")
        return tersimpan

    try:
        if SERPER_KEY:
            hasil = _serper(query, berita, waktu)
            mesin = "Google"
        else:
            hasil = _ddg(query, berita, waktu)
            mesin = "DuckDuckGo"
    except Exception as e:
        logger.error(f"Pencarian gagal: {type(e).__name__}: {e}")
        return {"success": False, "result": f"Pencarian internet gagal: {type(e).__name__}"}

    if not hasil:
        return {"success": False, "result": f"Tidak ada hasil untuk '{query}'."}
    out = {
        "success": True,
        "mesin": mesin,
        "query": query,
        "hasil": hasil,
        "petunjuk": ("Rangkum hasil ini dalam bahasa Indonesia, singkat dan natural (maksimal "
                     "3 kalimat). Sebutkan tanggal jika ada. Jangan menambah info yang tidak "
                     "ada di hasil, dan jangan membacakan URL."),
    }
    _cache_put(key, out)  # hanya hasil sukses yang disimpan
    return out


def register(mcp):
    @mcp.tool()
    def cari_web_google(query: str, berita: bool = False, waktu: str = "") -> dict:
        """
        PENCARIAN INTERNET UTAMA. Selalu pakai tool ini, bukan web_search bawaan, untuk
        informasi terbaru: berita, jadwal pertandingan (MPL, sepak bola, dll), skor, cuaca
        kota, harga, kurs, tokoh, dan peristiwa hari ini. Hasil berasal dari Google
        (bahasa Indonesia, wilayah Indonesia).
        query: kata kunci singkat, mis. "jadwal final MPL ID season 18".
        berita: true untuk mencari berita terbaru.
        waktu: batasi hasil ke "jam", "hari", "minggu", "bulan", atau "tahun"
               (kosong = semua waktu). Untuk "hari ini" isi "hari".
        """
        logger.info(f"Xiaozhi mencari web: '{query}' (berita={berita}, waktu={waktu or '-'})")
        return cari(query, berita, waktu)

    logger.info(f"Tool cari_web_google aktif (mesin: {'Google/Serper' if SERPER_KEY else 'DuckDuckGo'})")