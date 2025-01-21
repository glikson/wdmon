
FROM python:3.9-slim
RUN pip install kubernetes
COPY wdmon.py /app/wdmon.py
CMD ["python", "/app/wdmon.py"]