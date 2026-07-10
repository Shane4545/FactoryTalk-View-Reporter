# Ops Reporter — always-on demo (sample DLGLOG from GitHub Release)
FROM python:3.11-slim-bookworm

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl unzip \
    && rm -rf /var/lib/apt/lists/*

COPY server/requirements.txt /app/server/requirements.txt
RUN pip install --no-cache-dir -r /app/server/requirements.txt

COPY dist /app/dist
COPY server /app/server
COPY scada_launcher.py run_ops_reporter.py /app/
COPY profiles /app/profiles

# 3-day Chalk River sample (~17 MB) — co-workers can browse Daily/Insights/Trends
ARG DEMO_ZIP_URL=https://github.com/Shane4545/FactoryTalk-View-Reporter/releases/download/demo-v1/demo_dlglog_chalk_river_3days.zip
RUN mkdir -p /app/demo_dlglog \
 && curl -fsSL "$DEMO_ZIP_URL" -o /tmp/demo.zip \
 && unzip -q /tmp/demo.zip -d /app/demo_dlglog \
 && rm /tmp/demo.zip \
 && ls -la /app/demo_dlglog

RUN mkdir -p /app/config /app/cache /app/archive /app/PDF /app/Web \
 && printf '%s\n' \
'{'\
'  "product": "Ops Reporter",'\
'  "version": "1.0.0",'\
'  "plant": {'\
'    "id": "chalk-river-demo",'\
'    "name": "Chalk River Water Treatment Plant",'\
'    "municipality": "Town of Laurentian Hills (demo)"'\
'  },'\
'  "dlglog_path": "/app/demo_dlglog",'\
'  "dlglog_candidates": ["/app/demo_dlglog"],'\
'  "models": {'\
'    "trend": "WTP_TREND",'\
'    "motors": "WTP_MOTORS",'\
'    "feedback": "WTP_FEEDBACK"'\
'  },'\
'  "api_port": 8787'\
'}' > /app/config/plant.json

ENV PYTHONUNBUFFERED=1
EXPOSE 8787

WORKDIR /app/server
CMD ["sh", "-c", "python -m uvicorn main:app --host 0.0.0.0 --port ${PORT:-8787}"]
