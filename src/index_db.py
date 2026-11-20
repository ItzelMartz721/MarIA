"""
Proyecto: MarIA - Sistema híbrido de reconocimiento acústico y análisis espectral
Autor: Pamela Itzel Hernández Martínez
Sistemas de Comunicaciones - UNAM
Descripción: Escanea pistas de audio, extrae huellas digitales de constelaciones espectrales,
             y pobla la base de datos SQLite.
"""

import os
import sqlite3
import numpy as np
import joblib

# Importa la clase extractora de características unificada
from features import MarIAFeatureExtractor

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "database", "marIA.db")
SONGS_FOLDER = os.path.join(BASE_DIR, "database", "songs") 
LYRICS_FOLDER = os.path.join(BASE_DIR, "database", "lyrics")

def init_db():
    """Inicializa el esquema de la base de datos SQLite para canciones, géneros, letras y huellas acústicas."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    os.makedirs(LYRICS_FOLDER, exist_ok=True)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS songs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            artist TEXT,
            genre TEXT,
            lyrics TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS fingerprints (
            song_id INTEGER,
            time_val REAL,
            freq_val REAL,
            FOREIGN KEY (song_id) REFERENCES songs (id)
        )
    ''')
    conn.commit()
    conn.close()

def build_acoustic_database():
    print("\n\n === Iniciando proceso de indexación acústica de MarIA... ===\n\n")
    
    init_db()
    extractor = MarIAFeatureExtractor()

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    if not os.path.exists(SONGS_FOLDER):
        print(f"⚠️ El directorio '{SONGS_FOLDER}' no existe. Verifica la ruta.")
        conn.close()
        return

    # Escanear archivos de audio en SONGS_FOLDER
    audio_files = []
    for root, dirs, files in os.walk(SONGS_FOLDER):
        for file in files:
            if file.lower().endswith(('.mp3', '.wav')):
                audio_files.append((root, file))
    
    if not audio_files:
        print(f"⚠️ No se encontraron archivos de audio en '{SONGS_FOLDER}'.")
        conn.close()
        return

    print(f"🔍 Se encontraron {len(audio_files)} pista(s). Extrayendo constelaciones espectrales...")

    for root, file in audio_files:
        audio_path = os.path.join(root, file)
        filename_raw = os.path.splitext(file)[0]
        
        if " - " in filename_raw:
            artist, title = filename_raw.split(" - ", 1)
            artist = artist.replace("_", " ").strip()
            title = title.replace("_", " ").strip()
        else:
            artist = "Unknown Artist"
            title = filename_raw.replace("_", " ").strip()
        
        # Evitar duplicados en SQLite
        cursor.execute("SELECT id FROM songs WHERE title = ? AND artist = ?", (title, artist))
        if cursor.fetchone():
            print(f"⏭️ '{artist} - {title}' ya está registrada en la base de datos. Omitiendo...")
            continue

        print(f"🎵 Extrayendo huella acústica (STFT) para: {artist} - {title}...")
        
        # Extraer únicamente los picos de la constelación espectral
        fingerprint = extractor.extract_fingerprint(audio_path, is_mic_sample=False)
        
        if fingerprint:
            # Si está dentro de una subcarpeta de género, tomar su nombre; si no, "N/A"
            parent_folder = os.path.basename(root)
            detected_genre = parent_folder if os.path.abspath(root) != os.path.abspath(SONGS_FOLDER) else "N/A"
            
            lyrics_filename = f"{filename_raw}.txt"
            lyrics_path = os.path.join(LYRICS_FOLDER, lyrics_filename)
            
            if os.path.exists(lyrics_path):
                try:
                    with open(lyrics_path, "r", encoding="utf-8") as f:
                        song_lyrics = f.read().strip()
                    print(f"   📝 Letra cargada desde: {lyrics_filename}")
                except Exception as e:
                    print(f"   ⚠️ Error al leer letra {lyrics_filename}: {e}")
                    song_lyrics = "NL"
            else:
                song_lyrics = "NL"
            
            cursor.execute('''
                INSERT INTO songs (title, artist, genre, lyrics)
                VALUES (?, ?, ?, ?)
            ''', (title, artist, detected_genre, song_lyrics))
            
            song_id = cursor.lastrowid
            
            fingerprint_data = [(song_id, float(t), float(f)) for t, f in fingerprint]
            cursor.executemany('''
                INSERT INTO fingerprints (song_id, time_val, freq_val)
                VALUES (?, ?, ?)
            ''', fingerprint_data)
            
            conn.commit()
            print(f"\n ** Indexada correctamente ({len(fingerprint)} picos espectrales | Género: {detected_genre}).")

    conn.close()
    print("\n\n=== Indexación acústica completada exitosamente.===")


if __name__ == "__main__":
    build_acoustic_database()
