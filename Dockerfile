# Récepteur webhook Pomofocus — image légère (Flask seul, sans pandas/matplotlib).
FROM python:3.12-slim

WORKDIR /app

# Fuseau horaire : les heures du CSV (datetime.fromtimestamp = heure locale)
# doivent correspondre aux exports Pomofocus (Europe/Paris), pas à l'UTC du conteneur.
ENV TZ=Europe/Paris
RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-webhook.txt .
RUN pip install --no-cache-dir -r requirements-webhook.txt

# Seuls les fichiers nécessaires au récepteur.
COPY webhook_receiver.py config.py config.yml projects-config.yml ./

EXPOSE 5000

# gunicorn sert le même objet `app` : le bloc `app.run(debug=True)` n'est jamais exécuté.
# -w 1 : un seul worker, car le récepteur écrit dans les fichiers sans verrou.
CMD ["gunicorn", "-w", "1", "-b", "0.0.0.0:5000", "webhook_receiver:app"]
