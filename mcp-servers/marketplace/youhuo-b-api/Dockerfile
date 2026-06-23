# 构建上下文：mcp-servers/ 根目录
# docker build -f marketplace/youhuo-b-api/Dockerfile -t youhuo-b-api-mcp:1.0.0 .

FROM node:20-alpine

LABEL org.opencontainers.image.title="youhuo-b-api-mcp" \
      org.opencontainers.image.version="1.0.0" \
      org.opencontainers.image.description="有活 B 端招工 MCP Server (Hosted)"

RUN apk add --no-cache python3 py3-pip curl \
    && ln -sf python3 /usr/bin/python \
    && ln -sf pip3 /usr/bin/pip

WORKDIR /app

COPY marketplace/youhuo-b-api/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

RUN npm install -g @cloudbase/mcp-transformer@1.0.0-beta.18

COPY shared_token_store.py /app/
COPY tools/ /app/tools/
COPY youhuo-b-api/ /app/youhuo-b-api/

# 生产网关由云托管 YOUHUO_BASE_URL 注入，勿在镜像内写 sops-test 默认值
ENV PYTHONUNBUFFERED=1

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -f http://127.0.0.1:80/ || exit 1

CMD ["npx", "@cloudbase/mcp-transformer", "stdio-to-http", \
     "--stdio", "python /app/youhuo-b-api/server.py", \
     "--port", "80", "--host", "0.0.0.0"]
