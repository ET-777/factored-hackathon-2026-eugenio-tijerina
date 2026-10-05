# Deployment

[Live application](https://factored-bank-demo.onrender.com/)

The submission repository is
[factored-hackathon-2026-eugenio-tijerina](https://github.com/ET-777/factored-hackathon-2026-eugenio-tijerina).
The existing Render service uses a separate runtime repository,
[ET-777/factored-bank-demo](https://github.com/ET-777/factored-bank-demo).
Renaming or updating the submission repository does not deploy application changes.

## Local development

```powershell
python -m pip install -e .
python -B -m bank_service web --port 8765 --router learned-preview-v2
```

Open `http://127.0.0.1:8765/`. Local mode binds to loopback. The explicit router
option selects the deployed model candidate; the CLI default is keyword routing.

## Docker and hosted configuration

```powershell
docker build -t transaction-support:local .
```

The image installs the core Python package and timezone data, runs as a non-root
user, and starts hosted mode with `learned-preview-v2`. Its health probe uses
`/healthz`. Tests, aggregate reports and private artifacts are outside the runtime
image. No model-provider secret or additional data service is required.

Required hosting settings:

| Setting | Value |
| --- | --- |
| Runtime | Docker |
| Dockerfile | `./Dockerfile` |
| Docker command override | Empty; use the image command |
| `PUBLIC_ORIGIN` | Exact canonical HTTPS origin, without a trailing slash |
| `PORT` | `8080`, or the platform's valid listening port |
| Health check | `/healthz` |
| Processes / replicas | One |
| Persistent disk | None for this fictional demo |

For the existing service, `PUBLIC_ORIGIN` is
`https://factored-bank-demo.onrender.com`. A new service must use its actual
assigned hostname. Missing or invalid origin/port configuration refuses startup.

The equivalent non-container command, behind a trusted HTTPS ingress, is:

```text
python -B -m bank_service web --hosted --host 0.0.0.0 --port 8080 --public-origin https://your-service.onrender.com --router learned-preview-v2
```

The hosting platform must terminate HTTPS, preserve the canonical Host and keep
the internal HTTP listener behind its ingress. The application uses the configured
origin rather than trusting forwarded headers. It does not provide TLS itself.
Hosted mode serves only fictional fixtures and refuses private-cohort identity
or permission overrides.

## Sessions and retention

Sessions and their SQLite ticket stores are temporary. Authorization expires
after 20 minutes; the process admits at most 20 live sessions and 100 new
sessions per minute. Hosted cookies are Secure, HttpOnly and SameSite=Strict.
Restart, replacement or spin-down loses session state. There is no shared
session store or production login service.

The free Render instance can sleep while idle. Allow time for it to wake before
recording or presenting, and expect existing sessions and tickets to be lost
after restart. Hosting logs, account quotas and ingress controls are separate
platform responsibilities. Do not enter personal or financial information.

## Verified release

On October 5, Render showed commit
`21cf0c7f4ecc08ca7dbbc14e2ef336447d0d7b05` live with guarded v2. The bounded
HTTPS verification passed **22 technical check groups over 43 requests** across
two isolated fictional Spanish/Portuguese sessions. It checked inquiry, record
selection, consent, confirmation, verified receipts, repeated confirmation,
handoff context and repaired report/PIN/scheduling boundaries.

[Unchanged verification report](../evidence/hosted_demo_verification_v2.json)

These are technical smoke checks, not model scores or fluent Portuguese review.
They did not inject all eight local safety scenarios or test hosted expiry,
restart, capacity, platform log retention or access from a judge's device.
The exact mixed-language browser sequence for filming was not verified by this
HTTP run. Application test instructions and evaluation limits are in the
[README](../README.md) and [evaluation report](model-and-evaluation.md).
