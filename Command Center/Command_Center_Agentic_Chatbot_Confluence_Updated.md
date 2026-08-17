# 🚀 Command Center – Agentic Chatbot Solution Architecture

> **Current State:** PostgreSQL PoC  
> **Primary Interface:** Command Center Chat UI  
> **Future Target:** Oracle Database  
> **Future Direction:** Fewer agents, faster processing, conditional data sampling, and optional downloadable reports

---

## 🌟 Executive Snapshot

The **Command Center** is a governed **agentic chatbot** that allows users to ask business questions in natural language and receive concise, data-grounded answers without knowing database tables, columns, or query syntax.

**Text-to-SQL is an internal capability of the chatbot**, used to translate business questions into safe database queries. It is not the product identity.

### Current PoC flow

**Metadata Discovery → Table Routing → Table Sampling → Column Grounding → Query Generation → Query Validation → Query Execution → Response Summarization**

The current design intentionally separates responsibilities for easier validation and troubleshooting. The future design will consolidate related responsibilities into fewer agents to reduce latency.

---

# 1. Current Architecture

```text
Command Center Chat UI
        ↓
cc_orchestrator_agent
        ↓
cc_metadata_discovery_agent
        ↓
cc_table_routing_agent
        ↓
cc_table_sampling_agent
        ↓
cc_column_grounding_agent
        ↓
cc_query_generation_agent
        ↓
cc_query_validation_agent
        ↓
cc_query_execution_agent
        ↓
cc_response_summarization_agent
        ↓
Business-Friendly Answer
```

> 🔒 **Core control:** final business SQL is executed only after validation.

### Current design strengths

- Clear separation of responsibilities
- Governed metadata-driven decisions
- Read-only SQL execution
- Validation before final execution
- Easy troubleshooting by agent step
- Natural-language response returned to the Chat UI

### Current performance concern

The **table sampling step is currently one of the largest contributors to response time** because it introduces an additional agent hop and database query for every request.

This is acceptable for PoC validation, but it should not remain mandatory in the optimized future architecture.

---

# 2. Current Agent Responsibilities

| # | Agent | Current Responsibility | Tool |
|---:|---|---|---|
| 1 | `cc_orchestrator_agent` | Coordinates the current workflow | — |
| 2 | `cc_metadata_discovery_agent` | Retrieves relevant governed metadata | `command_center_metadata_retrieval` |
| 3 | `cc_table_routing_agent` | Selects the best single table | — |
| 4 | `cc_table_sampling_agent` | Retrieves a small table sample | `command_center_run_sql` |
| 5 | `cc_column_grounding_agent` | Maps business language to physical columns | — |
| 6 | `cc_query_generation_agent` | Generates one read-only PostgreSQL query | — |
| 7 | `cc_query_validation_agent` | Validates query safety, schema use and intent | — |
| 8 | `cc_query_execution_agent` | Executes only validated SQL | `command_center_run_sql` |
| 9 | `cc_response_summarization_agent` | Returns the final business-friendly answer | — |

---

# 3. Metadata Foundation

The active metadata model remains intentionally simple:

| Metadata Object | Purpose |
|---|---|
| **`AI_AGENT_METADATA`** | Search-friendly metadata used by the agent workflow |
| **`AI_COLUMN_METADATA`** | Physical column names, datatypes, descriptions, display names, synonyms and semantic context |
| **`AI_TABLE_METADATA`** | Table purpose, business description, row grain, date context and table synonyms |

## Metadata enrichment priority

`AI_COLUMN_METADATA` should progressively include:

- `display_name`
- `normalized_name`
- `business_description`
- `synonyms`
- `semantic_type`
- `selectable_flag`
- `filterable_flag`
- `agent_notes`

Example:

```text
Physical column: ACCOUNTNUMBER
Display name: Account Number
Normalized name: accountnumber
Synonyms: account, account id, customer account
Business description: Unique account identifier associated with the case.
```

Better metadata reduces the need for exploratory sampling.

---

# 4. Current Query Processing

The chatbot currently performs four major logical activities:

### Discover and Ground

Relevant tables and columns are identified from governed metadata. A small table sample is then used to improve confidence where descriptions alone are not sufficient.

### Generate

A single-table, read-only PostgreSQL query is generated using only approved metadata and grounded columns.

### Validate and Execute

The query is checked for:

- read-only behavior
- approved table/column usage
- PostgreSQL correctness
- user-intent alignment
- safe query boundaries

Only validated SQL is executed.

### Respond

Database results are converted into a concise natural-language response suitable for the Command Center Chat UI.

---

# 5. Future Optimized Agent Architecture

The future state should **not simply migrate all nine PoC agents to Oracle**.

The target is a smaller, more precise architecture with **four core agents**.

```text
Command Center Chat UI
        ↓
1. cc_orchestrator_agent
        ↓
2. cc_data_context_agent
   Metadata Discovery
   + Table Selection
   + Column Grounding
   + Conditional Sampling
        ↓
3. cc_query_intelligence_agent
   Query Generation
   + Deterministic Validation
   + Read-only Execution
        ↓
4. cc_response_agent
   Natural-Language Answer
   + Optional Report Handoff
        ↓
Business Answer / Optional Report
```

## Future agent responsibilities

| Future Agent | Consolidates | Key Responsibility |
|---|---|---|
| **`cc_orchestrator_agent`** | Root coordination | Route only the processing required for the request |
| **`cc_data_context_agent`** | Metadata discovery + table routing + column grounding + sampling decision | Build the minimum trusted data context needed |
| **`cc_query_intelligence_agent`** | Query generation + validation + execution coordination | Generate Oracle SQL, validate deterministically, then execute read-only |
| **`cc_response_agent`** | Summarization + report decision | Return concise answer and optionally hand results to report rendering |

---

# 6. Sampling Optimization

Sampling should become a **conditional capability**, not a dedicated always-on agent.

### Current

```text
Every Question
    ↓
Table Sampling Agent
    ↓
SELECT * FROM selected_table LIMIT 8
```

### Future

```text
Metadata Confidence Check
        ↓
High confidence ─────────────→ Skip sampling
        ↓
Low confidence / value evidence needed
        ↓
Targeted sample only
```

### Recommended improvements

- Skip sampling when metadata is sufficient.
- Sample only the selected columns instead of `SELECT *`.
- Sample only when a filter value, categorical mapping, or ambiguous field needs verification.
- Cache reusable metadata context.
- Reuse recent safe profiling results where appropriate.
- Apply strict row limits and timeout controls.
- Keep sampling deterministic rather than creating another LLM reasoning hop.

This directly addresses the current latency bottleneck.

---

# 7. Future Oracle & Reporting State

After PoC acceptance:

```text
PostgreSQL PoC
      ↓
Optimized Agent Design
      ↓
Oracle DEV
      ↓
SIT
      ↓
UAT
      ↓
PROD
```

The Oracle future state requires:

- Oracle-compatible SQL generation
- deterministic query validation
- read-only Oracle execution
- performance and concurrency testing
- security and audit controls
- metadata validation against Oracle objects

## Optional report generation

Reporting remains downstream of successful query execution:

```text
Business Question
      ↓
Optimized Agentic Chatbot
      ↓
Validated Query Results
      ├────────→ Natural-Language Answer
      │
      └────────→ Optional Report Renderer
                       ↓
                 KPI Cards
                 Graphs
                 Tables
                 CSV / Excel
                 HTML / PDF
```

The report renderer should **consume approved query results** and must not bypass the governed query path.

---

# 8. Current Progress & Future Work

| Area | Status | Direction |
|---|:---:|---|
| PostgreSQL PoC workflow | 🟢 | Functional current state |
| Metadata retrieval | 🟢 | Continue enrichment |
| Table routing | 🟢 | Future consolidation into Data Context Agent |
| Table sampling | 🟡 | Current latency hotspot; make conditional |
| Column grounding | 🟢 | Future consolidation into Data Context Agent |
| Query generation | 🟢 | Migrate dialect to Oracle later |
| Query validation | 🟢 | Move toward deterministic validation |
| Query execution | 🟢 | Future Oracle read-only adapter |
| UI response formatting | 🟢 | Compact business-friendly text |
| Future 4-agent architecture | 🔵 | Planned optimization |
| Oracle migration | 🔵 | After PoC acceptance |
| Downloadable reports | 🔵 | Future optional capability |

---

# ✅ Immediate Next Steps

1. Continue improving `AI_COLUMN_METADATA` and `AI_TABLE_METADATA`.
2. Measure per-agent latency to establish a baseline.
3. Quantify table-sampling latency separately.
4. Test when sampling can safely be skipped.
5. Prototype consolidation of metadata discovery, routing and grounding.
6. Add deterministic SQL validation.
7. Compare the current 9-agent flow with the optimized 4-agent flow for:
   - response time
   - query accuracy
   - metadata-selection accuracy
   - token usage
   - database calls
8. Move the optimized design to Oracle after PoC acceptance.
9. Add the optional report renderer only after query accuracy and performance are stable.

---

# 🏁 Architecture Principle

> **Understand the business question → retrieve only the required governed context → sample only when necessary → generate and validate safely → execute read-only → return a concise business answer.**

The future Command Center should be **simpler, faster and more precise**, not simply a larger version of the PoC.
