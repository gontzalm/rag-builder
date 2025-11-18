FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY --exclude=.venv --exclude=__pycache__ --exclude=.env . .

EXPOSE 8000

CMD ["python", "-m", "chainlit", "run", "main.py", "-h", "--host", "0.0.0.0"]
