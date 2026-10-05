# Transaction Support Assistant

**Eugenio Tijerina · Factored AI & Data Hackathon 2026**

[Live application](https://factored-bank-demo.onrender.com/) · [Submission repository](https://github.com/ET-777/factored-hackathon-2026-eugenio-tijerina)

A Spanish and Portuguese assistant for finding a recorded payment, checking its
facts, and preparing a review ticket or a summary for human support. The customer
chooses the transaction, reviews the draft, and confirms before anything is saved.
The receipt confirms that the ticket was stored and checked; it is not a refund.

The public application uses fictional transactions. No money moves, no bank is
contacted, and no real support team receives the tickets. Do not enter personal
or financial information.

## Run locally

Python 3.11 or later:

```powershell
python -m pip install -e .
python -B -m bank_service web --port 8765 --router learned-preview-v2
```

Open **http://127.0.0.1:8765/**. Stop the server with Ctrl+C. Without an explicit
router option, `web` uses the keyword baseline. The Docker image selects v2.

To run the scripted fictional workflows or the application tests:

```powershell
python -B -m bank_service demo --language es
python -B -m bank_service demo --language pt
python -B -m unittest discover -s tests -q
```

The selected model trains locally from the included 144 authored examples.
It requires no model download, API key, paid inference or external model call.

## How it works

- Search by date, or amount and currency, then choose a matching record.
- Read grounded merchant, amount, status and date information.
- Agree to prepare a review request; inspect and explicitly confirm its draft.
- Ask for human support and supply the issue. The summary preserves relevant
  facts, completed steps and any earlier verified ticket.

Search supports MXN, COP, ARS and USD without conversion. The public fixtures
contain USD only. Dates accept day-first numeric formats, ISO dates and Spanish
or Portuguese month names; an omitted year uses the current year in Monterrey.

Service code enforces ownership, permissions, session expiry, confirmation and
verified saving. A model prediction cannot grant access or save a ticket.

## Results and limits

The repaired workflow completed **15/16 service journeys per language** and
passed **8/8 specified safety scenarios per language**. These are reused-case
regression results under corrected scoring, not model accuracy or a new unseen
evaluation. The original frozen evaluation failed. Portuguese wording has no
fluent human review, and the demo identity is not production authentication.
See the [model and evaluation report](docs/model-and-evaluation.md) for both
scoring views, original results and remaining limitations.

## Documentation

- [Architecture](docs/architecture.md): workflow, controls and module map.
- [Model and evaluation](docs/model-and-evaluation.md): model choice, comparisons,
  service results and safety scenarios.
- [Data](docs/data.md): source audit, authored inputs and public fixtures.
- [Deployment](docs/deployment.md): Docker, Render and session retention.

`bank_service/` contains the application, browser assets and training resources;
`tests/` contains synthetic application tests; `evidence/` contains unchanged
aggregate reports. Organizer records, credentials, PDFs and private evaluation
cases are excluded.
