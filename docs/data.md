# Data and scope

I chose transaction inquiry with confirmed review tickets and human-support
summaries because the supplied records support grounded payment facts and a
small workflow with testable outcomes.

## Supplied records

The organizer's dataset is synthetic. Its contact metadata labels 240,056 of
686,296 contacts as transaction-related: **34.98%**. This broad label informed
scope; it does not measure real-bank demand or the frequency of unrecognized
charges. [Contact audit aggregates](../evidence/local_contacts_summary.json)

Source-backed tests use a reproducible private subset of **50 validated
transactions**, with customer/product ownership and record constraints checked
before serving. I used a small cohort to keep joins, record evidence and scripted
journeys inspectable within the hackathon. It is not representative of the full
dataset. Historical snapshots do not establish live bank balances or policy.

Organizer records, source PDFs, credentials and private record bindings are not
distributed here. No separate source-data redistribution license was established.

## Why authored customer messages

A bounded transcript inventory reviewed seven daily partitions: **1,098 rows,
42 normalized full-text variants and two balance-request opening families**.
Every stored language tag was Spanish. The inventory found no transaction-inquiry,
review-ticket or human-request openings under the chosen intent rubric, and no
Portuguese examples in that subset.

The opening-family classification was not independently human-validated. Stored
language tags are not fluent review, and this subset cannot establish coverage
for every source transcript. Repeated templates and appended follow-ups do not
provide independent requests. [Inventory aggregates](../evidence/source_intent_inventory_summary.json)

I used authored Spanish and Portuguese requests to cover the selected workflow,
including short messages and intentional typos. Organizer guidance permitted
authored evaluation messages grounded in supplied transactions, with separately
labeled simulated safety/tool-failure scenarios, when justified. The missing
workflow and Portuguese coverage supplies that justification; it does not prove
benchmark quality or grant source redistribution rights.

The v2 TRAIN resource contains 144 authored examples. I reviewed Spanish wording
and intent labels, plus the Spanish workflow review material. Portuguese wording
has no fluent human review and remains a stated limitation. Generated requests
and simulated failures are not historical customer allegations or bank outcomes.

## Public fixtures and privacy

The public application uses separate fictional records: two USD purchases at
Demo Mercado Sol and Demo Cafe Luna. These are not source extracts. Search also
supports MXN, COP and ARS, but these currencies have no public fixture matches.
Amounts remain in their original currency; the application performs no conversion.

Hosted mode refuses private-cohort options. The repository excludes raw data,
source PDFs, credentials, local configuration, case databases and private
evaluation cases. Public evidence contains aggregates and commitments, not
customer text, transaction facts, credentials or session tokens.

The public identity is a fixed fictional account. Tickets remain inside the
prototype; they do not initiate a bank dispute, refund or real human contact.
