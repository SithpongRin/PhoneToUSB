# Multi-stage production Dockerfile for PhoneToUSB Coordination Backend
FROM python:3.13-slim as builder

WORKDIR /build

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

FROM python:3.13-slim

WORKDIR /app

# Non-root user for security
RUN groupadd -g 1001 phonetousb && \
    useradd -u 1001 -g phonetousb -s /bin/sh phonetousb

COPY --from=builder /root/.local /home/phonetousb/.local
COPY app /app/backend/app

ENV PATH=/home/phonetousb/.local/bin:$PATH
ENV PYTHONPATH=/app

USER phonetousb

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
