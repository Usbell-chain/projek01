import os
import threading
import subprocess
import requests
import time
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

# Lokasi Dasar
HOME_DIR = os.path.expanduser('~')
BASE_PICTURES = os.path.join(HOME_DIR, 'Pictures')

# Status Global
status_data = {
    'text': 'Siap...',
    'percent': 0,
    'status': 'idle'
}

# --- SCAN URL ---
@app.route('/scan', methods=['POST'])
def scan_url():
    raw_url = request.json.get('url')
    if not raw_url: return jsonify({'status': 'error', 'message': 'URL kosong'})

    # TIKTOK: Bypass Preview
    if "tiktok.com" in raw_url:
        return jsonify({
            'status': 'success',
            'mode': 'bulk_tiktok',
            'message': 'TikTok Slide Terdeteksi (Mode API)'
        })

    # INSTAGRAM: Pakai Gallery-DL
    try:
        command = ["gallery-dl", "-g", "--cookies-from-browser", "brave", raw_url]
        result = subprocess.run(command, capture_output=True, text=True)

        if result.returncode == 0:
            raw_links = result.stdout.strip().split('\n')
            valid_links = [link for link in raw_links if link.startswith('http')]
            if not valid_links:
                 return jsonify({'status': 'error', 'message': 'Tidak ada gambar ditemukan.'})
            return jsonify({
                'status': 'success',
                'mode': 'select_ig',
                'images': valid_links,
                'count': len(valid_links)
            })
        else:
            return jsonify({'status': 'error', 'message': "Gagal Scan IG (Cek Login Brave)"})

    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})


# --- EKSEKUTOR TIKTOK (JALUR BELAKANG / API) ---
def run_tiktok_api(url):
    global status_data
    status_data['status'] = 'downloading'

    TARGET_FOLDER = os.path.join(BASE_PICTURES, 'TikTok')
    if not os.path.exists(TARGET_FOLDER): os.makedirs(TARGET_FOLDER)

    try:
        status_data['percent'] = 10
        status_data['text'] = "Menghubungi Server TikWM..."

        # 1. TEMBAK KE API PUBLIK (TikWM)
        # Ini akan mengembalikan JSON berisi link gambar yang bersih
        api_url = "https://www.tikwm.com/api/"
        payload = {'url': url, 'hd': 1}

        req = requests.post(api_url, data=payload)
        resp = req.json()

        image_urls = []

        # 2. AMBIL LIST GAMBAR DARI RESPON
        if resp.get('code') == 0:
            data = resp.get('data', {})
            if 'images' in data:
                image_urls = data['images']
            else:
                # Kalau ternyata bukan slide, tapi video single (ambil covernya)
                if 'cover' in data: image_urls.append(data['cover'])
        else:
            raise Exception("Gagal mengambil data dari API (Link Private/Salah).")

        if not image_urls:
            raise Exception("Tidak ada gambar ditemukan.")

        # 3. DOWNLOAD MANUAL
        total = len(image_urls)
        print(f"API Berhasil: Ditemukan {total} slide.")

        # Headers standar
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }

        success_count = 0
        for i, img_url in enumerate(image_urls):
            current = i + 1
            status_data['percent'] = (current / total) * 100
            status_data['text'] = f"Menyimpan Slide {current} dari {total}..."

            try:
                response = requests.get(img_url, headers=headers, stream=True)
                if response.status_code == 200:
                    filename = f"TK_{int(time.time())}_{current}.jpg"
                    full_path = os.path.join(TARGET_FOLDER, filename)

                    with open(full_path, 'wb') as f:
                        for chunk in response.iter_content(1024):
                            f.write(chunk)
                    success_count += 1
            except: pass

        status_data['status'] = 'finished'
        status_data['percent'] = 100
        status_data['text'] = f"Selesai! {success_count} slide tersimpan."

    except Exception as e:
        print(f"Error TikTok API: {e}")
        status_data['status'] = 'error'
        status_data['text'] = "Gagal memproses (Server API sibuk/Link salah)"


# --- EKSEKUTOR IG ---
def run_ig_manual(selected_urls):
    global status_data
    status_data['status'] = 'downloading'
    total = len(selected_urls)
    TARGET_FOLDER = os.path.join(BASE_PICTURES, 'Instagram')
    if not os.path.exists(TARGET_FOLDER): os.makedirs(TARGET_FOLDER)

    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}

    for i, img_url in enumerate(selected_urls):
        try:
            current = i + 1
            status_data['percent'] = (current / total) * 100
            status_data['text'] = f"Menyimpan ke Instagram ({current}/{total})..."
            response = requests.get(img_url, headers=headers, stream=True)
            if response.status_code == 200:
                filename = f"IG_{int(time.time())}_{current}.jpg"
                full_path = os.path.join(TARGET_FOLDER, filename)
                with open(full_path, 'wb') as f:
                    for chunk in response.iter_content(1024):
                        f.write(chunk)
        except: pass

    status_data['status'] = 'finished'
    status_data['percent'] = 100
    status_data['text'] = "Selesai! Cek folder Pictures/Instagram"


@app.route('/')
def home():
    return render_template('index.html')

@app.route('/action', methods=['POST'])
def action():
    data = request.json
    mode = data.get('mode')

    if mode == 'tiktok':
        url = data.get('url')
        t = threading.Thread(target=run_tiktok_api, args=(url,))
        t.start()
    elif mode == 'instagram':
        urls = data.get('urls')
        t = threading.Thread(target=run_ig_manual, args=(urls,))
        t.start()

    return jsonify({'status': 'started'})

@app.route('/status')
def status():
    return jsonify(status_data)

if __name__ == '__main__':
    app.run(debug=True, port=5001, host='0.0.0.0')
