# A reproducible, public-hosting image for the Streamlit transcription app.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/opt/models \
    XDG_CACHE_HOME=/opt/models

WORKDIR /app

# CTranslate2 uses OpenMP for CPU transcription.
RUN apt-get update \
    && apt-get install --no-install-recommends -y libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Bake the recommended model into the image so the public service is ready
# on its first user request, rather than downloading it at runtime.
RUN python -c "from faster_whisper import WhisperModel; WhisperModel('small', device='cpu', compute_type='int8')"

COPY . ./

RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app /opt/models

USER appuser
EXPOSE 8501

CMD ["sh", "-c", "streamlit run main.py --server.address=0.0.0.0 --server.port=${PORT:-8501} --server.headless=true --browser.gatherUsageStats=false"]
