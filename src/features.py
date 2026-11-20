"""
Proyecto: MarIA - Sistema híbrido de reconocimiento acústico y análisis espectral
Autor: Pamela Itzel Hernández Martínez
Sistemas de Comunicaciones - UNAM
Descripción: Módulo de extracción de características espectrales y filtrado de ruido para muestras
"""

import librosa
import numpy as np
from scipy.ndimage import maximum_filter
from scipy.signal import butter, lfilter

class MarIAFeatureExtractor:
    def __init__(self, sample_rate=11025):
        self.sr = sample_rate

    def apply_bandpass_filter(self, y, lowcut=80.0, highcut=5000.0, order=4):
        """
        Aplica un filtro de paso de banda Butterworth para eliminar el ruido de baja frecuencia (retumbar) 
        y el siseo de alta frecuencia provenientes del micrófono al procesar grabaciones en directo.
        """
        nyquist = 0.5 * self.sr
        
        #Las frecuencias de corte se normalizan con respecto a la frecuencia de Nyquist y se limitan a 0.99 para evitar errores
        low = min(lowcut / nyquist, 0.99)
        high = min(highcut / nyquist, 0.99)
        if low >= high:
            return y
        b, a = butter(order, [low, high], btype='band')
        return lfilter(b, a, y)

    def load_and_preprocess_audio(self, audio_path, is_mic_sample=False):
        """
        Función base para cargar audio, estandarizar la tasa de muestreo, normalizar la amplitud,
        aplicar el filtro de pre-emphasis y filtrar opcionalmente el ruido de fondo del micrófono.
        """
        try:
           # Cargar archivo de audio (fuerza el modo mono y la frecuencia de muestreo objetivo)
            y, sr = librosa.load(audio_path, sr=self.sr, mono=True)

            # 1. Normalización de volumen RMS (Garantiza que las grabaciones realizadas con un micrófono a bajo nivel alcancen los niveles de estudio)
            rms = np.sqrt(np.mean(y**2))
            if rms > 1e-6:
                target_db = -20.0
                current_db = 20 * np.log10(rms)
                gain = 10 ** ((target_db - current_db) / 20)
                y = np.clip(y * gain, -1.0, 1.0)
            
            # Normalización de amplitud
            if np.max(np.abs(y)) > 0:
                y = y / np.max(np.abs(y))
                
            # Filtro de pre-emphasis (atenua el ruido de baja frecuencia y mejora los armónicos)
            pre_emphasis = 0.97
            y = np.append(y[0], y[1:] - pre_emphasis * y[:-1])
            
            # Si se trata de una muestra de micrófono en tiempo real, aplica un filtro de paso de banda para eliminar la interferencia de la sala o del micrófono.
            if is_mic_sample:
                y = self.apply_bandpass_filter(y)
            
            return y, sr
        except Exception as e:
            print(f"Error al cargar audio {audio_path}: {e}")
            return None, None

    def extract_fingerprint(self, audio_path, is_mic_sample=False):
        """
        Extrae los picos espectrales locales (constelación de huellas digitales) para la identificación de pistas.
        """
        y, sr = self.load_and_preprocess_audio(audio_path, is_mic_sample=is_mic_sample)
        if y is None:
            return []

        try:
            stft = librosa.stft(y, n_fft=2048, hop_length=512)
            spectrogram = np.abs(stft)**2
            log_spectrogram = librosa.amplitude_to_db(spectrogram, ref=np.max)
            
            neighborhood = (10, 10)
            local_max = maximum_filter(log_spectrogram, size=neighborhood)
            
            threshold = -40 
            peaks_mask = (log_spectrogram == local_max) & (log_spectrogram > threshold)
            
            frequencies, times = np.where(peaks_mask)
            
            return list(zip([int(t) for t in times], [int(f) for f in frequencies]))

        except Exception as e:
            print(f"Error al extraer las huellas digitales para {audio_path}: {e}")
            return []
            
if __name__ == "__main__":
    extractor = MarIAFeatureExtractor()
    print("\n\n === El módulo extractor de características de MarIA, con filtrado de micrófono en tiempo real, está listo. ===\n\n")