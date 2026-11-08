import os
import requests
from mcp.server.fastmcp import FastMCP

# Inisialisasi server MCP
mcp = FastMCP("ESP32_S3_ChatBot_Server")

# ==========================================
# 1. Tool untuk Menjalankan Servo
# ==========================================
@mcp.tool()
def control_servo(angle: int, esp32_ip: str) -> str:
    """
    Mengirim perintah eksternal ke ESP32 untuk mengatur sudut servo SG90.
    Catatan: Secara internal ESP32 sudah mendaftarkan tool 'self.servo.set_angle',
    namun fungsi Python ini berfungsi sebagai jembatan remote jika LLM berjalan di PC.
    
    Args:
        angle: Sudut servo (0-180 derajat).
        esp32_ip: Alamat IP lokal dari perangkat ESP32.
    """
    if not (0 <= angle <= 180):
        return "Error: Sudut servo harus berada di antara 0 dan 180 derajat."
    
    try:
        # Mengasumsikan Anda membuat endpoint HTTP sederhana di ESP32 untuk menerima perintah
        url = f"http://{esp32_ip}/api/servo?angle={angle}"
        response = requests.get(url, timeout=5)
        
        if response.status_code == 200:
            return f"Berhasil! Servo bergerak ke sudut {angle}°."
        else:
            return f"Gagal mengontrol servo. HTTP Status: {response.status_code}"
    except requests.exceptions.RequestException as e:
        return f"Gagal terhubung ke ESP32 (IP: {esp32_ip}). Error: {str(e)}"

# ==========================================
# 2. Tool untuk Mengambil Data GPS dari Telegram Bot
# ==========================================
@mcp.tool()
def get_gps_from_telegram() -> str:
    """
    Mengambil data koordinat lokasi terakhir dari bot Telegram.
    Sistem akan memindai riwayat pembaruan untuk mencari tautan Google Maps.
    """
    # Kredensial sesuai dengan konfigurasi pada ESP32
    bot_token = "8333104105:AAGCv7D54Yfo9AM7_xt1m6_1THL32S15AkE"
    chat_id = "5914797003"
    
    try:
        url = f"https://api.telegram.org/bot{bot_token}/getUpdates"
        response = requests.get(url, timeout=10)
        data = response.json()
        
        if data.get("ok") and data.get("result"):
            # Lakukan iterasi mundur untuk mendapatkan lokasi paling baru
            for update in reversed(data["result"]):
                message = update.get("message", {})
                text = message.get("text", "")
                
                # Verifikasi bahwa pesan dikirim ke/dari CHAT_ID yang berwenang
                if str(message.get("chat", {}).get("id")) == chat_id:
                    if "google.com/maps" in text:
                        return f"Data GPS terbaru ditemukan: {text}"
            
            return "Tidak ada tautan lokasi GPS yang ditemukan di riwayat terbaru bot."
        else:
            return "Gagal mendapatkan riwayat pembaruan dari Telegram API."
    except Exception as e:
        return f"Terjadi kesalahan saat menghubungi API Telegram: {str(e)}"

# ==========================================
# 3. Tool untuk Membaca Dokumen di PC
# ==========================================
@mcp.tool()
def read_pc_document(file_path: str) -> str:
    """
    Membaca isi dokumen (TXT, MD, JSON, dsb) secara langsung dari sistem file PC lokal.
    Sangat berguna untuk menyuntikkan dokumen teknis atau silabus ke dalam konteks AI.
    
    Args:
        file_path: Path absolut ke dokumen (misal: /home/saifulnb/docs/referensi.md 
                   atau C:\\Users\\saifulnb\\Documents\\referensi.txt)
    """
    if not os.path.exists(file_path):
        return f"Error: File '{file_path}' tidak ditemukan di komputer lokal."
    
    if not os.path.isfile(file_path):
        return f"Error: '{file_path}' adalah direktori, bukan sebuah file."
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return f"--- Mulai Isi File: {os.path.basename(file_path)} ---\n\n{content}\n\n--- Selesai ---"
    except UnicodeDecodeError:
        return f"Gagal membaca '{file_path}'. Pastikan format file berupa teks (bukan biner/PDF terenkripsi)."
    except Exception as e:
        return f"Gagal membuka file. Terjadi kesalahan izin akses atau I/O: {str(e)}"

if __name__ == "__main__":
    print("Memulai Server MCP untuk ESP32 ChatBot AI...")
    # Blokir dan biarkan server standby menerima permintaan tool call
    mcp.run()