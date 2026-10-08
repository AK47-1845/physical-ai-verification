FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=7860 HOME=/home/app
RUN useradd --create-home --uid 1000 app
WORKDIR /app
COPY backend/requirements-public.txt /app/backend/requirements-public.txt
RUN pip install --no-cache-dir -r backend/requirements-public.txt
COPY --chown=1000:1000 backend /app/backend
COPY --chown=1000:1000 packages /app/packages
RUN mkdir -p /app/var/public-demo && chown -R 1000:1000 /app/var
USER 1000
EXPOSE 7860
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.getenv('PORT','7860')+'/readyz',timeout=4)"
CMD ["sh", "-c", "exec uvicorn backend.public_app:create_public_app --factory --host 0.0.0.0 --port ${PORT:-7860} --workers 1 --no-proxy-headers --no-access-log"]