# Stage 1: install Python dependencies (Debian slim ships prebuilt wheels for
# lxml/tiktoken/psycopg, so no gcc toolchain is needed — builds are fast and
# stable even on slow networks).
FROM python:3.11-slim-bookworm AS builder
WORKDIR /app
COPY requirements.txt ./
ARG PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple
RUN pip3 install --no-cache-dir --index-url="$PIP_INDEX_URL" --prefix="/deps" -r requirements.txt

# Stage 2: runtime image
FROM python:3.11-slim-bookworm
LABEL authors="serpicroon"
WORKDIR /app
RUN addgroup --system --gid 981 rssai \
    && adduser --system --no-create-home --uid 999 --ingroup rssai rssai
COPY --from=builder /deps /usr/local
COPY . .
RUN chown -R 999:981 /app
USER 999:981
CMD ["python3", "-u", "main.py"]
