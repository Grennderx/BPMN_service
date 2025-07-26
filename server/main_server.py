import os
import tempfile
import time
import logging
import requests

from fastapi import FastAPI, HTTPException, Body, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse

from dotenv import load_dotenv

from event_chain_agent import EventChainAgent, JSONParseError
from bpmn_agent import BPMNAgent
from critic_agent import CriticAgent
from datetime import datetime
# Для Llama
from llama_cpp import Llama

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)

# Загрузим переменные .env (для AssemblyAI API key)
load_dotenv()

ASSEMBLYAI_API_KEY = "**"
if not ASSEMBLYAI_API_KEY:
    logger.error("ASSEMBLYAI_API_KEY not set in .env")
    raise RuntimeError("Set ASSEMBLYAI_API_KEY in .env")

# Константы
UPLOAD_FOLDER = tempfile.gettempdir()
TRANSCRIPT_FILE = "transcripts.txt"
ALLOWED_EXTENSIONS = {"wav", "mp3", "ogg"}

# Инициализируем FastAPI
app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

# Инициализация Llama и агентов
MODEL_PATH = r"model\Qwen2.5-14B-Instruct-GGUF\Qwen2.5-14B-Instruct-Q4_K_M.gguf"
model = Llama.from_pretrained(
    repo_id="lmstudio-community/Qwen2.5-14B-Instruct-1M-GGUF",
    filename="Qwen2.5-14B-Instruct-1M-Q4_K_M.gguf",
    n_gpu_layers=-1, split_mode=1, main_gpu=0,
    max_tokens=8000, n_ctx=32768, n_batch=1024,
    use_mlock=True, offload_kqv=True, flash_attn=True,
    verbose=False
)

event_agent  = EventChainAgent(model)
bpmn_agent   = BPMNAgent(model)
critic_agent = CriticAgent(model)

# --------------------
# НОВЫЕ ФУНКЦИИ ДЛЯ ТРАНСКРИПЦИИ
# --------------------
def allowed_file(filename: str) -> bool:
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def upload_file_to_assemblyai(file_path: str) -> str:
    """Загружает аудио на AssemblyAI и возвращает upload_url."""
    upload_url = "https://api.assemblyai.com/v2/upload"
    with open(file_path, 'rb') as ff:
        res = requests.post(
            upload_url,
            headers={"authorization": ASSEMBLYAI_API_KEY},
            data=ff.read(),
            timeout=30
        )
    res.raise_for_status()
    return res.json()["upload_url"]

def create_transcript(audio_url: str) -> str:
    """Создаёт задачу транскрипции и возвращает её ID."""
    transcript_url = "https://api.assemblyai.com/v2/transcript"
    data = {
        "audio_url": audio_url,
        "language_code": "ru",
        "speech_model": "best"
    }
    res = requests.post(transcript_url, json=data,
                        headers={"authorization": ASSEMBLYAI_API_KEY},
                        timeout=30)
    res.raise_for_status()
    return res.json()["id"]

def poll_transcript(transcript_id: str) -> str:
    """Ожидает готовности транскрипции и возвращает текст."""
    polling_url = f"https://api.assemblyai.com/v2/transcript/{transcript_id}"
    start = time.time()
    while True:
        if time.time() - start > 300:
            raise TimeoutError("Таймаут транскрипции")
        res = requests.get(polling_url,
                           headers={"authorization": ASSEMBLYAI_API_KEY})
        res.raise_for_status()
        data = res.json()
        if data["status"] == "completed":
            return data["text"]
        if data["status"] == "error":
            raise Exception(f"AssemblyAI error: {data.get('error')}")
        time.sleep(2)

@app.post("/transcribe")
async def transcribe_audio(audio: UploadFile = File(...)):
    # Проверка формата
    if not allowed_file(audio.filename):
        raise HTTPException(status_code=400, detail="Неподдерживаемый формат")
    # Сохраним во временный файл
    temp_path = os.path.join(UPLOAD_FOLDER, audio.filename)
    try:
        with open(temp_path, "wb") as f:
            f.write(await audio.read())
        # Загрузка, создание и ожидание транскрипции
        upload_url = upload_file_to_assemblyai(temp_path)
        transcript_id = create_transcript(upload_url)
        text = poll_transcript(transcript_id)
        # Опционально: сохраняем в лог
        with open(TRANSCRIPT_FILE, "a", encoding="utf-8") as tf:
            tf.write(f"{datetime.now().isoformat()}\t{text}\n")
        return {"success": True, "text": text}
    except Exception as e:
        logger.exception("transcribe failed")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

# --------------------
# Существующие маршруты вашего FastAPI
# --------------------
@app.get("/", response_class=HTMLResponse)
def home():
    return open("static/index.html", encoding="utf-8").read()

@app.post("/generate-event-chain")
def generate_event_chain(process_description: str = Body(..., embed=True)):
    try:
        if not process_description.strip():
            raise ValueError("Описание процесса не может быть пустым")
        return event_agent.generate_chain(process_description)
    except JSONParseError as e:
        raise HTTPException(400, str(e))
    except Exception:
        raise HTTPException(500, "Internal server error")

@app.post("/generate-bpmn")
def generate_bpmn(request_data: dict = Body(...)):
    try:
        xml, name = bpmn_agent.generate_raw_bpmn(
            request_data["event_chain"],
            request_data.get("filename")
        )
        return {"bpmn_xml": xml, "filename": name}
    except Exception as e:
        raise HTTPException(422, str(e))

@app.get("/diagram/{file_name}")
def get_diagram(file_name: str):
    path = os.path.join("exported_diagrams", file_name)
    if not os.path.exists(path):
        raise HTTPException(404, "File not found")
    return FileResponse(path, media_type="application/xml")

@app.post("/analyze-diagram")
def analyze_diagram(request_data: dict = Body(...)):
    try:
        return critic_agent.analyze_diagram(request_data.get("bpmn_json", {}))
    except Exception as e:
        raise HTTPException(422, str(e))

@app.post("/apply-fixes")
def apply_fixes(request_data: dict = Body(...)):
    try:
        original = request_data["original"]
        analysis = request_data["analysis"]
        issues = [
            *[err["message"] for err in analysis["algorithm_errors"]],
            *analysis["llm_recommendations"].get("recommendations", []),
            *analysis["llm_recommendations"].get("critical_issues", [])
        ]
        modified = critic_agent.generate_llm_fixes(original, issues)
        bpmn_xml, filename = bpmn_agent.generate_raw_bpmn(modified, None)
        return {"modified_data": modified, "bpmn_xml": bpmn_xml, "filename": filename}
    except Exception as e:
        raise HTTPException(422, str(e))

# --------------------
# Запуск
# --------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main_server:app", host="0.0.0.0", port=8000, reload=True)
