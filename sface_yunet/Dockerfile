FROM python:3.11-slim-bookworm
RUN pip install --no-cache-dir opencv-python-headless==4.14.0.94 numpy==2.4.6 paho-mqtt==2.1.0
WORKDIR /app
COPY download_models.py /app/download_models.py
COPY licenses /app/licenses
COPY CREDITS.md /app/CREDITS.md
RUN python /app/download_models.py /app/models
COPY server.py run.py review_store.py face_manager.py ha_bridge.py web_ui.py /app/
COPY web /app/web
CMD ["python", "-u", "/app/run.py"]
