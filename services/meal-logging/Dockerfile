FROM python:3.14-slim

# Don't write .pyc files, print logs straight away (so `docker logs` shows them),
# and turn off pytest's cache (the app user isn't allowed to write to /srv)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTEST_ADDOPTS="-p no:cacheprovider"

WORKDIR /srv

# The version this image reports at /version (and the website footer shows). It's set when the
# image is built, e.g. docker build --build-arg APP_VERSION=1.1.0, so each image knows its own
# version. That's what makes a rolling update or rollback visible.
ARG APP_VERSION=dev
ENV APP_VERSION=${APP_VERSION}

# Install the libraries before copying the code. Docker caches this step,
# so changing the code doesn't mean reinstalling everything.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY tests ./tests

# Run as a normal user rather than root
RUN useradd --create-home --uid 10001 appuser
USER appuser

EXPOSE 8001

# Written this way (a JSON list), uvicorn is the container's main process and gets the stop
# signal directly. It then finishes any requests it's in the middle of (for up to 10 seconds)
# before exiting, so `docker stop` or Kubernetes deleting the pod doesn't cut anyone off.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001", "--timeout-graceful-shutdown", "10"]
