# syntax=docker/dockerfile:1

# ---------- build stage ----------
FROM python:3.13-alpine AS build

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_NO_COMPILE=1 \
    PIP_ROOT_USER_ACTION=ignore

# 个别依赖没有 musl 轮子时在构建阶段编译；运行镜像不含工具链
RUN apk add --no-cache build-base libffi-dev

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app
COPY requirements.txt .
RUN pip install --upgrade pip setuptools wheel \
 && pip install -r requirements.txt \
 && rm -rf /opt/venv/lib/python3.13/site-packages/pip* \
           /opt/venv/lib/python3.13/site-packages/setuptools* \
           /opt/venv/lib/python3.13/site-packages/wheel* \
           /opt/venv/lib/python3.13/site-packages/_distutils_hack \
 && rm -f /opt/venv/lib/python3.13/site-packages/distutils-precedence.pth \
 && find /opt/venv -name '*.pyc' -delete

# ---------- runtime stage ----------
FROM python:3.13-alpine

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=Asia/Shanghai \
    PATH="/opt/venv/bin:$PATH"

# 不安装 ffmpeg：mp4 上传时若无 ffmpeg 会自动降级为无缩略图发送
RUN apk add --no-cache ca-certificates tzdata

# 非 root 运行；如需匹配宿主机用户，构建时传 --build-arg APP_UID=$(id -u) APP_GID=$(id -g)
ARG APP_UID=1000
ARG APP_GID=1000
RUN addgroup -g "${APP_GID}" aria2bot \
 && adduser -u "${APP_UID}" -G aria2bot -D -H -s /sbin/nologin aria2bot

# venv 已在构建阶段裁剪（pip/setuptools/wheel/.pyc），此处只拷贝干净产物
COPY --from=build /opt/venv /opt/venv

WORKDIR /app
COPY --chown=aria2bot:aria2bot . .
RUN mkdir -p /app/db && chown -R aria2bot:aria2bot /app

USER aria2bot

CMD ["python", "-u", "app.py"]
