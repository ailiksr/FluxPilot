FROM python:3.11-alpine
LABEL org.opencontainers.image.source="https://github.com/ailiksr/FluxPilot"
LABEL org.opencontainers.image.description="Privacy-preserving image cache proxy for FluxPilot"
WORKDIR /app
RUN addgroup -S -g 981 rssai \
    && adduser -S -D -H -u 999 -G rssai rssai
COPY server.py .
RUN mkdir -p /cache \
    && chown -R 999:981 /app /cache
ENV PYTHONUNBUFFERED=1 CACHE_DIR=/cache PYTHONDONTWRITEBYTECODE=1
USER 999:981
EXPOSE 8080
CMD ["python3", "server.py"]
