"""
Proyecto: MarIA - Módulo de Emparejamiento de Constelaciones Acústicas
Autora: Pamela Itzel Hernández Martínez
Sistemas de Comunicaciones - UNAM
Descripción: Compara las huellas acústicas de un audio de consulta contra la base de datos SQLite
             utilizando ventanas estrechas de frecuencia (±1 bin FFT) y cuantización temporal (0.05s).
"""

import os
import math
import sqlite3
from .features import MarIAFeatureExtractor

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "database", "marIA.db")

# Umbrales mínimos para validar una coincidencia local y evitar falsos positivos por ruido
MIN_ALIGNED_PEAKS = 14
MIN_MATCH_RATIO = 0.08  # Al menos el 8% de los picos deben alinearse en el mismo desfase temporal (delta_t)


def match_audio(query_audio_path, is_mic_sample=False):
    """
    Compara el audio de consulta contra la base de datos de constelaciones en SQLite
    y devuelve un ranking ordenado con puntajes de alineación y porcentajes de confianza.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    extractor = MarIAFeatureExtractor()
    print(f"🔍 Extrayendo huella de constelación espectral desde: {query_audio_path}...")

    query_fingerprint = extractor.extract_fingerprint(query_audio_path, is_mic_sample=is_mic_sample)

    if not query_fingerprint:
        print("⚠️ Advertencia: No se pudieron extraer picos espectrales del audio de consulta.")
        conn.close()
        return []

    matches_count = {}
    total_query_peaks = len(query_fingerprint)
    print(f"⚙️ Comparando {total_query_peaks} picos de constelación contra la base de datos...")

    for q_time, q_freq in query_fingerprint:
        # Tolerancia estricta de ±1 bin FFT para evitar que canciones muy densas dominen por fuerza bruta
        cursor.execute('''
            SELECT song_id, time_val FROM fingerprints
            WHERE freq_val BETWEEN ? AND ?
        ''', (q_freq - 1, q_freq + 1))

        results = cursor.fetchall()

        for song_id, db_time in results:
            # Cuantización fina de 0.05s (50 ms) para absorber jitter del canal y rechazar ruido aleatorio
            delta_t = round((db_time - q_time) * 20.0) / 20.0

            if song_id not in matches_count:
                matches_count[song_id] = {}

            matches_count[song_id][delta_t] = matches_count[song_id].get(delta_t, 0) + 1

    if not matches_count:
        print("❌ No se encontraron coincidencias en la base de datos acústica.")
        conn.close()
        return []

    # Obtener el mejor puntaje de desfase temporal (delta_t) por cada canción candidata
    song_best_scores = {
        song_id: max(offsets.values())
        for song_id, offsets in matches_count.items()
    }

    # Ordenar candidatos de mayor a menor según su puntaje de picos alineados (x[1])
    sorted_matches = sorted(song_best_scores.items(), key=lambda x: x[1], reverse=True)
    ranked_results = []

    print("\n📊 --- RANKING DE COINCIDENCIAS (TOP CANDIDATOS) ---")
    for idx, (song_id, score) in enumerate(sorted_matches[:5], 1):
        match_ratio = score / max(total_query_peaks, 1)

        # Curva calibrada de confianza basada en la alineación real de picos
        curve = 1.0 - math.exp(-score / 25.0)
        ratio_score = min(match_ratio / 0.30, 1.0)
        percentage = min(99.5, round((curve * 60.0) + (ratio_score * 39.5), 2))

        cursor.execute("SELECT title, artist, genre FROM songs WHERE id = ?", (song_id,))
        song = cursor.fetchone()

        if song:
            title, artist, genre = song
            is_valid = (score >= MIN_ALIGNED_PEAKS) and (match_ratio >= MIN_MATCH_RATIO)
            status_tag = "✅ VÁLIDA" if is_valid else "⚠️ RUIDO / EXTERNA"
            print(f"{idx}. 🎵 {title} - {artist} | Picos: {score}/{total_query_peaks} ({match_ratio*100:.1f}%) | Confianza: {percentage:.2f}% [{status_tag}]")

            if is_valid:
                ranked_results.append({
                    "title": title,
                    "artist": artist,
                    "genre": genre,
                    "score": score,
                    "percentage": percentage,
                    "source": "Base de Datos Local"
                })

    conn.close()
    return ranked_results


if __name__ == "__main__":
    test_audio = "database/test/Prueba3.mp3"
    match_audio(test_audio, is_mic_sample=True)
