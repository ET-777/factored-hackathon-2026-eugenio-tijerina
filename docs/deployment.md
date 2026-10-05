# Portable fictional demo and hosted contract

This package is a provider-neutral preparation artifact. It has not been deployed
or published. Docker's client was present during preparation, but its Linux engine
was unavailable; the container build and container runtime remain untested.

## Local development

From the private working checkout, Python 3.11 or later can run the fictional
loopback demo without a provider, model download, or experiment dependency:

```powershell
python -B -m bank_service web --port 8765
python -B -m bank_service demo --language es
python -B -m bank_service demo --language pt
```

Open `http://127.0.0.1:8765`. The keyword router is the default. Optional
`--router learned-preview` and `--router learned-preview-v2` use only the two
independently authored TRAIN JSON files. These are guarded experimental previews;
the current serving policy has no qualifying final evaluation. Spanish received
owner review; Portuguese was accepted by the owner without fluent review. Do not
present the preview as a qualified banking service or a multilingual benchmark win.

## Portable export

Create the package from the checkout before any build or transfer:

```powershell
python -B scripts/package_demo.py
# Or choose a new or empty directory explicitly:
python -B scripts/package_demo.py --output .local/deployment-package-owner-v1
```

The default is `.local/deployment-package-v1` relative to the checkout. An existing
nonempty destination is refused. Use a fresh directory for a later snapshot.
The exporter reads only a literal allowlist: the required runtime Python modules,
`pyproject.toml`, three web assets, two authored TRAIN files, `Dockerfile`,
`.dockerignore`, and this document. It rejects source/destination symbolic links,
Windows junctions and reparse points, and source hardlinks. It never traverses the
dataset, sealed evaluation, evidence, credentials, `.env`, PDF, Git content, or
cache directories. Git is queried only for the commit identifier.

`SHA256_MANIFEST.json` records the byte count and SHA256 of each exported file,
plus the source commit when available. It describes an allowlisted working-tree
snapshot; the commit alone does not prove the files were committed. The manifest
excludes itself. Identical source bytes and commit metadata give identical manifest
bytes; no timestamp, machine path, environment value, or Git remote is recorded.
Verify file hashes against this manifest after transfer, and retain it with the
exact package used for review.

## Container build and run

Build only from the clean exported directory. The Docker deny-all context admits
literal runtime paths; tests, evaluation and experiment code, source datasets,
documents other than this deployment note, and private artifacts are excluded.
Docker itself receives its Dockerfile and ignore rules separately.

```powershell
docker build -t factored-bank-demo:local .local/deployment-package-v1
```

The image uses the [official Python slim image](https://hub.docker.com/_/python),
installs the core package and `tzdata` for `America/Monterrey`, and runs as UID/GID
10001. Runtime state goes into a writable ephemeral directory. The image tag and
package index dependencies can change; the source export is reproducible, while
this initial Dockerfile does not claim a digest-pinned or offline-reproducible
image. Record the resulting image digest and resolved dependency versions once a
real build has passed. Docker documents its context filtering in
[Build context](https://docs.docker.com/build/concepts/context/).

Supply an exact public HTTPS origin and internal listening port through the
hosting platform's environment settings:

```text
PUBLIC_ORIGIN=https://demo.example.com
PORT=8080
```

The container starts `python -B -m bank_service web --hosted --host 0.0.0.0`.
`PUBLIC_ORIGIN` and `PORT` apply only in hosted mode. Missing or invalid required
configuration refuses startup. The platform forwards traffic to the configured
internal port; `EXPOSE 8080` is documentation and does not publish a port.
For explicit startup outside a container, the equivalent command is:

```text
python -B -m bank_service web --hosted --public-origin https://demo.example.com --host 0.0.0.0 --port 8080
```

Do not expose this HTTP listener directly to the public network. Before starting
public service, the selected platform must terminate HTTPS with a valid
certificate, redirect external HTTP to HTTPS, preserve the configured canonical
Host, and restrict the application listener to its trusted ingress. The app binds
authority to `PUBLIC_ORIGIN`; it never takes authority from `X-Forwarded-*` headers.
The container does not provide TLS or verify that platform settings are correct.
Its `/healthz` probe is stateless and creates no session. The container's local
probe uses the configured canonical Host; platform probes must preserve that Host.

## Public fixtures and session retention

Hosted mode accepts independently authored fictional demo records only. It
refuses the private cohort startup options, and the package contains no organizer
records. The fixed fictional identity is a demo fixture, not bank authentication.
Intake and human handoff remain simulations: no bank is modified, no external
ticket is created, and no human is contacted. Do not enter personal or financial
information into the public demo.

Sessions and their simulated case databases are ephemeral. Session authorization
expires after 20 minutes, a process is limited to 20 live sessions, and session
creation is capped at 100 minted sessions per minute. The browser cookie lasts for
the browser session, while server authorization expires after 20 minutes; hosted
cookies use `Secure`, `HttpOnly`, and `SameSite=Strict`. Restart or container replacement
loses session state. Do not mount a persistent volume for this demo. The app bounds
session memory and local temporary storage; host access logs, request retention,
and rate limiting at the ingress are platform settings the owner must inspect.
Run a single process/replica for this bounded demo because sessions are process
local; there is no shared session store or production authentication service.

## Proposed Render Free settings

Render Free is the proposed host for this fictional prototype. This is a setup
proposal, not authorization to create an account, upload a repository, connect an
app, or deploy. Use a separate private release repository containing only the
reviewed export and its manifest. Connecting the full research checkout would
give the provider access beyond the exported Docker context. The owner should
authorize the Git connection for that release repository only; Render supports
deploying private repositories through a linked Git provider.
[Render Git provider connection](https://render.com/docs/git-provider),
[Render web services](https://render.com/docs/web-services).

After that exact upload and deployment are authorized, select New > Web Service
and the private release repository. Configure:

| Setting | Value |
| --- | --- |
| Source | Owner-approved private release repository and exact branch/commit |
| Name and region | Owner-selected service name and region |
| Language | Docker |
| Root/build context | Release repository root (`.`) |
| Dockerfile Path | `./Dockerfile` |
| Docker Command | Leave blank to use the supplied hosted `CMD` |
| Instance type | Free, one instance |
| `PORT` | `8080` |
| `PUBLIC_ORIGIN` | Literal `https://` plus the actual assigned `onrender.com` hostname |
| Health Check Path | `/healthz` |
| Auto-Deploy | Off; review and deploy each specific release manually |
| Disk, data services and service secrets | None needed for this fictional demo |

Render builds Docker services from the selected Dockerfile and uses its `CMD`
when Docker Command is blank. The service reads `PORT` and binds to `0.0.0.0`.
The first Create Web Service action starts a build and deployment, even when later
automatic deploys are disabled; treat that action as the deployment approval gate.
[Docker on Render](https://render.com/docs/docker),
[Render deployment controls](https://render.com/docs/deploys).

Set `PUBLIC_ORIGIN` to the actual service URL shown by Render before serving the
app, without a trailing slash. An illustrative value such as
`https://owner-approved-service.onrender.com` must be replaced by the assigned
hostname; do not guess it or place a literal environment-variable expression in
the field. Render also exposes the assigned hostname and URL as
`RENDER_EXTERNAL_HOSTNAME` and `RENDER_EXTERNAL_URL`, but this app deliberately
requires explicit `PUBLIC_ORIGIN` configuration.
[Render environment variables](https://render.com/docs/environment-variables).

For this initial setup, keep the assigned `onrender.com` URL as the sole canonical
origin and configure no custom domain. Render health checks send that hostname as
`Host` when no custom domain is verified; with verified custom domains, Render can
choose one of those domains instead. This app supports one canonical authority,
so an alternate hostname would fail its checks and browser Origin policy. A
domain change requires a reviewed configuration and verification pass.
[Render health checks](https://render.com/docs/health-checks).

Render's load balancer terminates HTTPS and redirects external HTTP to HTTPS;
its internal HTTP port is not directly public. Verify that behavior against the
actual deployment and that the canonical Host reaches the app unchanged.
[Render web service networking](https://render.com/docs/web-services#connecting-from-the-public-internet).

Free instances sleep after 15 idle minutes and take about a minute to resume.
Local SQLite and other filesystem changes disappear on spin-down, restart or
redeployment. Free instance hours are shared within the workspace. With no payment
method, exhausting included bandwidth suspends free services; exhausting included
build minutes disables new builds. With a payment method, supplementary bandwidth
and build usage can be billed. Do not add a payment method or upgrade under this
proposal. The owner must inspect current account usage and accept cold starts and
lost sessions before giving judges the URL.
[Render Free limits](https://render.com/docs/free).

## Manual judge access gate

No public URL or judge access is claimed by this preparation artifact. The owner
must select and authorize the platform, account, cost limit and exact public
origin before deployment or publication. After an authorized deployment, manually
verify HTTPS, canonical Host/Origin enforcement, cookie security, Spanish and
Portuguese fictional inquiries, clarification, consented simulated intake and
handoff, private-mode refusal, session expiry/capacity, stateless health checks,
and restart behavior. Inspect platform logs/retention and the exported allowlist.
Only then record the actual URL, image/package digest and observed checks in the
submission, and explicitly approve making that exact deployment available to
judges. A local package, passing unit test, or available Docker client is not proof
of deployment, judge access, TLS configuration, or a qualified final evaluation.
