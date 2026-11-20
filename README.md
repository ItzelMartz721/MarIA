# 🎵 MarIA — Sistema Híbrido de Reconocimiento Acústico y Análisis Espectral

**MarIA** es una aplicación web desarrollada en **Python (Flask)** para la asignatura de **Sistemas de Comunicaciones** (Facultad de Ingeniería, UNAM). El sistema modela el trayecto acústico entre una fuente sonora y un micrófono móvil como un canal ruidoso, aplicando técnicas de **Procesamiento Digital de Señales (DSP)** para acondicionar la señal, extraer su huella espectral y realizar reconocimiento híbrido mediante una base de datos local (**SQLite**) y APIs externas (**AudD** y **Deezer**).

---

## ✨ Características Principales

* **Acondicionamiento de Canal Acústico (DSP):**
  * **Muestreo bajo el Teorema de Nyquist:** Estandarización a $F_s = 22,050\text{ Hz}$ ($F_{\text{Nyquist}} = 11,025\text{ Hz}$).
  * **Filtrado Pasa-Banda Butterworth (4.º orden):** Eliminación de ruido ambiental de baja frecuencia y sibilancia de alta frecuencia ($45\text{ Hz} - 6.5\text{ kHz}$).
  * **Compensación de Graves y Pre-énfasis ($\alpha = 0.97$):** Equilibrio espectral para compensar la atenuación física en cápsulas de micrófonos móviles.
  * **Control Automático de Ganancia (AGC):** Normalización de potencia RMS objetivo a $-14\text{ dBFS}$ con limitador suave (`tanh`) para evitar saturación (*clipping*).
* **Radiografía del Canal en Tiempo Real:**
  * Cálculo de **Relación Señal a Ruido (SNR estimado en dB)**, **Potencia RMS (dBFS)**, **Factor de Cresta (dB)**, **Centroide Espectral (Hz)** y diagnóstico automático de calidad del canal.
* **Análisis Tiempo-Frecuencia (STFT) y Topología 3D:**
  * Generación de **espectrogramas comparativos** (Señal Capturada vs. Señal de Referencia) con visor ampliable en pantalla completa.
  * Visualización interactiva de **Topología Espectral 3D** ($\text{Tiempo} \times \text{Frecuencia} \times \text{Potencia en dB}$) mediante **Plotly.js**.
* **Arquitectura Híbrida con Auto-Aprendizaje:**
  * Identificación mediante constelaciones de picos espectrales en **SQLite** y respaldo con **AudD API** + previsualizaciones de audio vía **Deezer API**, indexando automáticamente nuevas canciones en la base de datos local.

---

## 🛠️ Tecnologías Utilizadas

* **Backend:** Python 3, Flask, Librosa, SciPy, NumPy, SoundFile, Matplotlib, SQLite3.
* **Frontend:** HTML5, Tailwind CSS, JavaScript (Web Audio API / PCM WAV Encoder), Plotly.js.
* **APIs Externas:** AudD Music Recognition API, Deezer Public Search API.

---

## 🚀 Instalación y Ejecución Local

1. **Clonar o descargar el repositorio:**
   ```bash
   git clone https://github.com
   cd MarIA-Sistemas-Comunicaciones
   ```

2. **Crear y activar un entorno virtual:**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Instalar dependencias:**
   ```bash
   pip install flask librosa scipy numpy soundfile matplotlib requests
   ```
   *(Asegúrate de tener `ffmpeg` instalado en el sistema: `sudo apt install ffmpeg`).*

4. **Configurar el token de AudD API:**
   ```bash
   export AUDD_API_TOKEN="tu_token_de_audd_aqui"
   ```

5. **Ejecutar la aplicación:**
   ```bash
   python app.py
   ```
   Abre tu navegador en `http://127.0.0.1:5000`.

---

## 👩‍💻 Autoría

* **Itzel Martínez** — Ingeniería, UNAM.
