# Image du projet HMM-CAC40 : application Django + pipeline de calcul (HMM, bêtas, backtest)
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Compilateur au cas où une dépendance (hmmlearn, statsmodels) n'a pas de wheel pour cette version
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dépendances d'abord : l'installation reste en cache tant que requirements/ ne change pas
COPY requirements/ requirements/
RUN pip install -r requirements/base.txt -r requirements/dev.txt

COPY . .

# Fins de ligne Windows (CRLF) retirées du script de démarrage
RUN sed -i 's/\r$//' docker/entrypoint.sh && chmod +x docker/entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["docker/entrypoint.sh"]
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
