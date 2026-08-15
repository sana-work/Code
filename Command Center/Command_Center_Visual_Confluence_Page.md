# 🚀 Command Center – Agentic Text-to-SQL Solution

> **Current State:** PostgreSQL PoC  
> **Future Target:** Oracle Database  
> **Primary Interface:** Command Center Chat UI  
> **Future Capability:** Downloadable reports with KPI cards, graphs, tables, and data

---

## 🌟 Executive Snapshot

The **Command Center** is a governed conversational interface that allows users to ask business questions in natural language and receive accurate, business-friendly answers without needing to know the underlying schema or SQL.

The current PoC runs on **PostgreSQL** and uses a controlled multi-agent workflow for metadata discovery, table selection, column grounding, SQL generation, validation, execution, and summarization.

After successful PoC validation, the solution will progress toward:

**PostgreSQL PoC → Oracle Target Architecture → SIT → UAT → PROD → Future Reporting**

---

## 🎯 What Problem Are We Solving?

Today, users may know the business question they want to ask, but they may not know:

| Challenge | Business Impact |
|---|---|
| Which source or table contains the data | Delays and dependency on technical teams |
| Which physical column represents a business term | Difficult natural-language interpretation |
| How values are stored | Incorrect filtering or assumptions |
| How to write SQL | Manual effort and specialist dependency |
| Which KPI formula is correct | Inconsistent reporting |
| Which fields are approved | Governance and security risk |

### ✅ Command Center Approach

```text
Business Question
      ↓
Metadata + Context Discovery
      ↓
Safe SQL Generation
      ↓
Validation
      ↓
Read-Only Execution
      ↓
Business-Friendly Answer
```

---

# 🧠 1. Current Agent Architecture

## Agentic Workflow

```text
┌───────────────────────────┐
│  Command Center Chat UI   │
└─────────────┬─────────────┘
              ↓
┌───────────────────────────┐
│ cc_orchestrator_agent     │
│ Root / Supervisor         │
└─────────────┬─────────────┘
              ↓
┌───────────────────────────┐
│ cc_metadata_discovery_agent│
└─────────────┬─────────────┘
              ↓
┌───────────────────────────┐
│ cc_table_routing_agent    │
└─────────────┬─────────────┘
              ↓
┌───────────────────────────┐
│ cc_table_sampling_agent   │
└─────────────┬─────────────┘
              ↓
┌───────────────────────────┐
│ cc_column_grounding_agent │
└─────────────┬─────────────┘
              ↓
┌───────────────────────────┐
│ cc_query_generation_agent │
└─────────────┬─────────────┘
              ↓
┌───────────────────────────┐
│ cc_query_validation_agent │
└─────────────┬─────────────┘
              ↓
┌───────────────────────────┐
│ cc_query_execution_agent  │
└─────────────┬─────────────┘
              ↓
┌───────────────────────────┐
│ cc_response_summarization │
└─────────────┬─────────────┘
              ↓
┌───────────────────────────┐
│ Natural Language Response │
└───────────────────────────┘
```

> 🔒 **Key Control:** SQL execution is never allowed before validation.

---

## 👥 Agent Responsibilities

| # | Agent | Primary Responsibility | Tool |
|---:|---|---|---|
| 1 | **`cc_orchestrator_agent`** | Controls the full workflow and returns the final response | — |
| 2 | **`cc_metadata_discovery_agent`** | Retrieves metadata relevant to the user question | `command_center_metadata_retrieval` |
| 3 | **`cc_table_routing_agent`** | Selects the most relevant table | — |
| 4 | **`cc_table_sampling_agent`** | Fetches a small sample from the selected table | `command_center_run_sql` |
| 5 | **`cc_column_grounding_agent`** | Identifies the most relevant columns and supporting metadata | `command_center_run_sql` |
| 6 | **`cc_query_generation_agent`** | Generates one read-only PostgreSQL query | — |
| 7 | **`cc_query_validation_agent`** | Validates SQL syntax, schema use, safety, and user intent | Future: `command_center_validate_sql` |
| 8 | **`cc_query_execution_agent`** | Executes only the validated SQL | `command_center_run_sql` |
| 9 | **`cc_response_summarization_agent`** | Converts query results into a business response | — |

---

# 🗂️ 2. Metadata & Governance Foundation

The Text-to-SQL solution is only as reliable as the metadata supplied to it.

## Core Metadata Objects

| Metadata Object | Purpose |
|---|---|
| **`AI_AGENT_METADATA`** | Consolidated metadata exposed to the agent workflow |
| **`AI_COLUMN_METADATA`** | Column name, datatype, technical description, business description, and related context |
| **`AI_TABLE_METADATA`** | Table-level purpose and business description |

### 🔍 Why Metadata Enrichment Matters

A physical column name may not match the way a user asks a question.

| Physical Column | Weak Description | Better Business Description |
|---|---|---|
| `ACCOUNTNUMBER` | Account number | Account number associated with the case and used to identify the customer account related to the case |
| `PXCREATEDATETIME` | Created datetime | Date and time when the case record was originally created |
| `PYLABEL` | Label | Business-facing label used to describe or categorize the case |

### Metadata Enrichment Checklist

- ✅ Explain what the column represents
- ✅ Explain how and when it is populated
- ✅ Explain how it is used in the business process
- ✅ Define important values where applicable
- ✅ Identify whether it is a date, status, identifier, category, measure, or text field
- ✅ Prioritize columns used by high-value business questions

---

# 🗃️ 3. Current Data Scope

## Initial Source Tables

| Business Area | Table |
|---|---|
| Current Case Data | `PACT_WORK` |
| Case History | `PACT_HISTORY_WORK` |
| Email History | `EMT_WORK_HISTORY` |
| AI Insights | `CITI_DATA_AI_INSIGHTS` |
| NLP Reporting | `CITI_DATA_NLP_REPORTING` |
| NLP Case Data | `CITI_DATA_NLP_CASEDATA` |
| API Invocation Logs | `CITI_DATA_LOG` |

---

# 📊 4. Current Progress Dashboard

### Status Legend

🟢 **Complete / Defined**  
🟡 **In Progress**  
🟠 **Planned / Dependency**  
🔵 **Future**

| Workstream | Status | Current Position |
|---|:---:|---|
| PoC scope | 🟢 | Conversational Text-to-SQL defined |
| Agent architecture | 🟢 | Nine-agent controlled workflow defined |
| Agent naming | 🟢 | Standard `cc_` naming established |
| Agent prompts | 🟢 | Updated for PostgreSQL PoC |
| Metadata objects | 🟢 | `AI_AGENT_METADATA`, `AI_COLUMN_METADATA`, `AI_TABLE_METADATA` |
| Metadata descriptions | 🟡 | Business descriptions still being enriched |
| Metadata retrieval tool | 🟢 | Current PoC tool |
| SQL execution tool | 🟢 | Current PoC tool |
| Query validation | 🟡 | Agent validation available; deterministic validation tool planned |
| Natural-language schema mapping | 🟡 | Improving with better metadata descriptions |
| Multi-table joins | 🟠 | Enable only after relationships are verified |
| Oracle migration | 🔵 | Future target |
| Report generation | 🔵 | Future capability |
| Production deployment | 🔵 | After DEV, SIT and UAT approvals |

---

# 💬 5. Example End-to-End User Query

## User asks

> **“How many API invocation records are available?”**

### What Happens Internally

| Step | Agent | Example Action |
|---:|---|---|
| 1 | `cc_orchestrator_agent` | Starts the workflow |
| 2 | `cc_metadata_discovery_agent` | Finds API log related metadata |
| 3 | `cc_table_routing_agent` | Selects `CITI_DATA_LOG` |
| 4 | `cc_table_sampling_agent` | Fetches a small controlled table sample |
| 5 | `cc_column_grounding_agent` | Confirms no additional filter column is needed |
| 6 | `cc_query_generation_agent` | Generates a count query |
| 7 | `cc_query_validation_agent` | Validates safety, syntax, and intent |
| 8 | `cc_query_execution_agent` | Executes validated SQL |
| 9 | `cc_response_summarization_agent` | Returns a natural-language answer |

### Example SQL

```sql
SELECT COUNT(*) AS api_invocation_count
FROM citi_data_log;
```

### What the user sees

> ✅ **There are 1,284 API invocation records available.**

*Illustrative example only — not a live database result.*

---

# 📈 6. KPI Coverage

## Priority Business Domains

| KPI Domain | Example Measures |
|---|---|
| 🎯 Output Success | Classification, summarization, sentiment, entity extraction |
| 👥 User & Adoption | Active users, Intent IQ usage, AI Insights views |
| 😊 Sentiment & Complaints | Negative sentiment, potential complaints, corrections |
| ⚙️ Platform Performance | API success/failure rate, latency, errors |
| ⏱️ Productivity | Time saved, FTE impact, handle-time reduction |
| 🛡️ Risk & Compliance | Feedback, access exceptions, monitoring and governance |

### Example Questions

- How many sentiment records were manually corrected?
- What is the API success rate this week?
- How many active cases currently exist?
- What are the most common API errors?
- How many NLP records were processed this month?
- How much time has case summarization saved?

---

# 🔐 7. Security & Governance Controls

## Database Controls

| Control | Requirement |
|---|---|
| Access | Read-only service account |
| Allowed SQL | `SELECT` / `WITH ... SELECT` |
| Blocked SQL | Insert, update, delete, merge, alter, drop, truncate |
| Result protection | Row/result-size limits |
| Runtime protection | Query timeout |
| Data access | Approved tables and columns only |

## Agent Controls

- 🔒 No invented tables
- 🔒 No invented columns
- 🔒 No execution before validation
- 🔒 Preserve explicit user values
- 🔒 Do not silently change business intent
- 🔒 Final answer must be grounded in query results

## Operational Controls

- Request logging
- Agent-step logging
- Generated SQL logging
- Validation logging
- Execution status logging
- Performance monitoring
- Audit and security review

---

# 🚦 8. Implementation & Deployment Strategy

## Environment Promotion Flow

```text
┌──────────────┐
│ PostgreSQL   │
│ PoC in DEV   │
└──────┬───────┘
       ↓
┌──────────────┐
│ PoC Approval │
└──────┬───────┘
       ↓
┌──────────────┐
│ Oracle DEV   │
└──────┬───────┘
       ↓
┌──────────────┐
│ SIT          │
└──────┬───────┘
       ↓
┌──────────────┐
│ UAT          │
└──────┬───────┘
       ↓
┌──────────────┐
│ PROD         │
└──────────────┘
```

---

## 🛠️ DEV

**Purpose:** Build, iterate, and validate.

| Key Activities |
|---|
| Agent configuration and prompt tuning |
| Metadata enrichment |
| PostgreSQL PoC testing |
| Tool integration |
| Regression question catalogue |
| Error handling and logging |
| SQL validation improvements |

### DEV Exit Criteria

- Priority questions work end-to-end
- Correct table and column selection
- Read-only execution verified
- No critical workflow defects

---

## 🔗 SIT

**Purpose:** Validate system integration.

| Key Activities |
|---|
| End-to-end integration testing |
| Database connectivity validation |
| Access and credential validation |
| Oracle dialect testing after migration |
| Negative and malicious SQL testing |
| Timeout and large-result testing |
| Performance and concurrency testing |
| Audit and monitoring validation |

### SIT Exit Criteria

- No critical integration defects
- Security controls validated
- Stable Oracle integration
- Logging and monitoring operational

---

## 👤 UAT

**Purpose:** Validate business usability and accuracy.

| Key Activities |
|---|
| Execute approved business-question catalogue |
| Compare results against known SQL/report results |
| Validate KPI formulas |
| Validate business terminology |
| Validate response readability |
| Capture metadata gaps |
| Obtain business/product sign-off |

### UAT Exit Criteria

- Business users confirm accuracy
- KPI calculations accepted
- User experience approved
- No open critical business defects

---

## 🚀 PROD

**Purpose:** Production operation.

### Production Readiness

- ✅ Production Oracle connectivity
- ✅ Least-privilege service account
- ✅ Approved metadata version
- ✅ Security review
- ✅ Monitoring and alerts
- ✅ Audit retention
- ✅ Support ownership
- ✅ Release plan
- ✅ Rollback plan
- ✅ Production performance baseline

---

# 🟣 9. Future Oracle State

The target design keeps the **same overall agent architecture** while switching the database-specific components.

| Area | PostgreSQL PoC | Oracle Future State |
|---|---|---|
| SQL Dialect | PostgreSQL | Oracle SQL |
| Connection | PostgreSQL | Oracle |
| Validation | PostgreSQL rules | Oracle rules |
| Row limiting | `LIMIT` | Oracle-compatible syntax |
| Date functions | PostgreSQL | Oracle date/time functions |
| Query execution adapter | PostgreSQL | Oracle |

> 💡 **Design Principle:** Keep the agent contracts stable and isolate database-specific logic.

---

# 📑 10. Future Report Generation

Report generation is **not required for the current PoC**, but can be added once Text-to-SQL is stable.

## Future User Request

> **“Generate a weekly API performance report for the last four weeks.”**

### Future Flow

```text
User Question
      ↓
Agentic Text-to-SQL
      ↓
Validated Query Result
      ↓
Future Report Rendering
      ↓
┌────────────┬────────────┬─────────────┐
│ KPI Cards  │   Graphs   │ Data Tables │
└────────────┴────────────┴─────────────┘
      ↓
Download / Share
```

### Potential Outputs

| Output | Example |
|---|---|
| KPI Cards | API success rate, total calls, response time |
| Graphs | Weekly trend, category distribution |
| Tables | KPI and detailed data |
| Raw Data | CSV / Excel |
| Report | HTML / PDF |

> 🔐 Future reports should use **validated query results only** and must not bypass Command Center security, metadata, or validation controls.

---

# 🗺️ 11. Delivery Roadmap

| Phase | Focus | Deliverable |
|---|---|---|
| **Phase 1** | PoC Foundation | Stable PostgreSQL Text-to-SQL flow |
| **Phase 2** | Metadata & Accuracy | Improved business descriptions and regression coverage |
| **Phase 3** | Validation Hardening | Deterministic validation tool and stronger controls |
| **Phase 4** | Oracle Migration | Oracle-compatible SQL generation and execution |
| **Phase 5** | SIT & UAT | Integrated and business-validated solution |
| **Phase 6** | PROD | Production release and support model |
| **Phase 7** | Reporting | Graphs, tables, KPI cards, downloadable data |

---

# ⚠️ 12. Key Risks & Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Incomplete column descriptions | Wrong schema mapping | Enrich metadata with source owners |
| Similar column names | Incorrect column selection | Improve business descriptions and grounding |
| Non-representative sample rows | Wrong assumption | Treat samples as evidence, not full-table truth |
| Unsafe SQL | Security risk | Mandatory validation + read-only access |
| PostgreSQL/Oracle syntax differences | Migration defects | Isolate dialect-specific rules |
| Inconsistent KPI definitions | Conflicting results | Maintain approved KPI definitions |
| Missing external data | Incomplete answers | Incremental source onboarding |
| Reporting bypasses controls | Governance risk | Generate reports only from validated query results |

---

# ✅ 13. Immediate Next Steps

1. Finalize priority business questions
2. Complete business descriptions for priority columns
3. Validate `AI_AGENT_METADATA`, `AI_COLUMN_METADATA`, and `AI_TABLE_METADATA`
4. Test the updated nine-agent PostgreSQL flow
5. Create and maintain a regression question suite
6. Strengthen SQL validation
7. Implement `command_center_validate_sql`
8. Finalize PoC acceptance criteria
9. Prepare Oracle migration design
10. Prepare SIT and UAT test scenarios
11. Define PROD operational controls
12. Design future report generation after the core flow is stable

---

# 🏁 14. Success Criteria

The solution is ready to progress when:

- ✅ Users can ask approved business questions in normal language
- ✅ Correct tables and columns are selected
- ✅ Generated SQL is read-only and valid
- ✅ Unsafe queries are blocked before execution
- ✅ Answers match validated query results
- ✅ Responses are understandable to business users
- ✅ Metadata gaps are measurable and continuously improved
- ✅ PostgreSQL PoC acceptance criteria are met
- ✅ Oracle migration is regression tested
- ✅ SIT and UAT sign-off is completed before PROD
- ✅ Monitoring and auditability are operational
- ✅ Future reports can consume validated results without bypassing governance

---

# 💡 Final Architecture Principle

> **Metadata First → Ground the Question → Generate Safe SQL → Validate → Execute Read-Only → Return a Business Answer**

The immediate priority is to make the PostgreSQL PoC **accurate, reliable, explainable, and controlled**.

The same architecture can then move through **Oracle → SIT → UAT → PROD** and later support **interactive reports, graphs, tables, and downloadable data** without changing the core governance model.
