FROM python:3.9-slim
RUN apt-get update && apt-get install -y ffmpeg rubberband-cli && rm -rf /var/lib/apt/lists/*
WORKDIR /code
COPY ./requirements.txt /code/requirements.txt
RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt
COPY . .
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860"]