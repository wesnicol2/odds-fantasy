FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN mkdir -p data

# Which commit this image is. .dockerignore excludes .git, so a running
# container has no repository to interrogate -- if it isn't baked in here, the
# footer in the UI can't tell you what is deployed. Kept last so a new commit
# only invalidates this layer, and defaulted so a plain `docker build` still
# works (it just reports "unknown", which is the honest answer for a build that
# didn't say).
ARG GIT_COMMIT=unknown
ARG GIT_BRANCH=""
ARG IMAGE_TAG=""
ARG BUILT_AT=""
ENV APP_COMMIT=$GIT_COMMIT     APP_BRANCH=$GIT_BRANCH     APP_IMAGE_TAG=$IMAGE_TAG     APP_BUILT_AT=$BUILT_AT

EXPOSE 8000

CMD ["python", "-m", "oddsfantasy.api", "--host", "0.0.0.0", "--port", "8000"]
