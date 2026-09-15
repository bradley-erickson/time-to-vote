# syntax=docker/dockerfile:1
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py utils.py ./
COPY templates/ templates/

RUN useradd --create-home --uid 1000 ttv && chown -R ttv:ttv /app
USER ttv

EXPOSE 8000

# No /healthz route exists in this app (unlike Almanac) — "/" always
# renders the home page with no auth, so it doubles fine as a liveness check.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/')" || exit 1

# README's own uvicorn.run(..., reload=True) is a dev convenience per its
# own note about the Pi deployment — invoking uvicorn directly here instead
# of `python main.py` sidesteps that flag rather than requiring an edit.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
