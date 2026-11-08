# servo.py
from fastmcp import FastMCP
import sys
import logging
import time

logger = logging.getLogger('ServoMCP')

# Fix UTF-8 encoding for Windows console
if sys.platform == 'win32':
    sys.stderr.reconfigure(encoding='utf-8')
    sys.stdout.reconfigure(encoding='utf-8')

# ==================== KONFIGURASI ====================
# Ganti sesuai kebutuhan Anda
SERVO_METHOD = "serial"          # Pilihan: "print", "serial", "http"
SERIAL_PORT = "COM12"            # Windows: COM3, COM4...  | Linux/Mac: /dev/ttyUSB0
SERIAL_BAUDRATE = 115200
# =====================================================

mcp = FastMCP("ServoController")

# Variabel status servo (simulasi)
current_angle = 90

def send_to_servo(angle: int) -> str:
    """Fungsi inti mengirim perintah ke servo"""
    global current_angle
    angle = max(0, min(180, angle))  # Batasi 0-180

    if SERVO_METHOD == "print":
        # Mode testing (hanya print)
        logger.info(f"[SIMULASI] Servo bergerak ke {angle}°")
        current_angle = angle
        return f"Servo berhasil diatur ke {angle} derajat (simulasi)"

    elif SERVO_METHOD == "serial":
        # Mode Serial (paling umum untuk ESP32)
        try:
            import serial
            with serial.Serial(SERIAL_PORT, SERIAL_BAUDRATE, timeout=1) as ser:
                # Format perintah: "SERVO:90\n"  (sesuaikan dengan firmware ESP32 Anda)
                command = f"SERVO:{angle}\n"
                ser.write(command.encode())
                time.sleep(0.1)
                current_angle = angle
                logger.info(f"Kirim serial: {command.strip()}")
                return f"Servo diatur ke {angle} derajat via serial ({SERIAL_PORT})"
        except Exception as e:
            logger.error(f"Gagal kirim serial: {e}")
            return f"Gagal mengontrol servo: {str(e)}"

    elif SERVO_METHOD == "http":
        # Mode HTTP (jika ESP32 punya web server)
        try:
            import requests
            # Ganti IP sesuai ESP32 Anda
            url = f"http://192.168.1.100/servo?angle={angle}"
            resp = requests.get(url, timeout=3)
            current_angle = angle
            return f"Servo diatur ke {angle} derajat via HTTP"
        except Exception as e:
            return f"Gagal HTTP: {str(e)}"

    return "Metode kontrol tidak dikenali"


@mcp.tool()
def set_servo_angle(angle: int) -> dict:
    """
    Mengatur sudut servo motor SG90 ke posisi tertentu.
    Gunakan tool ini setiap kali user ingin menggerakkan servo.
    angle: sudut target antara 0 sampai 180 derajat.
    """
    logger.info(f"Menerima perintah set_servo_angle: {angle}")
    result_msg = send_to_servo(angle)
    return {
        "success": True,
        "angle": angle,
        "message": result_msg
    }


@mcp.tool()
def get_servo_position() -> dict:
    """
    Mendapatkan posisi sudut servo saat ini.
    """
    return {
        "success": True,
        "current_angle": current_angle,
        "message": f"Posisi servo sekarang {current_angle} derajat"
    }


@mcp.tool()
def reset_servo() -> dict:
    """
    Mengembalikan servo ke posisi tengah (90 derajat).
    """
    result_msg = send_to_servo(90)
    return {
        "success": True,
        "angle": 90,
        "message": result_msg
    }


@mcp.tool()
def move_servo(degrees: int) -> dict:
    """
    Menggerakkan servo secara relatif dari posisi sekarang.
    degrees positif = searah jarum jam, negatif = berlawanan arah.
    Contoh: degrees=30 berarti putar 30 derajat dari posisi sekarang.
    """
    new_angle = current_angle + degrees
    result_msg = send_to_servo(new_angle)
    return {
        "success": True,
        "moved_by": degrees,
        "new_angle": current_angle,
        "message": result_msg
    }


if __name__ == "__main__":
    mcp.run(transport="stdio")