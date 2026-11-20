
const chatToggleBtn = document.getElementById('chat-toggle-btn');
        const chatCloseBtn = document.getElementById('chat-close-btn');
        const chatWindow = document.getElementById('chat-window');
        const chatMessages = document.getElementById('chat-messages');
        const chatInput = document.getElementById('chat-input');
        const chatSendBtn = document.getElementById('chat-send-btn');
        
        const micBtn = document.getElementById('mic-btn');
        const micBtnText = document.getElementById('mic-btn-text');
        const uploadBtn = document.getElementById('upload-btn');
        const audioFileInput = document.getElementById('audio-file-input');
        const statusIndicator = document.getElementById('status-indicator');
        const visualizerContainer = document.getElementById('visualizer-container');
        const recordingProgress = document.getElementById('recording-progress');
        const eqBars = document.querySelectorAll('.eq-bar');

        let mediaRecorder;
        let audioChunks = [];
        let isRecording = false;
        let recordingInterval;
        let eqInterval;

        chatToggleBtn.addEventListener('click', () => chatWindow.classList.toggle('hidden'));
        chatCloseBtn.addEventListener('click', () => chatWindow.classList.add('hidden'));

        let totalAttempts = 0;
        let totalSuccesses = 0;

        // Handle file upload from laptop and trigger backend analysis
        function uploadAndAnalyze() {
            const fileInput = document.getElementById('audio-file-input');
            
            if (fileInput.files.length === 0) {
                alert("Please select an audio file from your computer first. :3");
                return;
            }

            const formData = new FormData();
            formData.append('audio', fileInput.files[0]);
            formData.append('is_mic', 'false'); // File uploaded from device

            console.log("📤 Uploading audio file and processing constellation fingerprints with MarIA...");

            fetch('/api/analyze', {
                method: 'POST',
                body: formData
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    const topMatch = data.top_match;
                    
                    // Open the Tailwind result modal with detected song details
                    showResultModal(topMatch);
                } else {
                    alert("⚠️ Analysis error: " + data.error);
                }
            })
            .catch(error => {
                console.error('❌ Network error:', error);
                alert("An error occurred while connecting to the Flask server.");
            });
        }

        // --- MODAL CONTROLS ---
        function showResultModal(topMatch) {
            document.getElementById('res-title').innerText = topMatch.title;
            document.getElementById('res-artist').innerText = topMatch.artist;
            document.getElementById('res-genre').innerText = topMatch.genre;
            document.getElementById('res-similarity').innerText = topMatch.percentage;
            
            // Remove 'hidden' class to display the Tailwind modal smoothly
            document.getElementById('result-modal').classList.remove('hidden');
        }

        function closeResultModal() {
            // Add 'hidden' class back to hide the modal
            document.getElementById('result-modal').classList.add('hidden');
        }

        // --- REAL-TIME FEEDBACK SYSTEM ---
        function registerFeedback(success) {
    totalAttempts++;
    if (success) {
        totalSuccesses++;
    }
    
    // Calculate real-time accuracy percentage
    let percentage = (totalSuccesses / totalAttempts) * 100;
    
    // Update DOM elements in real-time
    document.getElementById('accuracy-percentage').innerText = percentage.toFixed(2) + '%';
    document.getElementById('stats-fraction').innerText = `${totalSuccesses}/${totalAttempts}`;
    
    console.log(`✨ Feedback registered. Current stats: ${totalSuccesses}/${totalAttempts} (${percentage.toFixed(2)}%)`);
}
        
        function appendMessage(sender, htmlContent) {
            const messageDiv = document.createElement('div');
            if (sender === 'user') {
                messageDiv.className = 'flex justify-end';
                messageDiv.innerHTML = `<div class="bg-slate-800 text-slate-100 rounded-2xl rounded-tr-none p-3 max-w-[85%] shadow">${htmlContent}</div>`;
            } else {
                messageDiv.className = 'flex justify-start';
                messageDiv.innerHTML = `<div class="bg-indigo-600 text-white rounded-2xl rounded-tl-none p-3 max-w-[85%] shadow space-y-2">${htmlContent}</div>`;
            }
            chatMessages.appendChild(messageDiv);
            chatMessages.scrollTop = chatMessages.scrollHeight;
        }

        chatSendBtn.addEventListener('click', handleUserTextMessage);
        chatInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') handleUserTextMessage();
        });

        function handleUserTextMessage() {
            const text = chatInput.value.trim();
            if (!text) return;
            appendMessage('user', text);
            chatInput.value = '';
            setTimeout(() => {
                appendMessage('bot', `🤖 Received query: "<i>${text}</i>". You can use the central microphone for audio classification.`);
            }, 600);
        }

        uploadBtn.addEventListener('click', () => audioFileInput.click());

        audioFileInput.addEventListener('change', async (e) => {
            const file = e.target.files[0];
            if (!file) return;

            chatWindow.classList.remove('hidden');
            appendMessage('user', `📁 File uploaded: <b>${file.name}</b>`);
            statusIndicator.textContent = "Processing audio through neural pipeline...";

            const formData = new FormData();
            formData.append('audio_file', file);
            formData.append('is_mic', 'false');

            await sendAudioToBackend(formData);
        });

        // Live Microphone Recording with Equalizer & Progress Animation
        micBtn.addEventListener('click', async () => {
            if (!isRecording) {
                try {
                    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
                    mediaRecorder = new MediaRecorder(stream);
                    audioChunks = [];

                    mediaRecorder.ondataavailable = (event) => audioChunks.push(event.data);
                    mediaRecorder.onstop = async () => {
                        const audioBlob = new Blob(audioChunks, { type: 'audio/wav' });
                        const formData = new FormData();
                        formData.append('audio_data', audioBlob, 'mic_recording.wav');
                        formData.append('is_mic', 'true');

                        chatWindow.classList.remove('hidden');
                        appendMessage('user', `🎤 Live microphone capture completed.`);
                        statusIndicator.textContent = "Analyzing spectral constellation fingerprints...";
                        await sendAudioToBackend(formData);
                    };

                    mediaRecorder.start();
                    isRecording = true;
                    micBtn.classList.add('animate-pulse', 'border-pink-600', 'bg-pink-950/40');
                    micBtnText.textContent = "RECORDING";
                    statusIndicator.textContent = "Listening to ambient audio (15s)...";
                    
                    // Show equalizer visualizer and animate bars
                    visualizerContainer.classList.remove('hidden');
                    recordingProgress.style.width = '0%';
                    
                    let progress = 0;
                    recordingInterval = setInterval(() => {
                        progress += (100 / 150); // 15 seconds progress simulation
                        if (progress >= 100) {
                            progress = 100;
                            if (isRecording) stopRecording();
                        }
                        recordingProgress.style.width = progress + '%';
                    }, 100);

                    eqInterval = setInterval(() => {
                        eqBars.forEach(bar => {
                            const randomHeight = Math.floor(Math.random() * 85) + 15;
                            bar.style.height = randomHeight + '%';
                        });
                    }, 150);

                } catch (err) {
                    alert("Microphone access denied: " + err);
                }
            } else {
                stopRecording();
            }
        });

        function stopRecording() {
            if (isRecording && mediaRecorder && mediaRecorder.state !== 'inactive') {
                mediaRecorder.stop();
            }
            isRecording = false;
            clearInterval(recordingInterval);
            clearInterval(eqInterval);
            micBtn.classList.remove('animate-pulse', 'border-pink-600', 'bg-pink-950/40');
            micBtnText.textContent = "LISTEN";
            visualizerContainer.classList.add('hidden');
            statusIndicator.textContent = "Processing captured audio...";
        }

        async function sendAudioToBackend(formData) {
            try {
                const response = await fetch('/api/analyze', { method: 'POST', body: formData });
                const data = await response.json();

                if (data.success) {
                    const song = data.prediction;
                    let htmlResponse = `
                        <p>🎯 <b>Predicted Genre:</b> ${song.genre} (${song.confidence})</p>
                        <hr class="border-indigo-400/30 my-1">
                        <p>🎵 <b>Detected Track:</b><br>${song.artist} - ${song.title}</p>
                        <p class="text-[11px] text-indigo-200">📝 Lyrics: ${song.lyrics.substring(0, 80)}...</p>
                    `;
                    
                    if (song.audio_url) {
                        htmlResponse += `
                            <div class="mt-2 pt-1 border-t border-indigo-400/30">
                                <p class="text-[11px] mb-1">🎧 Play audio sample:</p>
                                <audio controls class="w-full h-7">
                                    <source src="${song.audio_url}" type="audio/mpeg">
                                    Your browser does not support audio playback.
                                </audio>
                            </div>
                        `;
                    }
                    appendMessage('bot', htmlResponse);
                } else {
                    appendMessage('bot', `❌ Error: ${data.error}`);
                }
            } catch (error) {
                appendMessage('bot', `❌ Server connection error with Flask backend.`);
            } finally {
                statusIndicator.textContent = "Click the microphone to record ambient audio (15s)";
            }
        }