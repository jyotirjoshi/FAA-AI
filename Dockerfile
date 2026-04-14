FROM python:3.12-slim

# HF Spaces requires non-root user with uid 1000
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH

WORKDIR $HOME/app

COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download the embedding model so the container doesn't need network access at runtime.
# This avoids HF Hub rate-limit (429) errors on cold starts.
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')"

COPY --chown=user . .

EXPOSE 7860

# PORT is set by Render at runtime; falls back to 7860 for HF Spaces.
CMD uvicorn src.api.main:app --host 0.0.0.0 --port ${PORT:-7860}
