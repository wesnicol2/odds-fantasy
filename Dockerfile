FROM node:22-bookworm-slim AS frontend-build

WORKDIR /frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN rm -rf ui && mkdir -p ui data
COPY --from=frontend-build /frontend/dist/ ./ui/

# Which commit this image is. .dockerignore excludes .git, so a running
# container has no repository to interrogate. Default values keep plain local
# builds honest while CI bakes traceable build metadata into deployed images.
ARG GIT_COMMIT=unknown
ARG GIT_BRANCH=""
ARG IMAGE_TAG=""
ARG BUILT_AT=""
ENV APP_COMMIT=$GIT_COMMIT \
    APP_BRANCH=$GIT_BRANCH \
    APP_IMAGE_TAG=$IMAGE_TAG \
    APP_BUILT_AT=$BUILT_AT

EXPOSE 8000

CMD ["python", "-m", "oddsfantasy.api", "--host", "0.0.0.0", "--port", "8000"]
