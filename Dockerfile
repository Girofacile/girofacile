FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY static ./static

EXPOSE 8000

# DATABASE_URL, APP_SECRET e credenziali devono essere fornite dall'ambiente.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
RUN echo '#tab-activity,[data-tab=activity]{display:none!important}body:not(.sector-transfer-v54) [data-mobile-tab=activity]{display:none!important}body:not(.sector-transfer-v54) .gf-mobile-bottom-nav-v62{grid-template-columns:repeat(4,1fr)!important}' >> static/dashboard/style.css
