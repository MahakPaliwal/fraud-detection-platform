FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .

# CPU-only torch first: much smaller than the default CUDA build
RUN pip install --no-cache-dir --default-timeout=100 --retries 10 torch --index-url https://download.pytorch.org/whl/cpu

# Everything else; torch is already satisfied, so the GPU build isn't pulled
RUN pip install --no-cache-dir --default-timeout=100 --retries 10 -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]