import os
import sqlite3

# Ruta a tu base de datos
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "database", "marIA.db")

def check_database():
    if not os.path.exists(DB_PATH):
        print(f"❌ No se encontró la base de datos en: {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Contar el total de canciones
    cursor.execute("SELECT COUNT(*) FROM songs;")
    total_songs = cursor.fetchone()[0]

    print(f"\n📊 --- ESTADÍSTICAS DE LA BASE DE DATOS ---")
    print(f"🎵 Total de canciones registradas: {total_songs}\n")

    # Listar todas las canciones guardadas
    cursor.execute("SELECT id, title, artist, genre FROM songs;")
    songs = cursor.fetchall()

    print("📜 --- LISTADO DE CANCIONES EN MARIADB ---")
    for song in songs:
        song_id, title, artist, genre = song
        print(f"[{song_id}] {artist} - {title} ({genre})")

    conn.close()

if __name__ == "__main__":
    check_database()