# Ops Assist Chatbot Platform — Architecture, Federation Model, Features & Roadmap

> **Purpose:** Consolidated ~3-page design brief based on the supplied architecture slides and the additional showcase/use-case notes provided by the teammate.

## 1. Executive Summary and Target Architecture

Ops Assist is positioned as the **internal operations AI assistant pillar** within a wider enterprise AI strategy that also includes Client Assist and Sales Assist. All three assistants are expected to reuse the **Services Agentic AI Platform**, while Ops Assist focuses on internal Services users across LOBs such as Payments, Trade, Investor, Core Accounts, Bank Search and related operational domains.

The proposed direction is a **shell-mounted, centrally governed Chatbot MFE platform runtime**:

- The **Shared Ops UI Host Shell** authenticates the user through SSO and dynamically loads MFEs through React + Webpack 5 Module Federation.
- The **Ops Assist / Chatbot MFE** is mounted once as a persistent sibling to business MFEs, rather than being embedded separately inside each LOB application.
- Business MFEs publish safe context changes through a governed browser event such as `CHATBOT_CONTEXT_CHANGED`.
- Navigation and chat are intentionally decoupled:
  - **Navigation / record selection** updates local chatbot context only.
  - **Explicit user chat submission** triggers the backend path.
- The **Chatbot BFF is implemented in Python**, with FastAPI as the recommended API layer.
- The BFF acts as the secure chat gateway and performs authentication validation, entitlement orchestration, context enrichment, PII redaction, rate limiting, audit/observability, response caching where safe, and streaming back to the UI.
- **EEMS** provides centralized entitlement scope and fine-grained permissions for LOB access and chatbot actions.
- **MongoDB** is proposed for conversation history and replay/audit use cases; **Redis** is proposed for session state, response cache and rate-limit counters.
- The BFF connects to the **Services Agentic AI Platform**, which provides multi-agent orchestration, reasoning, agent execution and a governed tool registry. Responses can return through SSE for interactive chat and Kafka for asynchronous/long-running flows.

### Recommended logical flow

```text
Ops User
  ↓ SSO
Shared Ops UI Host Shell
  ├── Payments MFE + LOB BFF
  ├── Trade MFE + LOB BFF
  ├── Investor MFE + LOB BFF
  ├── Other MFEs
  └── Ops Assist Chatbot MFE (mounted once)
          ↓ REST/SSE
      Main Chatbot BFF — Python/FastAPI
          ├── Auth / Security Gateway
          ├── EEMS Entitlement Scope
          ├── Context Enrichment
          ├── PII Redaction / Guardrails
          ├── Rate Limiting
          ├── Cache (safe use cases only)
          ├── MongoDB / Redis
          └── Observability
                  ↓ secure REST / Kafka
          Services Agentic AI Platform
                  ↓ governed tools
          LOB BFFs / Business APIs / MCP servers
```

### Central platform vs LOB responsibility

The architecture should preserve a strong separation of ownership.

**Central platform owns and locks:**
- Chatbot MFE runtime and mounting lifecycle
- BFF protocol and security contract
- authentication / token handling
- EEMS integration
- PII redaction and prompt guardrails
- conversation persistence rules
- audit and observability standards
- SSE streaming contract
- extension governance and versioning
- core tool execution policy

**LOBs receive governed extension points for:**
- persona and greeting
- feature flags
- suggested prompts
- domain context schema
- approved tools / MCP integrations
- rich UI artifacts and actions
- domain-specific agent or workflow configuration
- LOB BFF endpoint or adapter configuration

A key recommendation is to expose these capabilities through **versioned contracts**, not by allowing each LOB to fork the core chatbot.

---

## 2. Federation Models, Base Features and Showcase Use Cases

### Federation models

The slides describe three adoption paths. These should remain as the enterprise onboarding model.

#### Path A — Federate within the Shared Ops UI Shell
Best for Services LOBs already participating in the shared platform.

- LOB MFE joins the Shared Ops shell.
- Chatbot MFE is already mounted and upgraded centrally.
- LOB supplies JSON configuration, approved tools and UI extensions.
- Context flows through the shared event contract.
- Strongest option for consistency, observability and centralized governance.

**Recommended default path for internal Services LOBs.**

#### Path B — Code Adoption / Kickstart
Best for teams with their own MFE shell or custom frontend platform.

- Central team provides versioned React MFE + Python BFF starter code.
- Adopting team deploys and owns its instance.
- Security contracts remain non-negotiable.
- More customization is possible, but upgrades and infrastructure ownership shift to the adopting team.

**Use selectively where Path A is not feasible.**

#### Path C — Embed into Application
Best for monoliths, vendor UIs and legacy portals with no MFE architecture.

Possible mechanisms:
- iframe
- web component
- centrally hosted widget
- API-only / agentic integration

Context can be passed through `postMessage`, query parameters or API contracts. This path has the highest integration complexity and weaker native event-bus behavior, so it should be treated as a compatibility path rather than the default.

### Base feature inventory

The current material already identifies a solid enterprise baseline.

#### Frontend / Chatbot MFE
- persistent conversation state
- Context Provider
- `CHATBOT_CONTEXT_CHANGED` event listener
- dedicated BFF client
- SSE streaming renderer
- retry and timeout handling
- graceful mid-stream disconnect behavior
- host-isolation so chatbot failures do not crash the business MFE
- React Context API and/or Redux for state sharing
- TypeScript for strongly typed contracts
- shared ICG design system / reusable UI components

#### Python Chatbot BFF
- FastAPI REST endpoints
- authentication validation
- EEMS entitlement checks
- server-side context enrichment
- PII redaction
- per-user / per-LOB rate limiting
- safe response caching
- conversation-history access
- AI platform connectivity
- structured logging and correlation IDs
- REST for synchronous requests
- Kafka for asynchronous/long-running activity where appropriate

#### Persistence and platform services
- MongoDB conversation history
- Redis session cache, active state, rate limits and safe response cache
- Kafka for asynchronous event propagation
- observability for P50/P95/P99 latency, errors, usage and satisfaction
- SSO / JWT / OAuth 2.0
- RBAC / EEMS entitlement management

### Teammate-provided showcase details incorporated

#### Use Case 1 — OnePay MTP Maker Task Recommendation
**Goal:** When a maker arrives at a task, Ops Assist receives the context already available in the UI and provides key information plus a recommended resolution/action plan.

**Agent design:**
- no tool call required for the first showcase
- use current MTP context
- produce a recommendation plan
- entitlement initially marked N/A in the notes, but the platform should still keep the security boundary ready

**Why it matters:**
- proves rich contextual assistance without rebuilding the LOB workflow
- demonstrates a reusable maker/checker pattern across LOBs
- showcases Path A with low integration effort

**Build focus:**
- context contract
- recommendation response
- rich UI artifacts
- action controls
- tables/charts
- downloadable output

#### Use Case 2 — Bank Search MFE Ops Assist Chat
**Goal:** Allow Bank Search users to query existing live application data with natural language and receive rich UI results.

**Agent design:**
- current on-screen record context
- Bank Search API exposed as an MCP-compatible tool
- single entitlement to start
- returned artifacts support view, copy and download

**Why it matters:**
- demonstrates how a new domain-specific assistant can be rolled out quickly using Path A
- proves coexistence of passive UI context plus active tool invocation

#### Additional showcase items
- **External Team Path A use case:** prove that an external team can integrate without making the Core team the delivery bottleneck.
- **E2E entitlement use case:** show permission enforcement from UI context through BFF, EEMS, tool invocation and final response.
- **Path C embeddable chat:** provide a reusable template for a legacy application, using web-component-compatible elements and native browser event communication.

---

## 3. Recommended Roadmap and Additional Features

### Phase 0 — Architecture contracts and decisions (1 sprint)
**Outcome:** lock the platform boundaries before feature development.

Deliver:
- Chatbot MFE public contract
- context-event schema and versioning
- Python BFF OpenAPI contract
- entitlement decision contract
- SSE event schema
- LOB config schema
- plugin/tool registration schema
- audit and observability event model
- Path A/B/C onboarding decision matrix

Key decisions:
- central BFF vs per-LOB BFF responsibility
- MongoDB retention policy
- Redis caching boundaries
- Kafka topics and ownership
- MCP governance model
- approved rich-UI artifact schema

### Phase 1 — Core Path A platform MVP (2–3 sprints)
Build:
- shell-mounted Chatbot MFE
- Context Provider
- event-driven context updates
- Python FastAPI BFF
- SSO token validation
- EEMS integration skeleton
- SSE streaming
- MongoDB conversation storage
- Redis session/rate-limit support
- baseline observability
- safe error handling

Pilot with:
- **OnePay MTP Maker Recommendation**

Acceptance:
- navigation does not trigger AI calls
- chat submission triggers BFF only
- chatbot persists across MFE navigation
- entitlement scope is propagated
- complete trace uses a correlation ID

### Phase 2 — Domain federation and rich UI (2–3 sprints)
Build:
- LOB config registry
- governed tool/MCP registration
- rich UI artifact renderer
- tables/charts/downloads
- action cards with permission checks
- Path A onboarding kit
- Bank Search MCP integration

Pilot with:
- **Bank Search MFE Ops Assist Chat**

Acceptance:
- new LOB can onboard without modifying core runtime
- tools are allow-listed and entitlement checked
- rich artifacts are schema validated

### Phase 3 — Enterprise hardening (2 sprints)
Build:
- E2E entitlement scenario
- PII / restricted-data policies
- prompt-injection defenses
- audit replay
- circuit breakers and downstream timeout policy
- dead-letter/retry strategy for Kafka flows
- safe cache policy
- accessibility validation
- performance and load tests

### Phase 4 — Paths B and C enablement (3–4 sprints)
Build:
- versioned code-adoption starter kit
- upgrade compatibility checks
- embeddable web component
- `postMessage` context bridge
- API-only integration template
- legacy app reference implementation

### Phase 5 — Scale and productization (ongoing)
Build:
- LOB self-service onboarding portal
- central extension marketplace
- automated contract conformance tests
- agent/tool evaluation dashboards
- usage and cost chargeback
- release compatibility matrix
- adoption analytics

### Recommended additional features

The following capabilities would materially strengthen the platform beyond the current slides.

1. **Typed Rich Artifact Protocol**  
   Define a standard response schema for text, tables, charts, downloadable files, citations and actions. This avoids each LOB inventing its own renderer.

2. **Tool and MCP Governance Registry**  
   Track tool owner, LOB, version, risk class, permissions, allowed data classification, approval status and kill switch.

3. **Human Confirmation for Sensitive Actions**  
   Read-only actions may be automatic; approve, cancel, release or escalate operations should support explicit confirmation and step-up authorization.

4. **Context TTL and Domain-Switch Policy**  
   Prevent stale context from one LOB being reused after the user moves to another domain. Add expiration, reset and conflict-resolution rules.

5. **Agent Evaluation and Regression Suite**  
   Maintain golden queries for intent accuracy, groundedness, tool selection, refusal behavior and policy compliance before every release.

6. **End-to-End Trace Explorer**  
   Trace `UI event → Chatbot MFE → Python BFF → EEMS → AI Platform → tool/MCP → response`, including latency, token usage, redaction and policy decisions.

7. **Safe Conversation Memory Controls**  
   Separate short-term conversational memory from long-term history. Add retention, deletion, summarization and classification rules.

8. **Extension Compatibility and Version Negotiation**  
   Every LOB config, context schema, plugin and tool contract should declare supported platform versions so central upgrades do not silently break adopters.

9. **Operational Kill Switches**  
   Allow central operators to disable one LOB integration, one tool, one model or one plugin without taking down the whole chatbot.

10. **Self-Service LOB Onboarding**  
    Provide templates, SDKs, OpenAPI specs, conformance tests and a promotion workflow from sandbox to production.

## Final Recommendation

Use **Path A as the strategic default** for Services LOBs: one shell-mounted Ops Assist MFE, one centrally governed platform contract, Python/FastAPI BFF enforcement, shared EEMS entitlement, and LOB customization through config, context events, approved tools/MCP and rich UI artifacts.

Use **Path B only when a team genuinely requires code ownership**, and use **Path C as a compatibility pattern for legacy or non-MFE applications**.

The next highest-value step is to complete the **OnePay MTP recommendation** and **Bank Search MCP** showcases because together they prove both sides of the platform value proposition:

- passive context-aware assistance with minimal LOB build effort
- active natural-language tool use with entitlement-aware rich UI output
