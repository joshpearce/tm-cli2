#!/usr/bin/env bash
# Quick tm-cli demo: a small authenticated web app with an edge load
# balancer and an in-VPC cache. Batched prompts — Claude fills in
# unspecified fields (privilege levels, trust levels, transports, ports,
# etc.) from the descriptions.

set -euo pipefail

# shellcheck source=demo-lib.sh
source "$(dirname "$0")/demo-lib.sh"

DIAGRAM_DESCRIPTION="Small authenticated web app threat model — built live via the tm CLI."

# Override the lib default: tell Claude up-front (in the appended system
# prompt, not in turn #1) that prompts will be batched and that it should
# infer the unspecified fields rather than ask. Avoid apostrophes — single-
# quoted on the command line.
SYSTEM_PROMPT='You are operating the `tm` CLI in a live threat-modeling session. The user will send short, often batched prompts. Execute each one directly: no clarifying questions, no alternative suggestions, no unsolicited commentary. Fill in sensible defaults from the descriptions — privilege levels, trust levels, transports, ports, payloads, and any other field you have to choose. Entity names must be lower-kebab-case, so convert the human-readable labels in each prompt accordingly (e.g. the boundary "AWS Public Subnet" becomes the name aws-public-subnet) and reuse the same kebab name when a later prompt refers back to that entity. After every change to the model, push the diagram so the editor view stays in sync. Work entity-first; skip `tm document`.'

demo_init

# Orient
ask "Run \`tm agent-info\` and summarize the output in one sentence."

# Boundaries + actor
ask "Create three trust boundaries: 'Internet' (untrusted public network), 'AWS Public Subnet' (Internet-facing edge of the VPC), and 'AWS Private Subnet' (the application and data tier). Add 'End User' as an external entity in the Internet boundary."

# Edge process
ask "In the AWS Public Subnet, add an 'Application Load Balancer' that terminates TLS and routes requests to backend services."

# Private-tier processes + stores
ask "Inside the AWS Private Subnet, add two processes — 'Web App' (serves the SPA and proxies API requests) and 'Auth Service' (issues session tokens) — plus two data stores: 'Redis' (session cache and rate-limit counters) and 'PostgreSQL' (user accounts and password hashes)."

# Data items
ask "Add data items where they belong: user credentials on End User, a session cookie on Web App, a cached session blob and a rate-limit counter on Redis, password hashes and user profile records on PostgreSQL."

# Flows. Flows themselves are undirected; direction is carried by payloads
# via --from <node_id>. Spell out "request and response payloads in both
# directions" so Claude attaches payloads on each endpoint, not just one.
ask "Add five flows between the following pairs, choosing appropriate transports and authentication, with request and response payloads attached in both directions: End User ↔ Application Load Balancer over the public Internet, Application Load Balancer ↔ Web App inside the VPC, Web App ↔ Auth Service inside the VPC, Web App ↔ Redis for session cache lookups, and Auth Service ↔ PostgreSQL for account lookups."

# Summary
ask "We're done. Print a one-line summary of how many nodes, containers, flows, and data items were created."

demo_done
