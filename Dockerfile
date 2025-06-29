# Usa Python 3.10 come base
FROM python:3.10-slim

# Crea una directory per l'app
WORKDIR /app

# Copia i file del progetto
COPY . .

# Installa le dipendenze
RUN pip install --upgrade pip && pip install -r requirements.txt

# Esponi la porta 8080 richiesta da Render
EXPOSE 8080

# Comando di avvio
CMD ["python", "linkedin_game_bot_pubblicato.py"]
