"""
Proyecto: MarIA - Módulo de Emparejamiento de Constelaciones Acústicas
Autora: Pamela Itzel Hernández Martínez
Sistemas de Comunicaciones - UNAM
Descripción: Módulo de emparejamiento de constelaciones acústicas para la identificación de señales de audio.
"""

import io
import base64
import shutil
import matplotlib
matplotlib.use('Agg')  # Evita abrir ventanas gráficas en Debian/servidor
import matplotlib.pyplot as plt
import librosa
import librosa.display
import csv
import os
import json
import sqlite3
from datetime import datetime
import soundfile as sf
import numpy as np
import requests
from scipy.signal import butter, sosfilt
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from scipy.signal import butter, sosfilt

from src.features import MarIAFeatureExtractor
from src.match_song import match_audio

app = Flask(__name__)
CORS(app)

# Directorios base y rutas
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "database", "marIA.db")
UPLOAD_FOLDER = os.path.join(BASE_DIR, "database", "temp_uploads")
STATS_FILE = os.path.join(BASE_DIR, "database", "stats.json")
MIC_ARCHIVE_FOLDER = os.path.join(BASE_DIR, "database", "mic_recordings")
os.makedirs(MIC_ARCHIVE_FOLDER, exist_ok=True)
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

AUDD_API_URL = "https://api.audd.io/"
AUDD_API_TOKEN = ""

ALLOWED_EXTENSIONS = {'mp3', 'wav', 'webm', 'ogg', 'm4a'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Inicializar extractor de características DSP ligero (FFT, paso de banda, RMS/pico)
extractor = MarIAFeatureExtractor()
print("\n\n=== MarIA DSP Feature Extractor loaded successfully! ===")

@app.route('/')
def index():
    """Renderiza la interfaz web principal."""
    return render_template('index.html')

def generate_spectrogram_base64(audio_path, title_label="Signal Spectrogram"):
    """Genera un espectrograma STFT de alta contraste codificado como PNG Base64 para visualización en frontend."""
    if not audio_path or not os.path.exists(audio_path):
        return None
    try:
        y, sr = librosa.load(audio_path, sr=22050, mono=True, duration=15.0)
        if len(y) == 0:
            return None

        # Filtro de preénfasis (0,97) para resaltar los formantes/armónicos de alta frecuencia
        y_pre = librosa.effects.preemphasis(y, coef=0.97)
        S = np.abs(librosa.stft(y_pre, n_fft=2048, hop_length=512))
        S_db = librosa.amplitude_to_db(S, ref=np.max)

        fig, ax = plt.subplots(figsize=(8.5, 4.6), dpi=180)
        fig.patch.set_facecolor('#0f172a')
        ax.set_facecolor('#0f172a')

        img = librosa.display.specshow(
            S_db, sr=sr, hop_length=512, x_axis='time', y_axis='hz',
            ax=ax, cmap='magma', fmax=8000
        )
        ax.set_title(title_label, color='#f8fafc', fontsize=9, fontweight='bold', pad=6)
        ax.set_xlabel("Time (s)", color='#94a3b8', fontsize=7.5)
        ax.set_ylabel("Freq (Hz)", color='#94a3b8', fontsize=7.5)
        ax.tick_params(colors='#94a3b8', labelsize=7)
        for spine in ax.spines.values():
            spine.set_edgecolor('#334155')

        cbar = fig.colorbar(img, ax=ax, format='%+2.0f dB')
        cbar.ax.yaxis.set_tick_params(color='#94a3b8', labelsize=6.5)
        plt.setp(plt.getp(cbar.ax.axes, 'yticklabels'), color='#94a3b8')

        plt.tight_layout()
        buf = io.BytesIO()
        plt.savefig(buf, format='png', facecolor=fig.get_facecolor())
        plt.close(fig)
        buf.seek(0)
        return f"data:image/png;base64,{base64.b64encode(buf.read()).decode('utf-8')}"
    except Exception as e:
        print(f"⚠️ Error generando espectrograma: {e}")
        return None

def compute_comms_radiography(audio_path, is_mic_sample=False):
    """
    Extrae las métricas completas de los Sistemas de Comunicaciones (RMS, Pico, Factor de Cresta,
    SNR Estimado, Ancho de Banda, Frecuencia de Nyquist, Orden de Butterworth) desde la señal capturada.
    """
    try:
        y_raw, sr = librosa.load(audio_path, sr=22050, mono=True)
        if len(y_raw) == 0:
            return None

        duration_sec = round(len(y_raw) / sr, 2)
        peak_amp = float(np.max(np.abs(y_raw)))
        rms_raw = float(np.sqrt(np.mean(y_raw**2)))

        rms_db = round(20 * np.log10(rms_raw), 2) if rms_raw > 1e-8 else -100.0
        peak_db = round(20 * np.log10(peak_amp), 2) if peak_amp > 1e-8 else -100.0
        crest_factor_db = round(peak_db - rms_db, 2) if rms_raw > 1e-8 else 0.0

        # Estimar SNR comparando frames activos (70% de energía) vs suelo de ruido (20% de energía)
        frame_rms = librosa.feature.rms(y=y_raw, frame_length=2048, hop_length=512)[0]
        if len(frame_rms) > 4:
            noise_floor = float(np.percentile(frame_rms, 20))
            signal_level = float(np.percentile(frame_rms, 80))
            snr_db = round(20 * np.log10(max(signal_level, 1e-7) / max(noise_floor, 1e-7)), 2)
        else:
            snr_db = 0.0

        # Frecuencia de centroide espectral y tasa de cruce por cero (ZCR)
        centroid_hz = round(float(np.mean(librosa.feature.spectral_centroid(y=y_raw, sr=sr))), 1)
        zcr_val = round(float(np.mean(librosa.feature.zero_crossing_rate(y=y_raw))), 4)

        # Clasificación del canal acústico según RMS y SNR
        if rms_db < -42 or snr_db < 4.0:
            channel_status = "Weak / High Noise Floor"
        elif snr_db < 10.0:
            channel_status = "Moderate Acoustic Noise"
        else:
            channel_status = "Clear Acoustic Channel"
        
        # Matriz 3D ligera (Frecuencia x Tiempo x Potencia dB) para visualización 3D interactiva
        S_small = np.abs(librosa.stft(y_raw, n_fft=512, hop_length=2048))
        S_small_db = librosa.amplitude_to_db(S_small, ref=np.max)
        
        # Tomar hasta 28 bandas de frecuencia (0 a ~6 kHz) y hasta 35 frames de tiempo
        z_surface = np.round(S_small_db[:28, :35], 1).tolist()

        return {
            "source_type": "Live Microphone (Acoustic Channel)" if is_mic_sample else "Direct Digital File",
            "sample_rate_hz": sr,
            "nyquist_freq_hz": sr // 2,
            "duration_sec": duration_sec,
            "rms_db": rms_db,
            "peak_db": peak_db,
            "crest_factor_db": crest_factor_db,
            "snr_db": snr_db,
            "centroid_hz": centroid_hz,
            "zcr": zcr_val,
            "filter_spec": "Butterworth 4th-Order Bandpass (100 Hz – 7.5 kHz) + Pre-Emphasis (α=0.97)",
            "channel_status": channel_status,
            "surface_3d": z_surface
        }
    except Exception as e:
        print(f"⚠️ Radiography computation error: {e}")
        return None

def find_local_song_filepath(title, artist):
    """Busca archivos de canciones locales en los directorios del proyecto; devuelve None para usar la vista previa externa del espectrograma."""
    if not title or title == "Unknown Track":
        return None
    clean_t = title.lower().strip()
    clean_a = artist.lower().strip() if artist and artist not in ("Unknown Artist", "Unidentified Artist") else ""

    for folder in (MIC_ARCHIVE_FOLDER, UPLOAD_FOLDER):
        if not os.path.exists(folder):
            continue
        for fname in os.listdir(folder):
            if not fname.lower().endswith(('.mp3', '.wav', '.ogg', '.m4a')):
                continue
            no_ext = os.path.splitext(fname)[0].lower().replace("_", " ")
            if (clean_a and f"{clean_a} - {clean_t}" == no_ext) or (clean_t in no_ext):
                return os.path.join(folder, fname)
    return None

@app.route('/api/analyze', methods=['POST'])
def analyze_audio():
    """
    Endpoint principal para recibir audio, procesarlo y devolver resultados de coincidencia.
    """
    user_agent = request.headers.get('User-Agent', '').lower()
    is_mobile_device = any(keyword in user_agent for keyword in ['android', 'iphone', 'ipad', 'ipod', 'mobile'])

    if is_mobile_device:
        print("\n\n === Audio recibido desde un CELULAR.")
    else:
        print("\n\n === Audio recibido desde una LAPTOP / ESCRITORIO.")

    if 'audio_data' not in request.files and 'audio_file' not in request.files and 'audio' not in request.files:
        return jsonify({"success": False, "error": "No audio file provided."}), 400

    file = request.files.get('audio_file') or request.files.get('audio_data') or request.files.get('audio')
    if file.filename == '':
        return jsonify({"success": False, "error": "Empty filename."}), 400

    file_path = os.path.join(UPLOAD_FOLDER, file.filename)
    file.save(file_path)

    is_mic = request.form.get('is_mic', 'false').lower() == 'true'

    try:
        # 1. Guardar copia permanente del audio grabado en tiempo real directamente como .mp3
        saved_mic_filename = None
        if is_mic and os.path.exists(file_path):
            timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            saved_mic_filename = f"mic_capture_{timestamp_str}.mp3"
            archived_path = os.path.join(MIC_ARCHIVE_FOLDER, saved_mic_filename)
            try:
                import subprocess
                subprocess.run(
                    ["ffmpeg", "-y", "-i", file_path, "-b:a", "192k", archived_path],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=True
                )
                print(f"\n\n === Guardado en database/mic_recordings/{saved_mic_filename} ===")
            except Exception as e_mp3:
                print(f"⚠️ No se pudo convertir a MP3 con ffmpeg ({e_mp3}), guardando respaldo...")
                shutil.copy2(file_path, archived_path)

        # 2. Calcular radiografía DSP (SNR, RMS, Crest Factor, Nyquist) y espectrograma de prueba
        comms_radiography = compute_comms_radiography(file_path, is_mic_sample=is_mic)
        query_spectrogram = generate_spectrogram_base64(file_path, title_label="Query Signal (Captured Audio)")

        # 3. Consultar PRIMERO API Externa (con audio acondicionado por Butterworth + AGC)
        print("\n\n\n=== Consultando API Externa como prioridad... ===\n")
        external_matches = recognize_with_external_api(file_path)

        # 4. Consultar BD Local (como respaldo o complemento)
        local_matches = match_audio(file_path, is_mic_sample=is_mic)

        if external_matches:
            ranked_matches = external_matches 
        else:
            print("\n\n === Sin resultado en API externa. Usando ranking de constelaciones locales... ===")
            ranked_matches = match_audio(file_path, is_mic_sample=is_mic)

        # 5. Preparar Top Match, preview de audio y espectrograma de referencia
        match_spectrogram = None
        if ranked_matches:
            top_match = ranked_matches[0]
            if not top_match.get("preview_url"):
                top_match["preview_url"] = get_audio_preview(top_match["title"], top_match["artist"])

            ref_audio_path = find_local_song_filepath(top_match.get("title", ""), top_match.get("artist", ""))
            temp_ref_dl = None

            if not ref_audio_path and top_match.get("preview_url"):
                try:
                    r_prev = requests.get(top_match["preview_url"], timeout=6)
                    if r_prev.status_code == 200:
                        temp_ref_dl = os.path.join(UPLOAD_FOLDER, f"spec_ref_{abs(hash(top_match['title']))}.mp3")
                        with open(temp_ref_dl, "wb") as f_ref:
                            f_ref.write(r_prev.content)
                        ref_audio_path = temp_ref_dl
                except Exception as e_dl:
                    print(f"⚠️ No se pudo descargar preview para espectrograma: {e_dl}")

            if ref_audio_path:
                match_spectrogram = generate_spectrogram_base64(
                    ref_audio_path,
                    title_label=f"Matched Reference: {top_match.get('title', 'Track')}"
                )

            if temp_ref_dl and os.path.exists(temp_ref_dl):
                os.remove(temp_ref_dl)
        else:
            top_match = {
                "title": "Unknown Track",
                "artist": "Unidentified Artist",
                "genre": "N/A",
                "score": 0,
                "percentage": 0.0,
                "preview_url": None
            }

        return jsonify({
            "success": True,
            "top_match": top_match,
            "ranking": ranked_matches if ranked_matches else [],
            "comms_radiography": comms_radiography,
            "query_spectrogram": query_spectrogram,
            "match_spectrogram": match_spectrogram,
            "archived_recording": saved_mic_filename
        })

    except Exception as e:
        print(f"Error en el análisis del backend: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

    finally:
        if os.path.exists(file_path):
            os.remove(file_path)
            print(f"\n\n === Archivo temporal {file.filename} eliminado. ===")

# --- REAL-WORLD ACCURACY STATS ---
def load_stats():
    if not os.path.exists(STATS_FILE):
        return {"attempts": 0, "successes": 0}
    try:
        with open(STATS_FILE, 'r', encoding='utf-8') as f:
            content = f.read().strip()
            if not content:
                return {"attempts": 0, "successes": 0}
            return json.loads(content)
    except (json.JSONDecodeError, ValueError):
        return {"attempts": 0, "successes": 0}

def save_stats(stats):
    with open(STATS_FILE, 'w', encoding='utf-8') as f:
        json.dump(stats, f, indent=4)

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Returns the global accuracy statistics."""
    stats = load_stats()
    accuracy = (stats["successes"] / stats["attempts"] * 100) if stats["attempts"] > 0 else 100.0
    return jsonify({
        "attempts": stats["attempts"],
        "successes": stats["successes"],
        "accuracy": round(accuracy, 2)
    })

@app.route('/api/feedback', methods=['POST'])
def post_feedback():
    """Registra la opinión del usuario (Sí/No) y actualiza la precisión global.."""
    data = request.get_json()
    is_correct = data.get('success', False)
    
    stats = load_stats()
    stats["attempts"] += 1
    if is_correct:
        stats["successes"] += 1
    save_stats(stats)
    
    accuracy = (stats["successes"] / stats["attempts"]) * 100
    return jsonify({
        "attempts": stats["attempts"],
        "successes": stats["successes"],
        "accuracy": round(accuracy, 2)
    })

def bandpass_filter_comms(y, sr, lowcut=100.0, highcut=7500.0, order=4):
    """Filtro paso banda Butterworth de cuarto orden para eliminar el ruido de fondo (retumbar) y el siseo en micrófonos móviles.."""
    nyq = 0.5 * sr
    low = max(lowcut / nyq, 0.001)
    high = min(highcut / nyq, 0.99)
    sos = butter(order, [low, high], btype='band', output='sos')
    return sosfilt(sos, y)

def compensate_mic_bass(y, sr, cutoff=180.0, boost_gain=2.2):
    """Compensa las frecuencias bajas perdidas por los micrófonos de smartphones para que el ritmo y el bajo coincidan con el audio del estudio."""
    nyq = 0.5 * sr
    sos_low = butter(2, cutoff / nyq, btype='low', output='sos')
    y_bass = sosfilt(sos_low, y)
    return y + (y_bass * boost_gain)

def get_audio_preview(title, artist):
    """Obtiene un enlace de vista previa de 30 segundos desde la API pública de Deezer."""
    if not title or title == "Unknown Track":
        return None
    try:
        clean_artist = artist if artist and artist != "Unknown Artist" else ""
        query = f"{title} {clean_artist}".strip()
        url = "https://api.deezer.com"
        params = {"q": query, "limit": 1}
        headers = {"User-Agent": "Mozilla/5.0"}

        res = requests.get(url, params=params, headers=headers, timeout=6)
        if res.status_code == 200 and res.text.strip().startswith("{"):
            data = res.json().get("data", [])
            if data and len(data) > 0:
                first_item = data[0]
                if first_item.get("preview"):
                    return first_item["preview"]
    except Exception as e:
        print(f"⚠️ Preview fetch error: {e}")
    return None


def auto_index_from_external(title, artist, preview_url):
    """
    Descarga la vista previa de 30 segundos desde una API externa, extrae los picos de las constelaciones y 
    los almacena automáticamente en SQLite para futuras comparaciones locales..
    """
    if not preview_url:
        return "N/A", 0

    temp_preview_path = os.path.join(UPLOAD_FOLDER, f"auto_{abs(hash(title + artist))}.mp3")
    try:
        res = requests.get(preview_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=8)
        if res.status_code != 200:
            return "N/A", 0

        with open(temp_preview_path, "wb") as f:
            f.write(res.content)

        # Extraer únicamente picos de constelación (sin red neuronal)
        fingerprint = extractor.extract_fingerprint(temp_preview_path, is_mic_sample=False)

        if not fingerprint:
            return "N/A", 0

        # Guardar en SQLite (evitando duplicados)
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM songs WHERE title = ? AND artist = ?", (title, artist))
        existing = cursor.fetchone()

        if not existing:
            cursor.execute(
                "INSERT INTO songs (title, artist, genre, lyrics) VALUES (?, ?, ?, ?)",
                (title, artist, "N/A", "NL")
            )
            song_id = cursor.lastrowid
            fingerprint_data = [(song_id, float(t), float(f)) for t, f in fingerprint]
            cursor.executemany(
                "INSERT INTO fingerprints (song_id, time_val, freq_val) VALUES (?, ?, ?)",
                fingerprint_data
            )
            conn.commit()
            print(f"🌱 [Auto-Learning]: '{artist} - {title}' indexed with {len(fingerprint)} peaks!")

        conn.close()
        return "N/A", len(fingerprint)

    except Exception as e:
        print(f"⚠️ Auto-index error: {e}")
        return "N/A", 0
    finally:
        if os.path.exists(temp_preview_path):
            os.remove(temp_preview_path)

def recognize_with_external_api(file_path, local_peaks_count=0):
    """
    Acondiciona el audio ruidoso del micrófono móvil mediante el filtrado paso banda 
    Butterworth + control automático de ganancia RMS
    Antes de consultar la API AudD, registra el diagnóstico completo del DSP de comunicaciones.
    """
    clean_audd_path = f"{os.path.splitext(file_path)[0]}_clean.wav"

    try:
        y_raw, sr_clean = librosa.load(file_path, sr=22050, mono=True)
        if len(y_raw) == 0:
            return []

        # 1. Recortar silencios iniciales y finales (top_db=40) para mejorar la coincidencia de constelaciones
        y_trimmed, _ = librosa.effects.trim(y_raw, top_db=40)
        if len(y_trimmed) > sr_clean * 3:
            y_raw = y_trimmed

        # 2. Calcular RMS y duración para descartar señales por debajo del umbral de ruido
        raw_rms = float(np.sqrt(np.mean(y_raw**2)))
        raw_rms_db = round(20 * np.log10(raw_rms), 2) if raw_rms > 1e-8 else -100.0
        duration_sec = round(len(y_raw) / sr_clean, 2)

        if raw_rms < 0.0008 or duration_sec < 1.2:
            print(f"⚠️ Signal below noise floor: RMS={raw_rms_db} dBFS, Duration={duration_sec}s")
            return []

        # 3. Filtrado paso banda Butterworth de 4to orden (100 Hz - 7.5 kHz) para eliminar retumbar y siseo
        y_filtered = bandpass_filter_comms(y_raw, sr_clean, lowcut=100.0, highcut=7500.0, order=4)

        # 3.1 Compensar graves perdidos por el micrófono para equilibrar ritmo vs voz
        y_filtered = compensate_mic_bass(y_filtered, sr_clean, cutoff=180.0, boost_gain=2.2)

        # 4. Control automático de ganancia (AGC): normalizar RMS a -14 dBFS (0.20) para que Android coincida con el nivel de iPhone
        filtered_rms = float(np.sqrt(np.mean(y_filtered**2)))
        target_rms = 0.20
        gain = target_rms / max(filtered_rms, 1e-6)
        y_agc = np.tanh(y_filtered * gain)  

        final_rms = float(np.sqrt(np.mean(y_agc**2)))
        final_rms_db = round(20 * np.log10(final_rms), 2)
        agc_gain_db = round(final_rms_db - raw_rms_db, 2)

        # Recortar a 12 segundos para cumplir con el límite de AudD API (12s máximo)
        if len(y_agc) > sr_clean * 12:
            start = (len(y_agc) - sr_clean * 12) // 2
            y_agc = y_agc[start:start + sr_clean * 12]

        print(
            f"\n\n📡 [Comms DSP -> AudD]: Raw RMS={raw_rms_db} dBFS -> Conditioned RMS={final_rms_db} dBFS "
            f"(AGC Gain=+{agc_gain_db} dB) | Duración={round(len(y_agc)/sr_clean, 2)}s"
        )

        sf.write(clean_audd_path, y_agc, sr_clean, subtype='PCM_16')

        with open(clean_audd_path, 'rb') as f:
            data = {'api_token': AUDD_API_TOKEN, 'return': 'deezer,apple_music'}
            files = {'file': f}
            res = requests.post("https://api.audd.io/", data=data, files=files, timeout=12)

        if res.status_code != 200 or not res.text.strip().startswith("{"):
            print(f"⚠️ AudD HTTP {res.status_code}: {res.text[:200]}")
            return []

        resp_json = res.json()
        print("\n\n📡 --- JSON RECIBIDO DE AUDD API ---")
        print(json.dumps(resp_json, indent=4, ensure_ascii=False))
        print("------------------------------------\n")

        if resp_json.get('result'):
            result = resp_json['result']
            title = result.get('title', 'Unknown Track')
            artist = result.get('artist', 'Unknown Artist')

            preview = None
            if result.get('deezer') and result['deezer'].get('preview'):
                preview = result['deezer']['preview']
            elif result.get('apple_music') and result['apple_music'].get('previews'):
                previews_list = result['apple_music']['previews']
                if len(previews_list) > 0:
                    preview = previews_list[0].get('url')
            if not preview:
                preview = get_audio_preview(title, artist)

            final_genre, peaks_added = auto_index_from_external(title, artist, preview)

            return [{
                "title": title,
                "artist": artist,
                "genre": final_genre,
                "score": peaks_added if peaks_added > 0 else 100,
                "percentage": 96.50,
                "source": "External API + Auto-Indexed" if peaks_added > 0 else "External API",
                "preview_url": preview,
                "comms_metrics": {
                    "raw_rms_db": raw_rms_db,
                    "conditioned_rms_db": final_rms_db,
                    "agc_gain_db": agc_gain_db,
                    "filter": "Butterworth Bandpass 4th-order (100Hz - 7.5kHz)"
                }
            }]

    except Exception as e:
        print(f"⚠️ External API error: {e}")
    finally:
        if os.path.exists(clean_audd_path):
            os.remove(clean_audd_path)

    return []

@app.route('/api/register_song', methods=['POST'])
def register_song():
    """
    Endpoint para registrar manualmente una canción en la base de datos local.
    """
    if 'audio_file' not in request.files:
        return jsonify({"success": False, "error": "No audio file uploaded."}), 400

    file = request.files['audio_file']
    if file.filename == '' or not allowed_file(file.filename):
        return jsonify({"success": False, "error": "Invalid or unsupported audio file."}), 400

    title = request.form.get('title', '').strip()
    artist = request.form.get('artist', '').strip()
    lyrics = request.form.get('lyrics', '').strip() or "NL"

    if not title or not artist:
        raw_name = os.path.splitext(file.filename)[0]
        if " - " in raw_name:
            parsed_artist, parsed_title = raw_name.split(" - ", 1)
            artist = artist or parsed_artist.replace("_", " ").strip()
            title = title or parsed_title.replace("_", " ").strip()
        else:
            artist = artist or "Unknown Artist"
            title = title or raw_name.replace("_", " ").strip()

    file_path = os.path.join(UPLOAD_FOLDER, f"index_{file.filename}")
    file.save(file_path)

    try:
        fingerprint = extractor.extract_fingerprint(file_path, is_mic_sample=False)

        if not fingerprint:
            if os.path.exists(file_path):
                os.remove(file_path)
            return jsonify({"success": False, "error": "Could not extract acoustic constellation from audio."}), 400

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM songs WHERE title = ? AND artist = ?", (title, artist))
        existing = cursor.fetchone()

        already_existed = False
        if existing:
            already_existed = True
            song_id = existing[0]
        else:
            cursor.execute(
                "INSERT INTO songs (title, artist, genre, lyrics) VALUES (?, ?, ?, ?)",
                (title, artist, "N/A", lyrics)
            )
            song_id = cursor.lastrowid
            fingerprint_data = [(song_id, float(t), float(f)) for t, f in fingerprint]
            cursor.executemany(
                "INSERT INTO fingerprints (song_id, time_val, freq_val) VALUES (?, ?, ?)",
                fingerprint_data
            )
            conn.commit()
        conn.close()

        if os.path.exists(file_path):
            os.remove(file_path)

        return jsonify({
            "success": True,
            "already_existed": already_existed,
            "song": {
                "id": song_id,
                "title": title,
                "artist": artist,
                "genre": "N/A",
                "peaks_count": len(fingerprint)
            },
            "xai": None
        })

    except Exception as e:
        if os.path.exists(file_path):
            os.remove(file_path)
        print(f"❌ Error in register_song: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)
