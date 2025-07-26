from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import tempfile
import requests
import time
import logging
from dotenv import load_dotenv
from datetime import datetime
# Настройка логирования
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

load_dotenv()

app = Flask(__name__)
CORS(app)

# Конфигурация
UPLOAD_FOLDER = tempfile.gettempdir()
ALLOWED_EXTENSIONS = {'wav', 'mp3', 'ogg'}
TRANSCRIPT_FILE = "transcripts.txt"
ASSEMBLYAI_API_KEY = "**"

# Проверка API ключа
if not ASSEMBLYAI_API_KEY:
    logger.error("ASSEMBLYAI_API_KEY не найден в .env файле")
    raise ValueError("Требуется AssemblyAI API Key")

HEADERS = {
    "authorization": ASSEMBLYAI_API_KEY,
    "content-type": "application/json"
}


def allowed_file(filename):
    return '.' in filename and \
        filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def upload_file(file_path):
    """Загрузка файла в AssemblyAI с обработкой ошибок"""
    try:
        logger.debug(f"Загрузка файла: {file_path}")
        upload_url = "https://api.assemblyai.com/v2/upload"

        with open(file_path, 'rb') as ff:
            response = requests.post(
                upload_url,
                headers={"authorization": ASSEMBLYAI_API_KEY},
                data=ff.read(),
                timeout=30
            )

        response.raise_for_status()
        return response.json()['upload_url']

    except Exception as e:
        logger.error(f"Ошибка загрузки: {str(e)}")
        raise


def create_transcript(audio_url):
    """Создание задачи транскрипции с правильными параметрами"""
    try:
        logger.debug(f"Создание транскрипции для: {audio_url}")
        transcript_url = "https://api.assemblyai.com/v2/transcript"

        data = {
            "audio_url": audio_url,
            "language_code": "ru",
            "speech_model": "best"  # Исправленный параметр
        }

        response = requests.post(
            transcript_url,
            json=data,
            headers=HEADERS,
            timeout=30
        )

        logger.debug(f"Ответ API: {response.status_code} {response.text}")
        response.raise_for_status()

        return response.json()['id']

    except requests.exceptions.HTTPError as e:
        logger.error(f"HTTP Error: {e.response.text}")
        raise
    except Exception as e:
        logger.error(f"Общая ошибка: {str(e)}")
        raise


def get_transcript(transcript_id):
    """Получение результатов транскрипции"""
    try:
        logger.debug(f"Получение транскрипции ID: {transcript_id}")
        polling_url = f"https://api.assemblyai.com/v2/transcript/{transcript_id}"
        start_time = time.time()

        while True:
            if time.time() - start_time > 300:
                raise TimeoutError("Таймаут ожидания транскрипции")

            response = requests.get(polling_url, headers=HEADERS)
            response.raise_for_status()
            data = response.json()

            if data['status'] == 'completed':
                return data['text']
            elif data['status'] == 'error':
                raise Exception(f"Ошибка транскрипции: {data.get('error', 'Unknown')}")

            time.sleep(2)

    except Exception as e:
        logger.error(f"Ошибка получения: {str(e)}")
        raise


@app.route('/transcribe', methods=['POST'])
def transcribe_audio():
    try:
        if 'audio' not in request.files:
            return jsonify({"success": False, "error": "Файл не предоставлен"}), 400

        file = request.files['audio']
        if not file or file.filename == '':
            return jsonify({"success": False, "error": "Неверный файл"}), 400

        if not allowed_file(file.filename):
            return jsonify({"success": False, "error": "Неподдерживаемый формат"}), 400

        temp_path = None
        try:
            # Сохраняем временный файл
            temp_path = os.path.join(UPLOAD_FOLDER, file.filename)
            file.save(temp_path)

            # Основной процесс транскрипции
            audio_url = upload_file(temp_path)
            transcript_id = create_transcript(audio_url)
            transcript_text = get_transcript(transcript_id)

            # Сохранение результата
            with open(TRANSCRIPT_FILE, "a", encoding="utf-8") as f:
                f.write(f"{transcript_text}\n")

            return jsonify({
                "success": True,
                "text": transcript_text
            })

        finally:
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)

    except Exception as e:
        logger.error(f"Финальная ошибка: {str(e)}")
        return jsonify({
            "success": False,
            "error": f"Ошибка обработки: {str(e)}"
        }), 500


if __name__ == '__main__':
    if not os.path.exists(TRANSCRIPT_FILE):
        with open(TRANSCRIPT_FILE, "w", encoding="utf-8") as f:
            pass

    app.run(host='0.0.0.0', port=5000)
