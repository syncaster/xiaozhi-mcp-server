from flask import Flask, render_template_string
import json
import os

app = Flask(__name__)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Xiaozhi Local MCP Log</title>
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f4f7f6; margin: 0; padding: 20px; }
        .container { max-width: 900px; margin: 0 auto; background: white; padding: 20px 30px; border-radius: 12px; box-shadow: 0 5px 15px rgba(0,0,0,0.05); }
        h2 { color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 10px; }
        .chat-card { background: #fff; border: 1px solid #e1e8ed; border-radius: 8px; padding: 15px; margin-bottom: 15px; transition: 0.3s; }
        .chat-card:hover { box-shadow: 0 4px 10px rgba(0,0,0,0.1); }
        .time { font-size: 12px; color: #7f8c8d; text-align: right; }
        .query { font-weight: 600; color: #e74c3c; margin: 5px 0 10px 0; font-size: 16px; }
        .result { background: #f8f9fa; border-left: 4px solid #2ecc71; padding: 12px; font-size: 14px; color: #34495e; line-height: 1.5; white-space: pre-wrap;}
        .refresh-btn { display: inline-block; padding: 10px 20px; background: #3498db; color: white; text-decoration: none; border-radius: 5px; margin-bottom: 20px;}
        .refresh-btn:hover { background: #2980b9; }
    </style>
</head>
<body>
    <div class="container">
        <h2>📡 Riwayat Penarikan Data (Localhost)</h2>
        <a href="/" class="refresh-btn">🔄 Refresh Data</a>
        
        {% if logs %}
            {% for item in logs | reverse %}
            <div class="chat-card">
                <div class="time">{{ item.waktu }}</div>
                <div class="query">🤖 Pertanyaan AI: "{{ item.pertanyaan }}"</div>
                <div class="result"><strong>Data yang dikirim komputer ke AI:</strong><br>{{ item.jawaban_sistem }}</div>
            </div>
            {% endfor %}
        {% else %}
            <div class="chat-card">
                <p style="text-align:center; color:#7f8c8d;">Belum ada interaksi. Cobalah bertanya kepada Xiaozhi.</p>
            </div>
        {% endif %}
    </div>
</body>
</html>
"""

@app.route('/')
def index():
    logs = []
    log_file = "mcp_chat_log.json"
    if os.path.exists(log_file):
        with open(log_file, "r", encoding="utf-8") as f:
            try:
                logs = json.load(f)
            except json.JSONDecodeError:
                pass
    return render_template_string(HTML_TEMPLATE, logs=logs)

if __name__ == '__main__':
    # Berjalan di port 5000 localhost
    print("Web server berjalan! Buka http://localhost:5000 di browser Anda.")
    app.run(debug=True, port=5000, host='0.0.0.0')