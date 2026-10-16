# The load test only needs Python itself (it uses the standard library), so this is tiny
FROM python:3.14-slim
ENV PYTHONUNBUFFERED=1
WORKDIR /loadtest
COPY loadtest.py .
RUN useradd --create-home --uid 10001 appuser
USER appuser
ENTRYPOINT ["python", "loadtest.py"]
