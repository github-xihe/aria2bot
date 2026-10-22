# syntax=docker/dockerfile:1

# ---------- build stage ----------
FROM python:3.13-slim-trixie AS build

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_ROOT_USER_ACTION=ignore

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app
COPY requirements.txt .
RUN pip install --upgrade pip setuptools wheel \
 && pip install -r requirements.txt

# ---------- runtime stage ----------
FROM python:3.13-slim-trixie

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=Asia/Shanghai \
    PATH="/opt/venv/bin:$PATH"

# ffmpeg: 生成视频缩略图（util.imgCoverFromFile 调用）
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg ca-certificates tzdata \
 && rm -rf /var/lib/apt/lists/*

# 非 root 运行；如需匹配宿主机用户，构建时传 --build-arg APP_UID=$(id -u) APP_GID=$(id -g)
ARG APP_UID=1000
ARG APP_GID=1000
RUN groupadd -g "${APP_GID}" aria2bot \
 && useradd -u "${APP_UID}" -g "${APP_GID}" -m -s /usr/sbin/nologin aria2bot

COPY --from=build /opt/venv /opt/venv

WORKDIR /app
COPY --chown=aria2bot:aria2bot . .
RUN mkdir -p /app/db && chown -R aria2bot:aria2bot /app

USER aria2bot

CMD ["python", "-u", "app.py"]
