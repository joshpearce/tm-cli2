#!/usr/bin/env bash
# Drive a Claude Code session in tmux through a Java-web-app threat model.
#
# Iterative walkthrough: an engineer (these prompts) builds up the model
# with Claude one entity at a time, the way you would in a real session.
# See examples/demo-prompt-java-webapp.md for the reference model.
#
# All config, helpers, and lifecycle live in demo-lib.sh; this file is
# pure demo content. To author a different demo, copy this file, swap the
# DIAGRAM_DESCRIPTION and the prompts, and you're done.

set -euo pipefail

# Source the shared library (config defaults, helpers, demo_init/demo_done).
# shellcheck source=demo-lib.sh
source "$(dirname "$0")/demo-lib.sh"

# Per-demo overrides (optional). These must be set *before* demo_init.
DIAGRAM_DESCRIPTION="Modern Java web app threat model — built live via the tm CLI."

# This demo spells out every field in each prompt, so the standing rule is
# "do exactly what I said" — no inference, no clarifying questions, no
# editorializing. Avoid apostrophes — single-quoted on the command line.
SYSTEM_PROMPT='You are operating the `tm` CLI in a live threat-modeling session. The user will send one short prompt at a time, each one fully specifying the entity to create. Execute each prompt exactly as written: no clarifying questions, no alternative suggestions, no unsolicited commentary, no inferred fields the user did not name. The one transformation you must apply: entity names are lower-kebab-case, so render each --name value accordingly (e.g. the label "AWS Public Subnet" becomes the name aws-public-subnet) and reuse the same kebab name whenever a later prompt refers back to that entity. After every change to the model, push the diagram so the editor view stays in sync. Work entity-first; skip `tm document`.'

# Sanity-check, reset db, configure shell, launch Claude.
demo_init

# Phase 2 sets a standing rule ("after every change, push the diagram")
# so subsequent prompts can stay terse and Claude keeps the dfd_editor in
# sync without per-prompt reminders.

# Phase 1 — orient
ask "We're going to use the \`tm\` CLI to do some threat modeling together. Run \`tm agent-info\` and read its output — that's the agent orientation doc. Give me a one-paragraph summary, then wait."

# Phase 2 — kickoff. Behavior rules already live in the appended system
# prompt; the diagram is already set up by the script and the CLI's
# default-diagram fallback handles ids automatically.
ask "We're starting a web app design, piece by piece. Wait for the first one."

# Phase 3 — trust boundaries (one per prompt)
ask "First trust boundary: 'Internet', privilege internet. Untrusted public network — any client can originate traffic here."
ask "Next: 'AWS Public Subnet', dmz. Internet-facing edge of the VPC where TLS terminates and the ALB lives."
ask "'AWS Private Subnet', corporate. Application tier — runs ECS Fargate and the in-VPC cache."
ask "'AWS Data Tier', restricted. Network-isolated durable storage subnet, no direct internet egress."
ask "'AWS Managed Services', corporate. Regional AWS services (S3, SQS, SES, Cognito) reached over HTTPS with IAM auth."

# Phase 4 — ECS Cluster container
ask "Now a logical container 'ECS Cluster' inside the Private Subnet boundary — that's our Fargate cluster. The four Spring Boot services will live in it."

# Phase 5 — external entities (one per prompt)
ask "External entity: 'End User', entity-type user, in the Internet boundary. Customer browsing from a regular browser."
ask "External entity: 'Stripe', entity-type service, mark it out-of-scope, in the Internet boundary. Third-party payment processor."
ask "External entity: 'Amazon SES', entity-type service, in AWS Managed Services. Transactional email."

# Phase 6 — edge processes + Cognito (one per prompt)
ask "Process: 'CloudFront CDN', trust-level system, in the Public Subnet. Edge cache and TLS termination for static assets and API routes."
ask "Process: 'Application Load Balancer', trust-level system, in the Public Subnet. Routes to ECS services by host/path."
ask "Process: 'Amazon Cognito', trust-level admin, in AWS Managed Services. Our IdP — user pools and federated sign-in."

# Phase 7 — Spring Boot services in ECS Cluster (one per prompt)
ask "Process inside ECS Cluster: 'Spring Boot Web Frontend', trust-level authenticated. Serves the Vue SPA, proxies auth + API. Add an assumption that TLS terminates at the ALB so the ALB→Frontend hop is plaintext HTTP inside the VPC, and another that session cookies are HttpOnly+Secure+SameSite=Lax."
ask "Process inside ECS Cluster: 'Spring Boot REST API', trust-level authenticated. CRUD and business-logic endpoints. Assumption: every inbound request carries a JWT minted by the Auth Service. Assumption: outbound AWS calls use the task IAM role, not static keys."
ask "Process inside ECS Cluster: 'Auth Service', trust-level admin. Fronts Cognito, mints short-lived JWTs and runs password flows."
ask "Process inside ECS Cluster: 'Background Worker', trust-level authenticated. Polls SQS for async jobs (email, billing reconciliation)."

# Phase 8 — data stores (one per prompt)
ask "Data store: 'ElastiCache Redis', storage-type cache, no PII, encrypted at rest, in the Private Subnet. Session cache + rate-limit counters; volatile."
ask "Data store: 'RDS PostgreSQL', storage-type database, contains PII, encrypted at rest, in the Data Tier. Primary relational store: accounts, orders, audit trail."
ask "Data store: 'S3 User Uploads', storage-type bucket, contains PII, encrypted at rest, in the Data Tier. Customer-supplied files, versioned, KMS-encrypted."
ask "Data store: 'SQS Job Queue', storage-type queue, no PII, encrypted at rest, in AWS Managed Services. Async work handed off by the REST API."

# Phase 9 — data items, grouped by parent (one prompt per parent)
ask "Data items on End User: D1 'User Credentials' (secret) — username + plaintext password supplied at sign-in. D12 'Credit Card PAN' (secret) — raw PAN entered at checkout."
ask "Data items on Stripe: D13 'Stripe Payment Token' (secret) — opaque tokenized card reference. D14 'Stripe Charge Receipt' (secret) — charge id, last4, amount, status."
ask "Data item on Amazon SES: D25 'SES Send Receipt' (internal) — MessageId ack returned by SES."
ask "Data items on CloudFront CDN: D21 'Static Web Asset' (public) — SPA bundle, CSS, images. D26 'Rendered HTML Page' (public) — server-rendered HTML."
ask "Data item on Spring Boot Web Frontend: D5 'Session Cookie' (secret) — HttpOnly Secure SameSite=Lax cookie."
ask "Data items on Spring Boot REST API: D22 'API Request Payload' (internal) — JSON request body. D23 'API Response Payload' (internal) — JSON response body."
ask "Data items on Auth Service: D3 'Session JWT' (secret) — short-lived access token. D4 'Refresh Token' (secret) — long-lived refresh token."
ask "Data item on Amazon Cognito: D6 'Cognito ID Token' (secret) — OIDC ID token after a successful auth challenge."
ask "Data item on Background Worker: D20 'Transactional Email' (pii) — rendered receipt or notification email body."
ask "Data items on ElastiCache Redis: D17 'Rate Limit Counter' (internal) — per-IP per-route counter with TTL. D18 'Cached Session State' (secret) — serialized session blob keyed by session id."
ask "Data items on RDS PostgreSQL: D2 'Password Hash' (secret) — bcrypt hash. D7 'User Profile Record' (pii). D8 'Customer Email Address' (pii). D9 'Shipping Address' (pii). D10 'Order Record' (internal). D11 'Audit Log Entry' (internal) — append-only timestamped action log."
ask "Data items on S3 User Uploads: D15 'Profile Photo' (pii) — user-uploaded avatar. D16 'File Attachment' (secret) — customer document."
ask "Data items on SQS Job Queue: D19 'Async Job Message' (internal) — job type + payload + correlation id. D24 'SQS Send Receipt' (internal) — MessageId ack."

# Phase 10 — flows (one per prompt; each carries its payloads)
ask "Flow F1: End User ↔ CloudFront CDN, HTTPS/443, unauthenticated, encrypted. Payloads from End User: D1, D5, D12, D22. From CDN: D15, D26, D5, D17."
ask "F2: CloudFront ↔ ALB (origin fetch), HTTPS/443, unauthenticated, encrypted. From CDN: D22, D5. From ALB: D17, D26."
ask "F3: ALB ↔ Spring Boot Web Frontend (in-VPC), HTTP/80, unauthenticated, NOT encrypted. From ALB: D22, D5. From Web: D17, D26, D5."
ask "F4: Web Frontend ↔ Auth Service, HTTPS/443 (mTLS), unauthenticated, encrypted. From Web: D1, D5. From Auth: D3, D4, D5."
ask "F5: Auth Service ↔ Cognito (AdminInitiateAuth), HTTPS/443 (IAM), authenticated, encrypted. From Auth: D1. From Cognito: D6."
ask "F6: Auth Service ↔ RDS (user-account lookup), PostgreSQL/5432 (TLS), authenticated, encrypted. From Auth: D7, D2. From RDS: D7, D2, D8."
ask "F7: Web Frontend ↔ REST API (JWT-bearing), HTTPS/443 (mTLS), authenticated, encrypted. From Web: D22, D3. From API: D17."
ask "F8: REST API ↔ RDS (application query), PostgreSQL/5432 (TLS), authenticated, encrypted. From API: D22, D7, D9, D10, D11. From RDS: D7, D8, D9, D10, D11."
ask "F9: REST API ↔ ElastiCache Redis, Redis/6379 (TLS), authenticated, encrypted. From API: D12, D11. From Redis: D12, D11."
ask "F10: REST API ↔ S3 User Uploads, HTTPS/443 (S3 SigV4), authenticated, encrypted. From API: D15, D16. From S3: D15, D16."
ask "F11: REST API ↔ SQS Job Queue (enqueue), HTTPS/443 (SQS SendMessage), authenticated, encrypted. From API: D13. From SQS: D18."
ask "F12: REST API ↔ Stripe (charge), HTTPS/443, authenticated, encrypted. From API: D13, D14. From Stripe: D14."
ask "F13: Background Worker ↔ SQS Job Queue (poll), HTTPS/443 (SQS ReceiveMessage), authenticated, encrypted. From Worker: D13. From SQS: D13."
ask "F14: Background Worker ↔ Amazon SES, HTTPS/443 (SES SendEmail), authenticated, encrypted. From Worker: D14, D8. From SES: D19."

# Phase 11 — summary
ask "We're done. Print a one-line summary of how many nodes, containers, flows, and data items got created."

demo_done
