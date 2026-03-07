FROM python:3.12-slim

WORKDIR /app

RUN useradd -m botuser

COPY requirements.txt /app/
RUN python -m venv /app/venv && \
    /app/venv/bin/pip install --no-cache-dir -r requirements.txt

COPY . /app
RUN chown -R botuser:botuser /app

USER botuser

CMD ["/app/venv/bin/python", "-u", "ai-irc-bot.py"]
