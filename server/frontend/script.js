let mediaRecorder;
let audioChunks = [];
const recordButton = document.getElementById('recordButton');
const statusDiv = document.getElementById('status');

// Инициализация аудио потока
navigator.mediaDevices.getUserMedia({ audio: true })
    .then(stream => {
        mediaRecorder = new MediaRecorder(stream);

        mediaRecorder.ondataavailable = event => {
            audioChunks.push(event.data);
        };

        mediaRecorder.onstop = async () => {
            const audioBlob = new Blob(audioChunks, { type: 'audio/wav' });
            await sendAudioToServer(audioBlob);
            audioChunks = [];
        };
    })
    .catch(err => {
        console.error('Ошибка доступа к микрофону:', err);
    });

// Обработчик кнопки записи
recordButton.addEventListener('click', () => {
    if (mediaRecorder.state === 'inactive') {
        mediaRecorder.start();
        recordButton.textContent = '⏹ Остановить запись';
        statusDiv.textContent = 'Статус: Запись...';
    } else {
        mediaRecorder.stop();
        recordButton.textContent = '🎤 Начать запись';
        statusDiv.textContent = 'Статус: Обработка...';
    }
});

// Отправка аудио на сервер
async function sendAudioToServer(audioBlob) {
    const formData = new FormData();
    formData.append('audio', audioBlob, 'recording.wav');

    try {
        const response = await fetch('http://localhost:5000/transcribe', {
            method: 'POST',
            body: formData
        });

        const result = await response.json();

        if (result.success) {
            // Добавляем новый результат
            const resultsContainer = document.getElementById('resultsContainer');
            const resultCard = document.createElement('div');
            resultCard.className = 'result-card';
            resultCard.innerHTML = `
                <p style="margin: 0; color: #333; font-size: 16px;">
                    ${result.text}
                </p>
                <small style="color: #666; display: block; margin-top: 8px;">
                    ${new Date().toLocaleTimeString()}
                </small>
            `;
            resultsContainer.prepend(resultCard);

            statusDiv.textContent = 'Запись сохранена';
        } else {
            statusDiv.textContent = 'Ошибка: ' + result.error;
            statusDiv.parentElement.style.background = '#fee';
            statusDiv.parentElement.style.borderLeft = '4px solid var(--error)';
        }
    } catch (error) {
        console.error('Ошибка:', error);
        statusDiv.textContent = 'Ошибка соединения с сервером';
    }
}

// Анимация кнопки
recordButton.addEventListener('click', function() {
    this.classList.toggle('recording');
});