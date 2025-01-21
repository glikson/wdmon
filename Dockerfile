FROM python:3.9-slim
RUN pip install kubernetes flask waitress
RUN apt-get update && apt-get install -y curl procps && rm -rf /var/lib/apt/lists/*
COPY wdmon.py /app/wdmon.py
COPY templates /app/templates
WORKDIR /app
ENV PYTHONUNBUFFERED=1
CMD ["python", "-u", "wdmon.py"]