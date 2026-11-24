# SOS Galápagos · © 2026 Universidad San Francisco de Quito (USFQ) · Autor: Julián Maya <jamaya@usfq.edu.ec>
# Licencia Apache 2.0 (ver LICENSE y NOTICE): puede reutilizarse dando crédito.
FROM python:3.12-slim
WORKDIR /app
COPY servidor.py /app/servidor.py
RUN useradd -r -u 10001 app && mkdir -p /datos && chown app /datos
USER app
ENV PYTHONUNBUFFERED=1 PORT=8080 COMENTARIOS_DB=/datos/comentarios.sqlite
EXPOSE 8080
CMD ["python", "/app/servidor.py"]
