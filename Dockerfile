FROM python:3.12-slim

# HF Spaces requires non-root user with uid 1000
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH

WORKDIR $HOME/app

COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download the embedding model during build so no network call is needed at runtime.
# HF_TOKEN is declared as a build ARG so HF Spaces automatically passes the Space secret,
# authenticating the download and avoiding 429 rate-limit errors from the builder IP.
ARG HF_TOKEN=""
RUN HF_TOKEN=$HF_TOKEN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')"

COPY --chown=user . .

EXPOSE 7860

# PORT is set by Render at runtime; falls back to 7860 for HF Spaces.
CMD uvicorn src.api.main:app --host 0.0.0.0 --port ${PORT:-7860}
