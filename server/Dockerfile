FROM python:3.9-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      build-essential cmake git supervisor \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Если у вас есть кастомный модуль bpmn_diagram_rep.py
COPY bpmn_diagram_rep.py /usr/local/lib/python3.9/site-packages/bpmn_python/bpmn_diagram_rep.py
ENV HF_HUB_ENABLE_PROGRESS_BARS=true
COPY . .

RUN mkdir -p exported_diagrams static

# копируем скорректированный конфиг
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

EXPOSE 8000 8005

CMD ["supervisord", "-n"]
