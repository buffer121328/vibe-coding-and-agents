# Dockerfile —— 镜像的“菜谱”：从零做出 forge-lite 的镜像（教程 11.15 Docker 小节）
# 构建：docker build -t forge-lite .
FROM python:3.12-slim

WORKDIR /app

# 先只拷依赖清单：这一层不变时，改代码重新构建不会重装依赖（层缓存的关键用法）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 再拷代码与种子文档（.dockerignore 已排除 runtime/ 与 .env，密钥绝不进镜像）
COPY forge_lite ./forge_lite
COPY scripts ./scripts
COPY data ./data

ENV PYTHONUNBUFFERED=1
EXPOSE 8800
CMD ["uvicorn", "forge_lite.web.app:app", "--host", "0.0.0.0", "--port", "8800"]
