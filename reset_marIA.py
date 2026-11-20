import os
import sqlite3

# Rutas de tu proyecto
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "database", "marIA.db")
UPLOAD_FOLDER = os.path.join(BASE_DIR, "database", "temp_uploads")

def reset_database_and_cache():
    print("🧹 Iniciando limpieza total de marIA...")

    # 1. Limpiar la Base de Datos SQLite (Borrar canciones y huellas)
    if os.path.exists(DB_PATH):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Borramos los datos de las tablas relacionales
        cursor.execute("DELETE FROM fingerprints;")
        cursor.execute("DELETE FROM songs;")
        conn.commit()
        conn.close()
        print("✅ Base de datos limpiada: ¡Todas las canciones y huellas fueron eliminadas!")
    else:
        print("⚠️ No se encontró la base de datos.")

    # 2. Limpiar la carpeta de archivos temporales (Caché de subidas y micros)
    if os.path.exists(UPLOAD_FOLDER):
        count = 0
        for filename in os.listdir(UPLOAD_FOLDER):
            file_path = os.path.join(UPLOAD_FOLDER, filename)
            if os.path.isfile(file_path):
                os.remove(file_path)
                count += 1
        print(f"✅ Caché de archivos temporales limpiada: {count} archivos eliminados de temp_uploads.")
    else:
        print("⚠️ La carpeta temp_uploads no existe o ya está vacía.")

    print("\n✨ ¡Listo, Pam! marIA ha quedado totalmente limpia y lista para re-aprender desde cero.")

if __name__ == "__main__":
    reset_database_and_cache()