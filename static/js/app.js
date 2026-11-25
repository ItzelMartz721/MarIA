/**
 * Proyecto: MarIA — Sistema Híbrido de Reconocimiento Acústico y Análisis Espectral
 * Archivo: static/js/app.js (Parte 1: Control de Interfaz, Modales y Visores Ampliados)
 * Autora: Pam (Itzel) Martínez — Facultad de Ingeniería, UNAM (Sistemas de Comunicaciones)
 */

// --- REFERENCIAS A ELEMENTOS DEL DOM (INTERFAZ PRINCIPAL) ---
const micBtn = document.getElementById('mic-btn');
const micBtnText = document.getElementById('mic-btn-text');
const uploadBtn = document.getElementById('upload-btn');
const audioFileInput = document.getElementById('audio-file-input');
const statusIndicator = document.getElementById('status-indicator');
const visualizerContainer = document.getElementById('visualizer-container');
const loadingContainer = document.getElementById('loading-container');
const loadingText = document.getElementById('loading-text');
const recordingProgress = document.getElementById('recording-progress');
const eqBars = document.querySelectorAll('.eq-bar');

// --- VARIABLES DE ESTADO DE GRABACIÓN Y PROCESAMIENTO ---
let isRecording = false;        // Indica si el micrófono está capturando audio actualmente
let isAnalyzing = false;        // Bloquea botones mientras el servidor procesa la señal
let recordingInterval;          // Temporizador de la barra de progreso de captura
let eqInterval;                 // Temporizador de animación del ecualizador visual

// --- VARIABLES DE WEB AUDIO API (CAPTURA PCM EN TIEMPO REAL) ---
let audioContext;               // Contexto de audio nativo del navegador
let micStream;                  // Flujo de entrada del hardware del micrófono
let scriptProcessor;            // Nodo procesador para extraer muestras crudas (Float32Array)
let recordedBuffers = [];       // Arreglo donde se acumulan los bloques de audio capturados
let recordingSampleRate = 22050;// Frecuencia de muestreo inicial (se actualiza a la nativa del dispositivo)

/**
 * Controla el estado visual de carga mientras el backend ejecuta el pipeline DSP
 * (Filtrado Butterworth, AGC, STFT y consulta híbrida).
 */
function setLoadingState(active, message = "Analizando huellas de constelación espectral...") {
  isAnalyzing = active;
  uploadBtn.disabled = active;
  micBtn.disabled = active;

  if (active) {
    uploadBtn.classList.add('opacity-50', 'cursor-not-allowed');
    micBtn.classList.add('opacity-50', 'cursor-not-allowed');
    loadingText.textContent = message;
    loadingContainer.classList.remove('hidden');
    statusIndicator.textContent = "Por favor espera mientras MarIA procesa la señal...";
  } else {
    uploadBtn.classList.remove('opacity-50', 'cursor-not-allowed');
    micBtn.classList.remove('opacity-50', 'cursor-not-allowed');
    loadingContainer.classList.add('hidden');
    statusIndicator.textContent = "Haz clic en el micrófono para grabar (10s)";
  }
}

/**
 * Despliega el modal de resultados con la canción ganadora (#1), el reproductor
 * de previsualización y el ranking de las mejores 5 coincidencias acústicas.
 */
function showResultModal(topMatch, ranking = []) {
  hasVotedCurrentSong = false;
  const feedbackBtns = document.querySelectorAll('#result-modal button[onclick*="registerFeedback"]');
  feedbackBtns.forEach(btn => {
    btn.classList.remove('opacity-50', 'cursor-not-allowed');
    btn.disabled = false;
  });
  const oldThanks = document.getElementById('feedback-thanks-msg');
  if (oldThanks) oldThanks.remove();

  // Mostrar metadatos de la coincidencia principal (#1)
  document.getElementById('res-title').innerText = topMatch.title || "Pista Desconocida";
  document.getElementById('res-artist').innerText = topMatch.artist || "Artista No Identificado";
  const resGenreEl = document.getElementById('res-genre');
  if (resGenreEl) resGenreEl.innerText = topMatch.genre || "N/A";
  document.getElementById('res-similarity').innerText = topMatch.percentage ?? 0;

  // Configurar reproductor de previsualización de 30s (Deezer / Local)
  const previewContainer = document.getElementById('preview-container');
  const audioPlayer = document.getElementById('song-preview-player');
  if (topMatch.preview_url) {
    audioPlayer.src = topMatch.preview_url;
    previewContainer.classList.remove('hidden');
  } else {
    audioPlayer.pause();
    audioPlayer.src = "";
    previewContainer.classList.add('hidden');
  }

  // Construir dinámicamente la lista de candidatos (Top 5)
  const top5Container = document.getElementById('top5-container');
  const top5List = document.getElementById('top5-list');
  top5List.innerHTML = '';

  if (ranking && ranking.length > 0) {
    ranking.forEach((song, index) => {
      const isFirst = index === 0;
      const itemDiv = document.createElement('div');
      itemDiv.className = `flex items-center justify-between p-2 rounded-xl text-xs border ${
        isFirst ? 'bg-indigo-500/15 border-indigo-500/40 text-white' : 'bg-slate-800/40 border-slate-800 text-slate-300'
      }`;

      itemDiv.innerHTML = `
        <div class="truncate pr-2 flex-1">
          <span class="font-bold text-pink-400 mr-1">#${index + 1}</span>
          <span class="font-medium">${song.title}</span>
          <span class="text-slate-400 text-[11px]"> — ${song.artist}</span>
        </div>
        <div class="flex items-center space-x-2 shrink-0">
          <span class="text-[11px] font-semibold text-emerald-400">${song.percentage}%</span>
          ${song.preview_url ? `
            <button onclick="playPreviewTrack('${song.preview_url}', '${song.title.replace(/'/g, "\\'")}', '${song.artist.replace(/'/g, "\\'")}')" 
                    class="bg-slate-700 hover:bg-indigo-600 text-white p-1.5 rounded-lg transition" title="Escuchar muestra">
              ▶
            </button>
          ` : ''}
        </div>
      `;
      top5List.appendChild(itemDiv);
    });
    top5Container.classList.remove('hidden');
  } else {
    top5Container.classList.add('hidden');
  }

  document.getElementById('result-modal').classList.remove('hidden');
}

// Almacena la matriz Z (Tiempo x Frecuencia x dB) para renderizar el visor 3D ampliado
let lastSurface3D = null;

/**
 * Abre un espectrograma STFT en visor de pantalla completa (Lightbox).
 */
function openSpectrogramLightbox(src, title) {
  if (!src) return;
  const lb = document.getElementById('spectrogram-lightbox');
  const img = document.getElementById('lightbox-spec-img');
  const lbl = document.getElementById('lightbox-spec-title');
  if (lb && img && lbl) {
    img.src = src;
    lbl.innerText = title || 'Vista de Espectrograma STFT';
    lb.classList.remove('hidden');
  }
}

/**
 * Cierra el visor de pantalla completa de espectrogramas.
 */
function closeSpectrogramLightbox() {
  const lb = document.getElementById('spectrogram-lightbox');
  if (lb) lb.classList.add('hidden');
}

/**
 * Renderiza la Topología Espectral 3D en pantalla completa usando Plotly.js (WebGL)
 * con ejes etiquetados en español y barra de escala en decibeles (dB).
 */
function open3DLightbox() {
  if (!lastSurface3D || typeof Plotly === 'undefined') return;
  const modal = document.getElementById('modal-3d-lightbox');
  const target = document.getElementById('comms-3d-plot-full');
  if (!modal || !target) return;

  modal.classList.remove('hidden');

  setTimeout(() => {
    const traceFull = [{
      z: lastSurface3D,
      type: 'surface',
      colorscale: 'Magma',
      colorbar: { title: 'dB', tickfont: { color: '#94a3b8' }, titlefont: { color: '#f8fafc' } },
      contours: {
        z: { show: true, usecolormap: true, highlightcolor: "#f472b6", project: { z: true } }
      }
    }];
    const layoutFull = {
      width: target.clientWidth || window.innerWidth - 48,
      height: target.clientHeight || window.innerHeight - 120,
      margin: { l: 10, r: 10, b: 10, t: 10 },
      paper_bgcolor: '#020617',
      scene: {
        xaxis: { title: 'Tramas de Tiempo', color: '#94a3b8', gridcolor: '#1e293b' },
        yaxis: { title: 'Bandas de Frecuencia', color: '#94a3b8', gridcolor: '#1e293b' },
        zaxis: { title: 'Potencia (dB)', color: '#94a3b8', gridcolor: '#1e293b' },
        camera: { eye: { x: 1.5, y: 1.5, z: 1.1 } }
      }
    };
    Plotly.newPlot(target, traceFull, layoutFull, { responsive: true, displayModeBar: true })
      .then(() => Plotly.Plots.resize(target));
  }, 100);
}

/**
 * Cierra el visor de pantalla completa de la Topología Espectral 3D.
 */
function close3DLightbox() {
  const modal = document.getElementById('modal-3d-lightbox');
  if (modal) modal.classList.add('hidden');
}

// Permite cerrar cualquier visor ampliado presionando la tecla ESC
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    closeSpectrogramLightbox();
    close3DLightbox();
  }
});

/**
 * Renderiza la Radiografía DSP del Canal (SNR, RMS, Factor de Cresta, Nyquist),
 * los dos espectrogramas comparativos STFT y la superficie 3D interactiva.
 */
function renderCommsDiagnostics(data) {
  const section = document.getElementById('comms-analysis-section');
  if (!section) return;

  const rad = data.comms_radiography;
  if (!rad) {
    section.classList.add('hidden');
    return;
  }

  // Mostrar métricas numéricas de Sistemas de Comunicaciones en la columna izquierda
  section.classList.remove('hidden');
  document.getElementById('comms-metrics-left')?.classList.remove('hidden');
  document.getElementById('comms-snr').innerText = `${rad.snr_db} dB`;
  document.getElementById('comms-rms').innerText = `${rad.rms_db} dBFS`;
  document.getElementById('comms-crest').innerText = `${rad.crest_factor_db} dB`;
  document.getElementById('comms-nyquist').innerText = `${rad.nyquist_freq_hz} / ${rad.sample_rate_hz} Hz`;
  document.getElementById('comms-filter-spec').innerText = `🔧 ${rad.filter_spec} | Centroide Espectral: ${rad.centroid_hz} Hz`;

  // Actualizar etiqueta de estado de calidad del canal acústico según el SNR
  const badge = document.getElementById('comms-channel-badge');
  badge.innerText = rad.channel_status;
  if (rad.channel_status.includes('Clear')) {
    badge.className = "text-[10px] font-semibold px-2.5 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300 border border-emerald-500/30";
  } else if (rad.channel_status.includes('Moderate')) {
    badge.className = "text-[10px] font-semibold px-2.5 py-0.5 rounded-full bg-amber-500/20 text-amber-300 border border-amber-500/30";
  } else {
    badge.className = "text-[10px] font-semibold px-2.5 py-0.5 rounded-full bg-rose-500/20 text-rose-300 border border-rose-500/30";
  }

  // Cargar imagen Base64 del espectrograma de la señal capturada (consulta)
  const qBox = document.getElementById('query-spec-box');
  const qImg = document.getElementById('query-spec-img');
  if (data.query_spectrogram) {
    qImg.src = data.query_spectrogram;
    qBox.classList.remove('hidden');
  } else {
    qBox.classList.add('hidden');
  }

  // Cargar imagen Base64 del espectrograma de referencia (canción identificada)
  const mBox = document.getElementById('match-spec-box');
  const mImg = document.getElementById('match-spec-img');
  if (data.match_spectrogram) {
    mImg.src = data.match_spectrogram;
    mBox.classList.remove('hidden');
  } else {
    mBox.classList.add('hidden');
  }

  // Dibujar Gráfico 3D Interactivo (Superficie Tiempo x Frecuencia x Potencia dB)
  const box3d = document.getElementById('comms-3d-box');
  const plot3d = document.getElementById('comms-3d-plot');
  if (rad.surface_3d && rad.surface_3d.length > 0 && typeof Plotly !== 'undefined') {
    lastSurface3D = rad.surface_3d;
    box3d.classList.remove('hidden');
    setTimeout(() => {
      const widthPx = plot3d.clientWidth || 340;
      const trace3d = [{
        z: rad.surface_3d,
        type: 'surface',
        colorscale: 'Magma',
        showscale: false
      }];
      const layout3d = {
        width: widthPx,
        height: 270,
        margin: { l: 0, r: 0, b: 0, t: 0 },
        paper_bgcolor: '#020617',
        scene: {
          xaxis: { title: 'Tiempo', color: '#94a3b8', gridcolor: '#1e293b', showticklabels: false },
          yaxis: { title: 'Frec', color: '#94a3b8', gridcolor: '#1e293b', showticklabels: false },
          zaxis: { title: 'dB', color: '#94a3b8', gridcolor: '#1e293b', showticklabels: false },
          camera: { eye: { x: 1.5, y: 1.5, z: 1.1 } }
        }
      };
      Plotly.newPlot(plot3d, trace3d, layout3d, { responsive: true, displayModeBar: false })
        .then(() => Plotly.Plots.resize(plot3d));
    }, 150);
  } else if (box3d) {
    lastSurface3D = null;
    box3d.classList.add('hidden');
  }
}

let activeCommsView = 'spec';

function selectCommsView(view) {
    activeCommsView = view;
    const views = ['spec', 'wave', '3d', 'radio'];

    views.forEach(v => {
        const btn = document.getElementById(`tab-btn-${v}`);
        const panel = document.getElementById(`view-panel-${v}`);
        if (v === view) {
            btn?.classList.add('bg-indigo-600', 'text-white', 'shadow');
            btn?.classList.remove('text-slate-400');
            panel?.classList.remove('hidden');
        } else {
            btn?.classList.remove('bg-indigo-600', 'text-white', 'shadow');
            btn?.classList.add('text-slate-400');
            panel?.classList.add('hidden');
        }
    });

    const alertBox = document.getElementById('ref-missing-alert');
    if (alertBox && alertBox.dataset.hasError === 'true') {
        if (view === 'spec' || view === 'wave') {
            alertBox.classList.remove('hidden');
        } else {
            alertBox.classList.add('hidden');
        }
    }

    if (view === '3d' && typeof Plotly !== 'undefined') {
        const plotEl = document.getElementById('comms-3d-plot');
        if (plotEl && plotEl.data) {
            setTimeout(() => Plotly.Plots.resize(plotEl), 50);
        }
    }
}

function populateWaveformAndDiagnostics(data) {
    const qWaveBox = document.getElementById('query-wave-box');
    const qWaveImg = document.getElementById('query-wave-img');
    if (data.query_waveform && qWaveBox && qWaveImg) {
        qWaveImg.src = data.query_waveform;
        qWaveBox.classList.remove('hidden');
    } else {
        qWaveBox?.classList.add('hidden');
    }

    const mWaveBox = document.getElementById('match-wave-box');
    const mWaveImg = document.getElementById('match-wave-img');
    if (data.match_waveform && mWaveBox && mWaveImg) {
        mWaveImg.src = data.match_waveform;
        mWaveBox.classList.remove('hidden');
    } else {
        mWaveBox?.classList.add('hidden');
    }

    const alertBox = document.getElementById('ref-missing-alert');
    const reasonEl = document.getElementById('ref-missing-reason');
    const metricsEl = document.getElementById('ref-missing-metrics');

    if (alertBox) {
        if (data.ref_visual_error) {
            alertBox.dataset.hasError = 'true';
            if (reasonEl) reasonEl.innerText = data.ref_visual_error;
            if (metricsEl && data.comms_radiography) {
                const r = data.comms_radiography;
                metricsEl.innerText = `Indicadores capturados → SNR: ${r.snr_db ?? '--'} dB | RMS: ${r.rms_dbfs ?? '--'} dBFS | Duración: ${r.duration_s ?? '--'}s`;
            }
        } else {
            alertBox.dataset.hasError = 'false';
            alertBox.classList.add('hidden');
        }
    }

    if (data.comms_radiography) {
        const r = data.comms_radiography;
        if (document.getElementById('tab-radio-snr')) document.getElementById('tab-radio-snr').innerText = `${r.snr_db ?? '--'} dB`;
        if (document.getElementById('tab-radio-rms')) document.getElementById('tab-radio-rms').innerText = `${r.rms_dbfs ?? '--'} dBFS`;
        if (document.getElementById('tab-radio-crest')) document.getElementById('tab-radio-crest').innerText = `${r.crest_factor_db ?? '--'} dB`;
        if (document.getElementById('tab-radio-nyquist')) document.getElementById('tab-radio-nyquist').innerText = `${r.nyquist_hz ?? 11025} Hz / ${r.sample_rate ?? 22050} Hz`;
        if (document.getElementById('tab-radio-dur')) document.getElementById('tab-radio-dur').innerText = `${r.duration_s ?? '--'} s`;
        if (document.getElementById('tab-radio-badge') && r.channel_quality) {
            document.getElementById('tab-radio-badge').innerText = r.channel_quality;
        }
    }

    selectCommsView(activeCommsView || 'spec');
}

/**
 * Cambia la pista activa en el reproductor cuando el usuario selecciona
 * una de las canciones alternativas del ranking Top 5.
 */
function playPreviewTrack(url, title, artist) {
  const previewContainer = document.getElementById('preview-container');
  const audioPlayer = document.getElementById('song-preview-player');
  document.getElementById('res-title').innerText = title;
  document.getElementById('res-artist').innerText = artist;
  audioPlayer.src = url;
  previewContainer.classList.remove('hidden');
  audioPlayer.play();
}

/**
 * Pausa la reproducción activa y cierra el modal de resultados.
 */
function closeResultModal() {
  const audioPlayer = document.getElementById('song-preview-player');
  if (audioPlayer) {
    audioPlayer.pause();
    audioPlayer.currentTime = 0;
  }
  document.getElementById('result-modal').classList.add('hidden');
}

// --- MANEJADOR DE CARGA DE ARCHIVOS DE AUDIO (.MP3, .WAV, .OGG, .M4A) ---
uploadBtn.addEventListener('click', () => {
  if (!isAnalyzing && !isRecording) {
    audioFileInput.click();
  }
});

audioFileInput.addEventListener('change', async (e) => {
  const file = e.target.files[0];
  if (!file || isAnalyzing) return;

  const formData = new FormData();
  formData.append('audio_file', file);
  formData.append('is_mic', 'false'); // Indica al backend que es un archivo digital directo

  // Limpiar el input para permitir volver a subir el mismo archivo si se desea
  e.target.value = '';

  await sendAudioToBackend(formData, `Analizando "${file.name}"...`);
});

// --- GRABACIÓN EN TIEMPO REAL DESDE MICRÓFONO (CAPTURA PCM SIN FILTROS DESTRUCTIVOS) ---
micBtn.addEventListener('click', async () => {
  if (isAnalyzing) return;

  if (!isRecording) {
    try {
      // Desactivar filtros automáticos de voz (AEC, NS, AGC) para conservar armónicos musicales reales
      micStream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: false,
          noiseSuppression: false,
          autoGainControl: false,
          channelCount: 1
        }
      });
      audioContext = new (window.AudioContext || window.webkitAudioContext)();

      // Reanudar el contexto de audio si el navegador lo inicia suspendido
      if (audioContext.state === 'suspended') {
        await audioContext.resume();
      }

      recordingSampleRate = audioContext.sampleRate;

      // Conectar flujo de micrófono al procesador de bloques PCM (4096 muestras por frame)
      const source = audioContext.createMediaStreamSource(micStream);
      scriptProcessor = audioContext.createScriptProcessor(4096, 1, 1);
      recordedBuffers = [];

      scriptProcessor.onaudioprocess = (e) => {
        if (!isRecording) return;
        const inputData = e.inputBuffer.getChannelData(0);
        recordedBuffers.push(new Float32Array(inputData));
      };

      source.connect(scriptProcessor);
      scriptProcessor.connect(audioContext.destination);

      isRecording = true;
      micBtn.classList.add('animate-pulse', 'border-pink-600', 'bg-pink-950/40');
      micBtnText.textContent = "GRABANDO";
      statusIndicator.textContent = "Escuchando audio ambiental (10s)...";

      visualizerContainer.classList.remove('hidden');
      recordingProgress.style.width = '0%';

      // Temporizador de captura automática de 10 segundos (100 pasos x 100ms)
      let progress = 0;
      recordingInterval = setInterval(() => {
        progress += (100 / 100);
        if (progress >= 100) {
          progress = 100;
          if (isRecording) stopRecording();
        }
        recordingProgress.style.width = progress + '%';
      }, 100);

      // Animación visual de las barras del ecualizador durante la grabación
      eqInterval = setInterval(() => {
        eqBars.forEach(bar => {
          const randomHeight = Math.floor(Math.random() * 85) + 15;
          bar.style.height = randomHeight + '%';
        });
      }, 150);

    } catch (err) {
      alert("Acceso al micrófono denegado: " + err);
    }
  } else {
    stopRecording();
  }
});

/**
 * Genera un identificador único con marca de tiempo y código aleatorio para cada
 * captura de audio ambiental, evitando colisiones en el servidor.
 */
function generateAudioSerial() {
  const now = new Date();
  const timestamp = now.toISOString().replace(/[-:T.Z]/g, '').slice(0, 14);
  const randomCode = Math.random().toString(36).substring(2, 6).toUpperCase();
  return `mic_${timestamp}_${randomCode}.wav`;
}

/**
 * Detiene la captura del micrófono, libera los recursos de hardware (MediaStream y AudioContext),
 * empaqueta los buffers acumulados en formato WAV PCM y los envía al backend Flask.
 */
async function stopRecording() {
  if (!isRecording) return;
  isRecording = false;

  clearInterval(recordingInterval);
  clearInterval(eqInterval);
  micBtn.classList.remove('animate-pulse', 'border-pink-600', 'bg-pink-950/40');
  micBtnText.textContent = "ESCUCHAR";
  visualizerContainer.classList.add('hidden');

  try {
    // Desconectar procesador y detener pistas físicas del micrófono
    if (scriptProcessor) {
      scriptProcessor.onaudioprocess = null;
      scriptProcessor.disconnect();
      scriptProcessor = null;
    }
    if (micStream) {
      micStream.getTracks().forEach(track => track.stop());
      micStream = null;
    }
    if (audioContext && audioContext.state !== 'closed') {
      audioContext.close().catch(() => {});
      audioContext = null;
    }

    if (!recordedBuffers || recordedBuffers.length === 0) {
      alert("⚠️ No se capturó audio del micrófono.");
      return;
    }

    // 1. Codificar los bloques Float32 en un archivo WAV estándar de 16 bits y liberar memoria
    const wavBlob = encodeWAV(recordedBuffers, recordingSampleRate);
    const capturedChunksCount = recordedBuffers.length;
    recordedBuffers = [];

    // 2. Asignar nombre de serie único y enviar al endpoint /api/analyze
    const audioSerialName = generateAudioSerial();
    console.log(`🆕 Nuevo audio generado: ${audioSerialName} | Bloques: ${capturedChunksCount} | Tamaño: ${wavBlob.size} bytes`);

    const formData = new FormData();
    formData.append('audio_data', wavBlob, audioSerialName);
    formData.append('is_mic', 'true');

    await sendAudioToBackend(formData, `Analizando muestra en vivo (${audioSerialName})...`);
  } catch (err) {
    recordedBuffers = [];
    console.error("❌ Error al detener la grabación:", err);
    alert("Error al procesar el audio: " + err.message);
  }
}

/**
 * Codificador de Audio WAV (RIFF / PCM 16-bit Mono) con Control Automático de Ganancia (AGC)
 * basado en potencia RMS y limitador de picos para evitar saturación (clipping).
 */
function encodeWAV(buffers, sampleRate) {
  // 1. Concatenar todos los fragmentos de tiempo capturados en un único arreglo continuo
  let totalLength = buffers.reduce((acc, buf) => acc + buf.length, 0);
  let samples = new Float32Array(totalLength);
  let offset = 0;
  for (let buf of buffers) {
    samples.set(buf, offset);
    offset += buf.length;
  }

  // 2. Calcular valor eficaz (RMS) y amplitud pico máxima para calibrar la ganancia
  let sumSquares = 0;
  let maxPeak = 0;
  for (let i = 0; i < samples.length; i++) {
    const absVal = Math.abs(samples[i]);
    sumSquares += samples[i] * samples[i];
    if (absVal > maxPeak) maxPeak = absVal;
  }
  const rms = Math.sqrt(sumSquares / samples.length);

  // Aplicar ganancia adaptativa (máx. 10x) acotando el pico máximo a 0.85 (-1.4 dBFS)
  let desiredGain = rms > 0.001 ? Math.min(10.0, 0.12 / rms) : 1.0;
  if (maxPeak * desiredGain > 0.85 && maxPeak > 0) {
    desiredGain = 0.85 / maxPeak;
  }
  const gain = desiredGain;

  const rmsDb = rms > 0 ? (20 * Math.log10(rms)).toFixed(2) : "-Inf";
  console.log(`🎙️ [Nivel de Micrófono]: RMS = ${rms.toFixed(4)} (${rmsDb} dBFS) | Pico = ${maxPeak.toFixed(4)} | Ganancia = ${gain.toFixed(2)}x`);

  // 3. Construir la cabecera estándar de 44 bytes del contenedor RIFF/WAVE
  let buffer = new ArrayBuffer(44 + samples.length * 2);
  let view = new DataView(buffer);

  const writeString = (view, offset, string) => {
    for (let i = 0; i < string.length; i++) {
      view.setUint8(offset + i, string.charCodeAt(i));
    }
  };

  writeString(view, 0, 'RIFF');
  view.setUint32(4, 36 + samples.length * 2, true);
  writeString(view, 8, 'WAVE');
  writeString(view, 12, 'fmt ');
  view.setUint32(16, 16, true);           // Tamaño del sub-bloque PCM
  view.setUint16(20, 1, true);            // Formato de audio 1 = PCM sin compresión
  view.setUint16(22, 1, true);            // Número de canales: 1 (Mono)
  view.setUint32(24, sampleRate, true);   // Frecuencia de muestreo (Hz)
  view.setUint32(28, sampleRate * 2, true); // Tasa de bytes por segundo (SampleRate * 2 bytes)
  view.setUint16(32, 2, true);            // Alineación de bloque (2 bytes por muestra)
  view.setUint16(34, 16, true);           // Profundidad de bits: 16 bits
  writeString(view, 36, 'data');
  view.setUint32(40, samples.length * 2, true);

  // 4. Cuantizar las muestras normalizadas de punto flotante [-1, 1] a enteros de 16 bits con signo
  let pos = 44;
  for (let i = 0; i < samples.length; i++, pos += 2) {
    let s = Math.max(-1, Math.min(1, samples[i] * gain));
    view.setInt16(pos, s < 0 ? s * 0x8000 : s * 0x7FFF, true);
  }

  return new Blob([view], { type: 'audio/wav' });
}

/**
 * Envía el archivo de audio (grabación en vivo o archivo subido) al endpoint /api/analyze
 * y despliega tanto la canción identificada como la radiografía DSP y espectrogramas.
 */
async function sendAudioToBackend(formData, loadingMsg) {
  setLoadingState(true, loadingMsg);

  try {
    const response = await fetch('/api/analyze', {
      method: 'POST',
      body: formData
    });
    const data = await response.json();
    console.log("Respuesta de Flask:", data);

    if (data.success) {
      const matchData = data.top_match || data.prediction;
      if (matchData) {
        showResultModal(matchData, data.ranking || []);
        renderCommsDiagnostics(data);
        populateWaveformAndDiagnostics(data);
      } else {
        alert("⚠️ El servidor respondió con éxito, pero no envió datos de la canción.");
      }
    } else {
      alert("⚠️ Error de análisis: " + (data.error || "Error desconocido"));
    }
  } catch (error) {
    console.error("❌ Error procesando respuesta de Flask:", error);
    alert("❌ Error al conectar o leer la respuesta del servidor Flask.");
  } finally {
    setLoadingState(false);
  }
}

// --- MÉTRICAS GLOBALES DE PRECISIÓN DEL SISTEMA ---
let hasVotedCurrentSong = false;

/**
 * Consulta en el backend la tasa histórica de aciertos del sistema (/api/stats).
 */
async function fetchGlobalStats() {
  try {
    const res = await fetch('/api/stats');
    const stats = await res.json();
    updateAccuracyUI(stats);
  } catch (err) {
    console.error("Error cargando estadísticas:", err);
  }
}

/**
 * Actualiza los indicadores porcentuales de precisión en la vista principal y en el modal.
 */
function updateAccuracyUI(stats) {
  const accFormatted = stats.accuracy.toFixed(2) + '%';
  const fractionFormatted = `${stats.successes}/${stats.attempts}`;

  const globalText = document.getElementById('global-accuracy-text');
  const globalFraction = document.getElementById('global-stats-fraction');
  if (globalText) globalText.innerText = accFormatted;
  if (globalFraction) globalFraction.innerText = fractionFormatted;

  const modalAcc = document.getElementById('accuracy-percentage');
  const modalFrac = document.getElementById('stats-fraction');
  if (modalAcc) modalAcc.innerText = accFormatted;
  if (modalFrac) modalFrac.innerText = fractionFormatted;
}

// 3. Función que llaman tus botones "Yes :)" -> registerFeedback(true) y "No :(" -> registerFeedback(false)
async function registerFeedback(isSuccess) {
    if (hasVotedCurrentSong) return;
    hasVotedCurrentSong = true;

    try {
        const res = await fetch('/api/feedback', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ success: isSuccess })
        });
        if (!res.ok) throw new Error("Error en el servidor");

        const updatedStats = await res.json();
        updateAccuracyUI(updatedStats);

        // Deshabilitar botones y mostrar confirmación
        const feedbackBtns = document.querySelectorAll('#result-modal button[onclick*="registerFeedback"]');
        feedbackBtns.forEach(btn => {
            btn.classList.add('opacity-50', 'cursor-not-allowed');
            btn.disabled = true;
        });

        // Agregar el mensaje de gracias con su ID para poder borrarlo en la siguiente canción
        const feedbackContainer = feedbackBtns[0]?.parentElement?.parentElement;
        if (feedbackContainer && !document.getElementById('feedback-thanks-msg')) {
            const thanksMsg = document.createElement('p');
            thanksMsg.id = 'feedback-thanks-msg';
            thanksMsg.className = 'text-xs text-emerald-400 font-medium pt-2';
            thanksMsg.innerText = '¡Gracias por tu feedback!';
            feedbackContainer.appendChild(thanksMsg);
        }
    } catch (err) {
        console.error("Error enviando feedback:", err);
        hasVotedCurrentSong = false; // Permite reintentar si falló
    }
}

// Ejecutar al cargar la página
document.addEventListener('DOMContentLoaded', fetchGlobalStats);
