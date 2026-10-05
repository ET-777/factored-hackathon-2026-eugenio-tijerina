FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080 \
    TMPDIR=/run/bank-demo

WORKDIR /opt/build
COPY pyproject.toml ./
COPY bank_service/ ./bank_service/

# tzdata supplies the America/Monterrey calendar on minimal Linux images.
# Install the application and timezone data.
RUN python -m pip install --no-cache-dir . tzdata \
    && groupadd --gid 10001 bankdemo \
    && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin bankdemo \
    && mkdir -p /run/bank-demo \
    && chown 10001:10001 /run/bank-demo \
    && rm -rf /opt/build

WORKDIR /run/bank-demo
USER 10001:10001
EXPOSE 8080

# Stateless probe with the configured canonical Host; no forwarded authority.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -B -c 'import http.client, os, sys; from urllib.parse import urlsplit; c = http.client.HTTPConnection("127.0.0.1", int(os.environ["PORT"]), timeout=2); c.request("GET", "/healthz", headers={"Host": urlsplit(os.environ["PUBLIC_ORIGIN"]).netloc}); sys.exit(0 if c.getresponse().status == 200 else 1)'

# Hosted CLI reads PUBLIC_ORIGIN and PORT; a missing origin refuses startup.
CMD ["python", "-B", "-m", "bank_service", "web", "--hosted", "--host", "0.0.0.0", "--router", "learned-preview-v2"]
