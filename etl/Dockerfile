# A small image that just runs the data-loading scripts.
# The USDA CSV files aren't copied in. They're mounted from etl/data when it runs.
FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTEST_ADDOPTS="-p no:cacheprovider"

WORKDIR /etl

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY *.py *.csv ./
COPY tests ./tests

RUN useradd --create-home --uid 10001 appuser
USER appuser

ENTRYPOINT ["python", "load_usda.py"]
