# Demo prompt: live-build a Java web app DFD via the tm CLI, then render via dfd_editor's HTTP API

Paste the **Prompt** section into a Claude Code session that has the `tm`
CLI on `PATH`, `jq` and `curl` installed, and a running `dfd_editor` server
reachable at `$DFD_EDITOR_URL`.
The agent builds the same modern-Java-web-app DFD as
[`dfd_editor/server/examples/demo-prompt-java-webapp.md`](../../dfd_editor/server/examples/demo-prompt-java-webapp.md),
but uses the relational `tm` CLI to construct the model. The diagram is
pushed to `dfd_editor` once up front (so it can be opened in the editor),
then re-pushed after every build step so the editor renders the model
progressively as the agent works.

This version is the **CLI equivalent** of the MCP demo:

| MCP tool                              | tm CLI equivalent                                          |
| ------------------------------------- | ---------------------------------------------------------- |
| `mcp__dfd-editor__create_diagram`     | `tm diagram create` + `tm diagram push` (combined)         |
| `mcp__dfd-editor__add_node`           | `tm node create process|external-entity|data-store`        |
| `mcp__dfd-editor__add_container`      | `tm container create trust-boundary|container`             |
| `mcp__dfd-editor__add_data_item`      | `tm data-item create --parent-node-id ...`                 |
| `mcp__dfd-editor__add_flow`           | `tm flow create` + `tm flow add-payload` (per ref)         |
| Container `children: [...]` array     | `tm node set-parent` / `tm container set-parent`           |
| `mcp__dfd-editor__display_diagram`    | `curl -X POST $DFD_EDITOR_URL/api/agent/diagrams/<REMOTE_ID>/display` (once, after the initial push) |

Because tm-cli is **relational** (integer ids per row, container membership
via a junction table, payload directionality via a `source_endpoint`
column), this prompt is more imperative than the MCP version. After each
build step, `tm diagram push --server $DFD_EDITOR_URL` walks the four
entity tables and the membership graph, derives stable UUIDv5s for every
element, and POSTs the resulting `Diagram` document to the dfd_editor
agent API. The first push creates the document remotely; every later push
is a `PUT` that broadcasts `diagram-updated` over the editor's websocket,
so a browser already viewing the diagram re-renders live. Element UUIDs
are deterministic, so dfd_editor-side layout survives every re-push.

### How the agent should run this prompt

This prompt is written for an agent that runs each Bash command as an
independent shell invocation. Shell variables **do not survive between
Bash tool calls**. So instead of capturing ids into shell variables, every
`tm --id-only … create` command is shown standalone, and a comment above
it (e.g. `# remember as EE_USER`) tells you what label to record the
returned integer under. Later commands reference those labels as
`<EE_USER>`, `<P_CDN>`, etc. — replace each placeholder with the bare
integer you remembered before running the command.

The same applies to two pieces of global state:

- `<D>` — the diagram id printed by `tm diagram create` in Step 1. Every
  `tm` command in the rest of the prompt must be prefixed with
  `TM_DIAGRAM_ID=<D>` so it targets the right diagram (`TM_DIAGRAM_ID` is
  an env var, not a flag, and it does not survive between Bash calls
  either).
- `<REMOTE_ID>` — the dfd_editor-side UUID printed by the first
  `tm diagram push` in Step 1. Used once in the `display` call, then not
  again (subsequent pushes look it up locally).

The `<DFD_EDITOR_URL>` placeholder is whatever URL your `dfd_editor`
server is listening on (defaults to `http://localhost:5050`). Substitute
the literal URL.

---

## Prompt

> Execute the steps below **in order** as Bash tool calls. Do not ask for
> confirmation. After every `tm --id-only … create` command, read the
> integer printed on stdout and remember it under the label given in the
> `# remember as …` comment. Substitute those labels (and `<D>`,
> `<REMOTE_ID>`, `<DFD_EDITOR_URL>`) into later commands as bare integers
> / strings before running them. Do **not** change descriptions,
> classifications, or property values — they're the threat-model fixtures
> the source dfd_editor demo uses.
>
> ### Setup
>
> Pick a fresh 6-digit suffix `<N>` for the diagram name (so demo runs
> don't collide) and verify the prerequisites:
>
> ```bash
> command -v tm   >/dev/null || { echo "tm CLI not on PATH"; exit 1; }
> command -v jq   >/dev/null || { echo "jq not on PATH"; exit 1; }
> command -v curl >/dev/null || { echo "curl not on PATH"; exit 1; }
> curl -fsS <DFD_EDITOR_URL>/api/agent/diagrams >/dev/null \
>   && echo "dfd_editor: reachable"
> ```
>
> Remember the `<DFD_EDITOR_URL>` you used (default
> `http://localhost:5050`) and the `<N>` you picked.
>
> ### Step 1 — create the diagram, push it, and open it in the editor
>
> Create the local diagram, push it once so dfd_editor mints a UUID, then
> `POST /display` so any open editor tab switches to it. Every later push
> will broadcast `diagram-updated` and the editor will re-render in place.
>
> Substitute `<N>` (your chosen suffix) into the create command, and read
> the integer it prints. **Remember it as `<D>`**:
>
> ```bash
> tm --id-only diagram create \
>   --name "Java Web App on AWS #<N>" \
>   --author "tm-cli demo" \
>   --description "Modern Java (Spring Boot on ECS Fargate) web app on AWS — built via the tm CLI."
> ```
>
> Push the (currently empty) diagram and read `remote_id` from the JSON
> result. **Remember it as `<REMOTE_ID>`**:
>
> ```bash
> TM_DIAGRAM_ID=<D> tm diagram push --server <DFD_EDITOR_URL>
> ```
>
> Open the diagram in any connected editor tab:
>
> ```bash
> curl -fsS -X POST <DFD_EDITOR_URL>/api/agent/diagrams/<REMOTE_ID>/display
> ```
>
> ### Step 2 — external entities (EE_USER, EE_STRIPE, EE_SES)
>
> ```bash
> # remember as EE_USER
> TM_DIAGRAM_ID=<D> tm --id-only node create external-entity \
>   --name "End User" \
>   --description "Customer accessing the web app from a browser." \
>   --entity-type user
> ```
>
> ```bash
> # remember as EE_STRIPE
> TM_DIAGRAM_ID=<D> tm --id-only node create external-entity \
>   --name "Stripe" \
>   --description "Third-party payment processor." \
>   --entity-type service --out-of-scope
> ```
>
> ```bash
> # remember as EE_SES
> TM_DIAGRAM_ID=<D> tm --id-only node create external-entity \
>   --name "Amazon SES" \
>   --description "Transactional email sender for receipts and account notifications." \
>   --entity-type service
> ```
>
> Push so the editor renders the new external entities:
>
> ```bash
> TM_DIAGRAM_ID=<D> tm diagram push --server <DFD_EDITOR_URL> >/dev/null
> ```
>
> ### Step 3 — edge processes + Cognito (P_CDN, P_ALB, P_COGNITO)
>
> ```bash
> # remember as P_CDN
> TM_DIAGRAM_ID=<D> tm --id-only node create process \
>   --name "CloudFront CDN" \
>   --description "Edge cache and TLS termination for static assets and API routes." \
>   --trust-level system
> ```
>
> ```bash
> # remember as P_ALB
> TM_DIAGRAM_ID=<D> tm --id-only node create process \
>   --name "Application Load Balancer" \
>   --description "Public-facing ALB routing to ECS services by host/path rules." \
>   --trust-level system
> ```
>
> ```bash
> # remember as P_COGNITO
> TM_DIAGRAM_ID=<D> tm --id-only node create process \
>   --name "Amazon Cognito" \
>   --description "Managed identity provider for user pools and federated sign-in (in-scope)." \
>   --trust-level admin
> ```
>
> ```bash
> TM_DIAGRAM_ID=<D> tm diagram push --server <DFD_EDITOR_URL> >/dev/null
> ```
>
> ### Step 4 — Spring Boot ECS Fargate services (P_WEB, P_API, P_AUTH, P_WORKER)
>
> ```bash
> # remember as P_WEB
> TM_DIAGRAM_ID=<D> tm --id-only node create process \
>   --name "Spring Boot Web Frontend" \
>   --description "Spring Boot service on ECS Fargate — serves the Vue SPA, proxies auth and API calls." \
>   --trust-level authenticated \
>   --assumption "TLS terminates at the ALB; the ALB→Frontend hop is plaintext HTTP inside the VPC." \
>   --assumption "Session cookies are HttpOnly, Secure, SameSite=Lax."
> ```
>
> ```bash
> # remember as P_API
> TM_DIAGRAM_ID=<D> tm --id-only node create process \
>   --name "Spring Boot REST API" \
>   --description "Spring Boot service on ECS Fargate — CRUD and business-logic endpoints." \
>   --trust-level authenticated \
>   --assumption "Every inbound request carries a JWT minted by the Auth Service." \
>   --assumption "Outbound calls to AWS use the task IAM role, not static keys."
> ```
>
> ```bash
> # remember as P_AUTH
> TM_DIAGRAM_ID=<D> tm --id-only node create process \
>   --name "Auth Service" \
>   --description "Spring Boot service on ECS Fargate fronting Cognito — issues short-lived JWTs and runs password flows." \
>   --trust-level admin
> ```
>
> ```bash
> # remember as P_WORKER
> TM_DIAGRAM_ID=<D> tm --id-only node create process \
>   --name "Background Worker" \
>   --description "Spring Boot service on ECS Fargate polling SQS for async jobs (email, billing reconciliation)." \
>   --trust-level authenticated
> ```
>
> ```bash
> TM_DIAGRAM_ID=<D> tm diagram push --server <DFD_EDITOR_URL> >/dev/null
> ```
>
> ### Step 5 — data stores (DS_REDIS, DS_RDS, DS_S3, DS_SQS)
>
> ```bash
> # remember as DS_REDIS
> TM_DIAGRAM_ID=<D> tm --id-only node create data-store \
>   --name "ElastiCache Redis" \
>   --description "Session cache and rate-limit counters. Volatile; no long-lived PII." \
>   --storage-type cache --no-contains-pii --encryption-at-rest
> ```
>
> ```bash
> # remember as DS_RDS
> TM_DIAGRAM_ID=<D> tm --id-only node create data-store \
>   --name "RDS PostgreSQL" \
>   --description "Primary relational store: accounts, orders, audit trail." \
>   --storage-type database --contains-pii --encryption-at-rest
> ```
>
> ```bash
> # remember as DS_S3
> TM_DIAGRAM_ID=<D> tm --id-only node create data-store \
>   --name "S3 User Uploads" \
>   --description "Customer-supplied files (profile photos, attachments). Versioned, KMS-encrypted." \
>   --storage-type bucket --contains-pii --encryption-at-rest
> ```
>
> ```bash
> # remember as DS_SQS
> TM_DIAGRAM_ID=<D> tm --id-only node create data-store \
>   --name "SQS Job Queue" \
>   --description "Durable queue for async work handed off by the REST API." \
>   --storage-type queue --no-contains-pii --encryption-at-rest
> ```
>
> ```bash
> TM_DIAGRAM_ID=<D> tm diagram push --server <DFD_EDITOR_URL> >/dev/null
> ```
>
> ### Step 6 — trust boundaries + ECS Cluster container
>
> ```bash
> # remember as TB_INTERNET
> TM_DIAGRAM_ID=<D> tm --id-only container create trust-boundary \
>   --name "Internet" \
>   --description "Untrusted network reachable by any client." \
>   --privilege-level internet
> ```
>
> ```bash
> # remember as TB_PUBLIC_SUBNET
> TM_DIAGRAM_ID=<D> tm --id-only container create trust-boundary \
>   --name "AWS Public Subnet" \
>   --description "DMZ edge of the VPC; terminates TLS and fronts internal services." \
>   --privilege-level dmz
> ```
>
> ```bash
> # remember as TB_PRIVATE_SUBNET
> TM_DIAGRAM_ID=<D> tm --id-only container create trust-boundary \
>   --name "AWS Private Subnet" \
>   --description "Application tier: ECS cluster and in-VPC cache." \
>   --privilege-level corporate
> ```
>
> ```bash
> # remember as TB_DATA_TIER
> TM_DIAGRAM_ID=<D> tm --id-only container create trust-boundary \
>   --name "AWS Data Tier" \
>   --description "Durable storage. Network-restricted from the public subnet." \
>   --privilege-level restricted
> ```
>
> ```bash
> # remember as TB_MANAGED_SERVICES
> TM_DIAGRAM_ID=<D> tm --id-only container create trust-boundary \
>   --name "AWS Managed Services" \
>   --description "Regional AWS services reached over HTTPS with IAM auth." \
>   --privilege-level corporate
> ```
>
> ```bash
> # remember as CT_ECS
> TM_DIAGRAM_ID=<D> tm --id-only container create container \
>   --name "ECS Cluster" \
>   --description "Fargate cluster running the four Spring Boot services."
> ```
>
> ```bash
> TM_DIAGRAM_ID=<D> tm diagram push --server <DFD_EDITOR_URL> >/dev/null
> ```
>
> ### Step 7 — placement (translate the source's `children` arrays)
>
> The source MCP demo embeds child references inside each container; in
> tm-cli, membership is one command per child. Order: place containers
> before placing nodes inside them. These commands consume placeholders
> only — none of them mints a new id — so a single Bash call per command
> is fine. Substitute every `<…>` with the integer you remembered.
>
> ```bash
> # CT_ECS lives inside TB_PRIVATE_SUBNET.
> TM_DIAGRAM_ID=<D> tm container set-parent <CT_ECS> <TB_PRIVATE_SUBNET> >/dev/null
> # TB_INTERNET children: EE_USER, EE_STRIPE
> TM_DIAGRAM_ID=<D> tm node set-parent <EE_USER>   <TB_INTERNET> >/dev/null
> TM_DIAGRAM_ID=<D> tm node set-parent <EE_STRIPE> <TB_INTERNET> >/dev/null
> # TB_PUBLIC_SUBNET children: P_CDN, P_ALB
> TM_DIAGRAM_ID=<D> tm node set-parent <P_CDN> <TB_PUBLIC_SUBNET> >/dev/null
> TM_DIAGRAM_ID=<D> tm node set-parent <P_ALB> <TB_PUBLIC_SUBNET> >/dev/null
> # TB_PRIVATE_SUBNET children (in addition to CT_ECS already placed): DS_REDIS
> TM_DIAGRAM_ID=<D> tm node set-parent <DS_REDIS> <TB_PRIVATE_SUBNET> >/dev/null
> # TB_DATA_TIER children: DS_RDS, DS_S3
> TM_DIAGRAM_ID=<D> tm node set-parent <DS_RDS> <TB_DATA_TIER> >/dev/null
> TM_DIAGRAM_ID=<D> tm node set-parent <DS_S3>  <TB_DATA_TIER> >/dev/null
> # TB_MANAGED_SERVICES children: P_COGNITO, EE_SES, DS_SQS
> TM_DIAGRAM_ID=<D> tm node set-parent <P_COGNITO> <TB_MANAGED_SERVICES> >/dev/null
> TM_DIAGRAM_ID=<D> tm node set-parent <EE_SES>    <TB_MANAGED_SERVICES> >/dev/null
> TM_DIAGRAM_ID=<D> tm node set-parent <DS_SQS>    <TB_MANAGED_SERVICES> >/dev/null
> # CT_ECS children: P_WEB, P_API, P_AUTH, P_WORKER
> TM_DIAGRAM_ID=<D> tm node set-parent <P_WEB>    <CT_ECS> >/dev/null
> TM_DIAGRAM_ID=<D> tm node set-parent <P_API>    <CT_ECS> >/dev/null
> TM_DIAGRAM_ID=<D> tm node set-parent <P_AUTH>   <CT_ECS> >/dev/null
> TM_DIAGRAM_ID=<D> tm node set-parent <P_WORKER> <CT_ECS> >/dev/null
> ```
>
> ```bash
> TM_DIAGRAM_ID=<D> tm diagram push --server <DFD_EDITOR_URL> >/dev/null
> ```
>
> ### Step 8 — data items (D1–D26)
>
> Each data item attaches to one node via `--parent-node-id <NODE>`. The
> parents map (source GUID prefix → label you remembered):
>
> | Item | Parent label |
> | ---- | ---- |
> | D1, D12 | EE_USER |
> | D13, D14 | EE_STRIPE |
> | D25 | EE_SES |
> | D21, D26 | P_CDN |
> | D5 | P_WEB |
> | D22, D23 | P_API |
> | D3, D4 | P_AUTH |
> | D20 | P_WORKER |
> | D6 | P_COGNITO |
> | D17, D18 | DS_REDIS |
> | D2, D7, D8, D9, D10, D11 | DS_RDS |
> | D15, D16 | DS_S3 |
> | D19, D24 | DS_SQS |
>
> Run each command, remember the printed integer under the label `D1`,
> `D2`, … `D26`:
>
> ```bash
> # remember as D1
> TM_DIAGRAM_ID=<D> tm --id-only data-item create \
>   --identifier "D1" --classification "secret" --parent-node-id <EE_USER> \
>   --name "User Credentials" \
>   --description "Username and plaintext password supplied during sign-in."
> ```
>
> ```bash
> # remember as D2
> TM_DIAGRAM_ID=<D> tm --id-only data-item create \
>   --identifier "D2" --classification "secret" --parent-node-id <DS_RDS> \
>   --name "Password Hash" \
>   --description "bcrypt hash of the user's password stored in the accounts table."
> ```
>
> ```bash
> # remember as D3
> TM_DIAGRAM_ID=<D> tm --id-only data-item create \
>   --identifier "D3" --classification "secret" --parent-node-id <P_AUTH> \
>   --name "Session JWT" \
>   --description "Short-lived access token minted by the Auth Service; carried on every API call."
> ```
>
> ```bash
> # remember as D4
> TM_DIAGRAM_ID=<D> tm --id-only data-item create \
>   --identifier "D4" --classification "secret" --parent-node-id <P_AUTH> \
>   --name "Refresh Token" \
>   --description "Long-lived refresh token used to mint new access JWTs without re-auth."
> ```
>
> ```bash
> # remember as D5
> TM_DIAGRAM_ID=<D> tm --id-only data-item create \
>   --identifier "D5" --classification "secret" --parent-node-id <P_WEB> \
>   --name "Session Cookie" \
>   --description "HttpOnly, Secure, SameSite=Lax cookie correlating browser to server session."
> ```
>
> ```bash
> # remember as D6
> TM_DIAGRAM_ID=<D> tm --id-only data-item create \
>   --identifier "D6" --classification "secret" --parent-node-id <P_COGNITO> \
>   --name "Cognito ID Token" \
>   --description "OIDC ID token returned by Cognito after successful auth challenge."
> ```
>
> ```bash
> # remember as D7
> TM_DIAGRAM_ID=<D> tm --id-only data-item create \
>   --identifier "D7" --classification "pii" --parent-node-id <DS_RDS> \
>   --name "User Profile Record" \
>   --description "Account row: user_id, display_name, email, created_at, preferences."
> ```
>
> ```bash
> # remember as D8
> TM_DIAGRAM_ID=<D> tm --id-only data-item create \
>   --identifier "D8" --classification "pii" --parent-node-id <DS_RDS> \
>   --name "Customer Email Address" \
>   --description "RFC 5322 email address used for login and transactional mail."
> ```
>
> ```bash
> # remember as D9
> TM_DIAGRAM_ID=<D> tm --id-only data-item create \
>   --identifier "D9" --classification "pii" --parent-node-id <DS_RDS> \
>   --name "Shipping Address" \
>   --description "Street address, city, postal code attached to an order."
> ```
>
> ```bash
> # remember as D10
> TM_DIAGRAM_ID=<D> tm --id-only data-item create \
>   --identifier "D10" --classification "internal" --parent-node-id <DS_RDS> \
>   --name "Order Record" \
>   --description "Order id, line items, quantities, total amount, status."
> ```
>
> ```bash
> # remember as D11
> TM_DIAGRAM_ID=<D> tm --id-only data-item create \
>   --identifier "D11" --classification "internal" --parent-node-id <DS_RDS> \
>   --name "Audit Log Entry" \
>   --description "Append-only record: timestamp, actor, action, resource, result."
> ```
>
> ```bash
> # remember as D12
> TM_DIAGRAM_ID=<D> tm --id-only data-item create \
>   --identifier "D12" --classification "secret" --parent-node-id <EE_USER> \
>   --name "Credit Card PAN" \
>   --description "Raw primary account number entered at checkout (tokenized client-side before upstream calls)."
> ```
>
> ```bash
> # remember as D13
> TM_DIAGRAM_ID=<D> tm --id-only data-item create \
>   --identifier "D13" --classification "secret" --parent-node-id <EE_STRIPE> \
>   --name "Stripe Payment Token" \
>   --description "Opaque tokenized card reference issued by Stripe; replaces the PAN on our side."
> ```
>
> ```bash
> # remember as D14
> TM_DIAGRAM_ID=<D> tm --id-only data-item create \
>   --identifier "D14" --classification "secret" --parent-node-id <EE_STRIPE> \
>   --name "Stripe Charge Receipt" \
>   --description "Charge id, last4, amount, status returned by Stripe after capture."
> ```
>
> ```bash
> # remember as D15
> TM_DIAGRAM_ID=<D> tm --id-only data-item create \
>   --identifier "D15" --classification "pii" --parent-node-id <DS_S3> \
>   --name "Profile Photo" \
>   --description "User-uploaded avatar image stored in the user-uploads bucket."
> ```
>
> ```bash
> # remember as D16
> TM_DIAGRAM_ID=<D> tm --id-only data-item create \
>   --identifier "D16" --classification "secret" --parent-node-id <DS_S3> \
>   --name "File Attachment" \
>   --description "Customer-supplied document attached to an order or support ticket."
> ```
>
> ```bash
> # remember as D17
> TM_DIAGRAM_ID=<D> tm --id-only data-item create \
>   --identifier "D17" --classification "internal" --parent-node-id <DS_REDIS> \
>   --name "Rate Limit Counter" \
>   --description "Per-IP, per-route request counter with a short TTL."
> ```
>
> ```bash
> # remember as D18
> TM_DIAGRAM_ID=<D> tm --id-only data-item create \
>   --identifier "D18" --classification "secret" --parent-node-id <DS_REDIS> \
>   --name "Cached Session State" \
>   --description "Serialized session blob (user_id, roles, csrf token) keyed by session id."
> ```
>
> ```bash
> # remember as D19
> TM_DIAGRAM_ID=<D> tm --id-only data-item create \
>   --identifier "D19" --classification "internal" --parent-node-id <DS_SQS> \
>   --name "Async Job Message" \
>   --description "SQS message body: job type, payload, correlation id, enqueue timestamp."
> ```
>
> ```bash
> # remember as D20
> TM_DIAGRAM_ID=<D> tm --id-only data-item create \
>   --identifier "D20" --classification "pii" --parent-node-id <P_WORKER> \
>   --name "Transactional Email" \
>   --description "Rendered receipt or account-notification email ready for SES."
> ```
>
> ```bash
> # remember as D21
> TM_DIAGRAM_ID=<D> tm --id-only data-item create \
>   --identifier "D21" --classification "public" --parent-node-id <P_CDN> \
>   --name "Static Web Asset" \
>   --description "SPA bundle, CSS, images served from the CDN edge cache."
> ```
>
> ```bash
> # remember as D22
> TM_DIAGRAM_ID=<D> tm --id-only data-item create \
>   --identifier "D22" --classification "internal" --parent-node-id <P_API> \
>   --name "API Request Payload" \
>   --description "JSON request body for CRUD and business-logic endpoints."
> ```
>
> ```bash
> # remember as D23
> TM_DIAGRAM_ID=<D> tm --id-only data-item create \
>   --identifier "D23" --classification "internal" --parent-node-id <P_API> \
>   --name "API Response Payload" \
>   --description "JSON response body returned by the REST API to upstream callers."
> ```
>
> ```bash
> # remember as D24
> TM_DIAGRAM_ID=<D> tm --id-only data-item create \
>   --identifier "D24" --classification "internal" --parent-node-id <DS_SQS> \
>   --name "SQS Send Receipt" \
>   --description "MessageId / sequence-number ack returned by SQS after a successful SendMessage."
> ```
>
> ```bash
> # remember as D25
> TM_DIAGRAM_ID=<D> tm --id-only data-item create \
>   --identifier "D25" --classification "internal" --parent-node-id <EE_SES> \
>   --name "SES Send Receipt" \
>   --description "MessageId acknowledgement returned by SES after a successful SendEmail."
> ```
>
> ```bash
> # remember as D26
> TM_DIAGRAM_ID=<D> tm --id-only data-item create \
>   --identifier "D26" --classification "public" --parent-node-id <P_CDN> \
>   --name "Rendered HTML Page" \
>   --description "Server-side rendered HTML delivered as the initial document response."
> ```
>
> ```bash
> TM_DIAGRAM_ID=<D> tm diagram push --server <DFD_EDITOR_URL> >/dev/null
> ```
>
> ### Step 9 — flows + payloads (F1–F14)
>
> tm-cli stores `data_flow` rows with `node1_id < node2_id` (canonical
> integer order). Pass `--from <NODE>` to identify which side of the flow
> originates each payload; the CLI resolves it to the correct
> `source_endpoint` internally.
>
> Each `tm --id-only flow create` returns a flow id — remember it as `F1`,
> `F2`, … `F14`. The `tm flow add-payload` calls below it consume that
> flow id plus data-item / node ids you already remembered.
>
> #### F1 — End User ↔ CloudFront, HTTPS/443
>
> ```bash
> # remember as F1
> TM_DIAGRAM_ID=<D> tm --id-only flow create \
>   --node1-id <EE_USER> --node2-id <P_CDN> \
>   --name "Browser ↔ CDN" --protocol "HTTPS/443" --no-authenticated --encrypted
> ```
>
> ```bash
> TM_DIAGRAM_ID=<D> tm flow add-payload <F1> --data-item <D1>  --from <EE_USER> >/dev/null
> TM_DIAGRAM_ID=<D> tm flow add-payload <F1> --data-item <D5>  --from <EE_USER> >/dev/null
> TM_DIAGRAM_ID=<D> tm flow add-payload <F1> --data-item <D12> --from <EE_USER> >/dev/null
> TM_DIAGRAM_ID=<D> tm flow add-payload <F1> --data-item <D22> --from <EE_USER> >/dev/null
> TM_DIAGRAM_ID=<D> tm flow add-payload <F1> --data-item <D15> --from <P_CDN> >/dev/null
> TM_DIAGRAM_ID=<D> tm flow add-payload <F1> --data-item <D26> --from <P_CDN> >/dev/null
> TM_DIAGRAM_ID=<D> tm flow add-payload <F1> --data-item <D5>  --from <P_CDN> >/dev/null
> TM_DIAGRAM_ID=<D> tm flow add-payload <F1> --data-item <D17> --from <P_CDN> >/dev/null
> ```
>
> #### F2 — CloudFront ↔ ALB, HTTPS/443
>
> ```bash
> # remember as F2
> TM_DIAGRAM_ID=<D> tm --id-only flow create \
>   --node1-id <P_CDN> --node2-id <P_ALB> \
>   --name "CDN origin fetch" --protocol "HTTPS/443" --no-authenticated --encrypted
> ```
>
> ```bash
> TM_DIAGRAM_ID=<D> tm flow add-payload <F2> --data-item <D22> --from <P_CDN> >/dev/null
> TM_DIAGRAM_ID=<D> tm flow add-payload <F2> --data-item <D5>  --from <P_CDN> >/dev/null
> TM_DIAGRAM_ID=<D> tm flow add-payload <F2> --data-item <D17> --from <P_ALB> >/dev/null
> TM_DIAGRAM_ID=<D> tm flow add-payload <F2> --data-item <D26> --from <P_ALB> >/dev/null
> ```
>
> #### F3 — ALB ↔ Web Frontend, HTTP/80 (in-VPC)
>
> ```bash
> # remember as F3
> TM_DIAGRAM_ID=<D> tm --id-only flow create \
>   --node1-id <P_ALB> --node2-id <P_WEB> \
>   --name "ALB → Web Frontend (in-VPC)" --protocol "HTTP/80" --no-authenticated --no-encrypted
> ```
>
> ```bash
> TM_DIAGRAM_ID=<D> tm flow add-payload <F3> --data-item <D22> --from <P_ALB> >/dev/null
> TM_DIAGRAM_ID=<D> tm flow add-payload <F3> --data-item <D5>  --from <P_ALB> >/dev/null
> TM_DIAGRAM_ID=<D> tm flow add-payload <F3> --data-item <D17> --from <P_WEB> >/dev/null
> TM_DIAGRAM_ID=<D> tm flow add-payload <F3> --data-item <D26> --from <P_WEB> >/dev/null
> TM_DIAGRAM_ID=<D> tm flow add-payload <F3> --data-item <D5>  --from <P_WEB> >/dev/null
> ```
>
> #### F4 — Web Frontend ↔ Auth Service, HTTPS/443 (mTLS)
>
> ```bash
> # remember as F4
> TM_DIAGRAM_ID=<D> tm --id-only flow create \
>   --node1-id <P_WEB> --node2-id <P_AUTH> \
>   --name "Sign-in / token refresh" --protocol "HTTPS/443 (mTLS)" --no-authenticated --encrypted
> ```
>
> ```bash
> TM_DIAGRAM_ID=<D> tm flow add-payload <F4> --data-item <D1> --from <P_WEB> >/dev/null
> TM_DIAGRAM_ID=<D> tm flow add-payload <F4> --data-item <D5> --from <P_WEB> >/dev/null
> TM_DIAGRAM_ID=<D> tm flow add-payload <F4> --data-item <D3> --from <P_AUTH> >/dev/null
> TM_DIAGRAM_ID=<D> tm flow add-payload <F4> --data-item <D4> --from <P_AUTH> >/dev/null
> TM_DIAGRAM_ID=<D> tm flow add-payload <F4> --data-item <D5> --from <P_AUTH> >/dev/null
> ```
>
> #### F5 — Auth Service ↔ Cognito, HTTPS/443 (IAM)
>
> ```bash
> # remember as F5
> TM_DIAGRAM_ID=<D> tm --id-only flow create \
>   --node1-id <P_AUTH> --node2-id <P_COGNITO> \
>   --name "Cognito AdminInitiateAuth" --protocol "HTTPS/443 (IAM)" --authenticated --encrypted
> ```
>
> ```bash
> TM_DIAGRAM_ID=<D> tm flow add-payload <F5> --data-item <D1> --from <P_AUTH> >/dev/null
> TM_DIAGRAM_ID=<D> tm flow add-payload <F5> --data-item <D6> --from <P_COGNITO> >/dev/null
> ```
>
> #### F6 — Auth Service ↔ RDS PostgreSQL, PostgreSQL/5432 (TLS)
>
> ```bash
> # remember as F6
> TM_DIAGRAM_ID=<D> tm --id-only flow create \
>   --node1-id <P_AUTH> --node2-id <DS_RDS> \
>   --name "User-account lookup" --protocol "PostgreSQL/5432 (TLS)" --authenticated --encrypted
> ```
>
> ```bash
> TM_DIAGRAM_ID=<D> tm flow add-payload <F6> --data-item <D7> --from <P_AUTH> >/dev/null
> TM_DIAGRAM_ID=<D> tm flow add-payload <F6> --data-item <D2> --from <P_AUTH> >/dev/null
> TM_DIAGRAM_ID=<D> tm flow add-payload <F6> --data-item <D7> --from <DS_RDS> >/dev/null
> TM_DIAGRAM_ID=<D> tm flow add-payload <F6> --data-item <D2> --from <DS_RDS> >/dev/null
> TM_DIAGRAM_ID=<D> tm flow add-payload <F6> --data-item <D8> --from <DS_RDS> >/dev/null
> ```
>
> #### F7 — Web Frontend ↔ REST API, HTTPS/443 (mTLS)
>
> ```bash
> # remember as F7
> TM_DIAGRAM_ID=<D> tm --id-only flow create \
>   --node1-id <P_WEB> --node2-id <P_API> \
>   --name "API call (JWT-bearing)" --protocol "HTTPS/443 (mTLS)" --authenticated --encrypted
> ```
>
> ```bash
> TM_DIAGRAM_ID=<D> tm flow add-payload <F7> --data-item <D22> --from <P_WEB> >/dev/null
> TM_DIAGRAM_ID=<D> tm flow add-payload <F7> --data-item <D3>  --from <P_WEB> >/dev/null
> TM_DIAGRAM_ID=<D> tm flow add-payload <F7> --data-item <D17> --from <P_API> >/dev/null
> ```
>
> #### F8 — REST API ↔ RDS PostgreSQL, PostgreSQL/5432 (TLS)
>
> ```bash
> # remember as F8
> TM_DIAGRAM_ID=<D> tm --id-only flow create \
>   --node1-id <P_API> --node2-id <DS_RDS> \
>   --name "Application query" --protocol "PostgreSQL/5432 (TLS)" --authenticated --encrypted
> ```
>
> ```bash
> TM_DIAGRAM_ID=<D> tm flow add-payload <F8> --data-item <D22> --from <P_API> >/dev/null
> TM_DIAGRAM_ID=<D> tm flow add-payload <F8> --data-item <D7>  --from <P_API> >/dev/null
> TM_DIAGRAM_ID=<D> tm flow add-payload <F8> --data-item <D9>  --from <P_API> >/dev/null
> TM_DIAGRAM_ID=<D> tm flow add-payload <F8> --data-item <D10> --from <P_API> >/dev/null
> TM_DIAGRAM_ID=<D> tm flow add-payload <F8> --data-item <D11> --from <P_API> >/dev/null
> TM_DIAGRAM_ID=<D> tm flow add-payload <F8> --data-item <D7>  --from <DS_RDS> >/dev/null
> TM_DIAGRAM_ID=<D> tm flow add-payload <F8> --data-item <D8>  --from <DS_RDS> >/dev/null
> TM_DIAGRAM_ID=<D> tm flow add-payload <F8> --data-item <D9>  --from <DS_RDS> >/dev/null
> TM_DIAGRAM_ID=<D> tm flow add-payload <F8> --data-item <D10> --from <DS_RDS> >/dev/null
> TM_DIAGRAM_ID=<D> tm flow add-payload <F8> --data-item <D11> --from <DS_RDS> >/dev/null
> ```
>
> #### F9 — REST API ↔ ElastiCache Redis, Redis/6379 (TLS)
>
> ```bash
> # remember as F9
> TM_DIAGRAM_ID=<D> tm --id-only flow create \
>   --node1-id <P_API> --node2-id <DS_REDIS> \
>   --name "Session / rate-limit cache" --protocol "Redis/6379 (TLS)" --authenticated --encrypted
> ```
>
> ```bash
> TM_DIAGRAM_ID=<D> tm flow add-payload <F9> --data-item <D12> --from <P_API> >/dev/null
> TM_DIAGRAM_ID=<D> tm flow add-payload <F9> --data-item <D11> --from <P_API> >/dev/null
> TM_DIAGRAM_ID=<D> tm flow add-payload <F9> --data-item <D12> --from <DS_REDIS> >/dev/null
> TM_DIAGRAM_ID=<D> tm flow add-payload <F9> --data-item <D11> --from <DS_REDIS> >/dev/null
> ```
>
> #### F10 — REST API ↔ S3 User Uploads, HTTPS/443 (S3 SigV4)
>
> ```bash
> # remember as F10
> TM_DIAGRAM_ID=<D> tm --id-only flow create \
>   --node1-id <P_API> --node2-id <DS_S3> \
>   --name "User-upload read/write" --protocol "HTTPS/443 (S3 SigV4)" --authenticated --encrypted
> ```
>
> ```bash
> TM_DIAGRAM_ID=<D> tm flow add-payload <F10> --data-item <D15> --from <P_API> >/dev/null
> TM_DIAGRAM_ID=<D> tm flow add-payload <F10> --data-item <D16> --from <P_API> >/dev/null
> TM_DIAGRAM_ID=<D> tm flow add-payload <F10> --data-item <D15> --from <DS_S3> >/dev/null
> TM_DIAGRAM_ID=<D> tm flow add-payload <F10> --data-item <D16> --from <DS_S3> >/dev/null
> ```
>
> #### F11 — REST API ↔ SQS Job Queue, HTTPS/443 (SQS SendMessage)
>
> ```bash
> # remember as F11
> TM_DIAGRAM_ID=<D> tm --id-only flow create \
>   --node1-id <P_API> --node2-id <DS_SQS> \
>   --name "Enqueue async job" --protocol "HTTPS/443 (SQS SendMessage)" --authenticated --encrypted
> ```
>
> ```bash
> TM_DIAGRAM_ID=<D> tm flow add-payload <F11> --data-item <D13> --from <P_API> >/dev/null
> TM_DIAGRAM_ID=<D> tm flow add-payload <F11> --data-item <D18> --from <DS_SQS> >/dev/null
> ```
>
> #### F12 — REST API ↔ Stripe, HTTPS/443
>
> ```bash
> # remember as F12
> TM_DIAGRAM_ID=<D> tm --id-only flow create \
>   --node1-id <P_API> --node2-id <EE_STRIPE> \
>   --name "Charge payment" --protocol "HTTPS/443" --authenticated --encrypted
> ```
>
> ```bash
> TM_DIAGRAM_ID=<D> tm flow add-payload <F12> --data-item <D13> --from <P_API> >/dev/null
> TM_DIAGRAM_ID=<D> tm flow add-payload <F12> --data-item <D14> --from <P_API> >/dev/null
> TM_DIAGRAM_ID=<D> tm flow add-payload <F12> --data-item <D14> --from <EE_STRIPE> >/dev/null
> ```
>
> #### F13 — Background Worker ↔ SQS Job Queue, HTTPS/443 (SQS ReceiveMessage)
>
> ```bash
> # remember as F13
> TM_DIAGRAM_ID=<D> tm --id-only flow create \
>   --node1-id <P_WORKER> --node2-id <DS_SQS> \
>   --name "Poll job queue" --protocol "HTTPS/443 (SQS ReceiveMessage)" --authenticated --encrypted
> ```
>
> ```bash
> TM_DIAGRAM_ID=<D> tm flow add-payload <F13> --data-item <D13> --from <P_WORKER> >/dev/null
> TM_DIAGRAM_ID=<D> tm flow add-payload <F13> --data-item <D13> --from <DS_SQS> >/dev/null
> ```
>
> #### F14 — Background Worker ↔ Amazon SES, HTTPS/443 (SES SendEmail)
>
> ```bash
> # remember as F14
> TM_DIAGRAM_ID=<D> tm --id-only flow create \
>   --node1-id <P_WORKER> --node2-id <EE_SES> \
>   --name "Send transactional email" --protocol "HTTPS/443 (SES SendEmail)" --authenticated --encrypted
> ```
>
> ```bash
> TM_DIAGRAM_ID=<D> tm flow add-payload <F14> --data-item <D14> --from <P_WORKER> >/dev/null
> TM_DIAGRAM_ID=<D> tm flow add-payload <F14> --data-item <D8>  --from <P_WORKER> >/dev/null
> TM_DIAGRAM_ID=<D> tm flow add-payload <F14> --data-item <D19> --from <EE_SES> >/dev/null
> ```
>
> Final push for this step:
>
> ```bash
> TM_DIAGRAM_ID=<D> tm diagram push --server <DFD_EDITOR_URL> >/dev/null
> ```
>
> ### Step 10 — confirm and report
>
> The editor has now received eight `diagram-updated` broadcasts (one per
> build step) and any open browser tab focused on `<REMOTE_ID>` shows the
> complete topology. Print the ids as the final lines of output:
>
> ```bash
> echo "diagram_id: <D>"
> echo "remote_id:  <REMOTE_ID>"
> ```
>
> To re-sync after local edits, just re-run `TM_DIAGRAM_ID=<D> tm diagram
> push --server <DFD_EDITOR_URL>` — element UUIDs are deterministic
> (uuid5 over the tm-cli integer ids), so dfd_editor-side layout is
> preserved and the editor re-renders in place.

---

## Notes

- **One diagram per run.** The `default` diagram fallback is bypassed by
  prefixing every command with `TM_DIAGRAM_ID=<D>`; the `tm diagram
  create` in Step 1 mints a fresh, named diagram per run.
- **Idempotency.** `tm flow add-payload` uses `INSERT OR IGNORE` on the
  `flow_payload` junction (`(flow_id, data_item_id, source_endpoint)` is
  the composite PK), so re-running a step is safe — the same data item
  at the same endpoint is a no-op. A data item appearing at both endpoints
  (e.g., `D5` Session Cookie on F1) is two separate rows and is correctly
  preserved.
- **Re-pushing and live updates.** The first `tm diagram push` (in Step 1)
  POSTs the document and persists the dfd_editor-minted diagram UUID
  locally; every subsequent push is a `PUT` to the same UUID and triggers
  a `diagram-updated` websocket broadcast, so any editor tab focused on
  `<REMOTE_ID>` re-renders live. Element UUIDs are
  `uuid5(NS_TM_DIAGRAM_PUSH, "{diagram_id}:{collection}:{local_id}")`,
  so dfd_editor-side layout (positions, sizes, manual moves) survives
  every re-push.
- **Opening the diagram.** `POST /api/agent/diagrams/<remote_id>/display`
  broadcasts a `display` event over the editor's websocket, telling
  connected browsers to switch to that diagram. It's a one-shot call
  issued in Step 1 right after the initial push; later pushes don't need
  to repeat it.
- **Push granularity.** This prompt pushes once per build step (Steps 2–9)
  for a clear progressive render. Pushing more often (e.g. after each
  flow in Step 9) gives a more dramatic live build at the cost of N extra
  HTTP round-trips; pushing only once at the end (the original demo
  flow) is faster but the editor stays empty until the final push lands.
- **Verification.** `TM_DIAGRAM_ID=<D> tm node list`, `… tm container list`,
  `… tm flow list`, `… tm data-item list`, and `… tm flow get <Fk>` are
  useful sanity checks before/after a push.
- **Schema reference.** `tm schema --all` returns Pydantic JSON Schema
  for every entity. `tm commands` returns the full Click tree. `tm agent-info`
  prints the agent-oriented orientation document.

## Enum reference

(Same as the source dfd_editor demo — both projects share the taxonomy.)

- `classification` ∈ `{unclassified, internal, pii, secret, public}`
- `entity-type` ∈ `{user, service, system, device}`
- `trust-level` ∈ `{public, authenticated, admin, system}`
- `storage-type` ∈ `{database, cache, file, queue, bucket}`
- `privilege-level` ∈ `{internet, dmz, corporate, restricted}`
- Node `type` (subcommand) ∈ `{process, external-entity, data-store}`
- Container `type` (subcommand) ∈ `{trust-boundary, container}`
