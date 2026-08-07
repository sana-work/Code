# Command Center – Agentic Text-to-SQL Solution (PoC)

## 1. Overview

The **Command Center** is a conversational interface that allows users to ask natural-language questions about Agent Assist, Intent IQ, operational, adoption, performance, productivity, risk, and compliance data.

The solution uses a metadata-driven multi-agent architecture to convert user questions into validated Oracle SQL, execute them using read-only access, and return a concise business response.

---

## 2. Problem Statement

Command Center data is distributed across multiple systems such as Oracle reporting tables, PACT CS Mart, AI Insights, NLP Reporting, Celonis, GSSP, user feedback, and governance platforms.

This creates challenges such as:

- Users not knowing the correct source, table, or column
- Manual report creation
- Inconsistent KPI definitions
- Missing or unverified joins between tables
- Security and governance requirements
- Difficulty converting business questions into SQL

The Command Center provides one governed conversational entry point for these data sources.

---

## 3. PoC Objectives

- Provide a single Chat UI for business questions
- Convert natural language into Oracle SQL
- Use approved metadata for table and column selection
- Prevent invented tables, columns, and joins
- Validate SQL before execution
- Use read-only database access
- Return clear business summaries
- Support future onboarding of additional KPIs and data sources

---

## 4. Scope

### In Scope

- Command Center Chat UI
- Natural-language questions
- Metadata-based schema discovery
- Oracle SQL generation and validation
- Read-only SQL execution
- Result summarization
- Session history and audit logging
- Single-table queries
- Multi-table queries only when joins are verified

### Out of Scope for Initial PoC

- Insert, update, delete, or other write operations
- Unverified multi-table joins
- Autonomous data changes
- Full dashboard or report generation
- Proactive notifications
- Production-scale integrations with all external platforms
- Access to unapproved or sensitive columns

---

## 5. Solution Architecture

### Agent Flow

```text
Command Center Chat UI
        ↓
cc_root_agent
        ↓
cc_metadata_retrieval_agent
        ↓
cc_sql_generation_agent
        ↓
cc_sql_validation_agent
        ↓
cc_sql_execution_agent
        ↓
cc_summarization_agent
        ↓
Final response returned to user
```

### Agent Responsibilities

| Agent | Responsibility |
|---|---|
| `cc_root_agent` | Understands the request, identifies intent, and orchestrates the full workflow |
| `cc_metadata_retrieval_agent` | Retrieves approved table, column, datatype, description, synonym, and relationship metadata |
| `cc_sql_generation_agent` | Generates Oracle SQL using approved metadata |
| `cc_sql_validation_agent` | Validates syntax, security, approved objects, joins, and row limits |
| `cc_sql_execution_agent` | Executes validated SQL using read-only Oracle access |
| `cc_summarization_agent` | Converts query results into a concise business response |

---

## 6. Metadata and Governance Layer

The metadata layer helps the agents understand the database without exposing unrestricted schema access.

| Object | Purpose |
|---|---|
| `AI_TABLE_METADATA` | Table names, business descriptions, row grain, default date columns, and rules |
| `AI_COLUMN_METADATA` | Column names, datatypes, descriptions, synonyms, semantic types, PII classification, and access flags |
| `AI_RELATIONSHIP_METADATA` | Verified relationships, join columns, join expressions, and cardinality |
| `AI_AGENT_METADATA_V` | Consolidated metadata view used by the metadata retrieval agent |

### Current Limitation

`AI_RELATIONSHIP_METADATA` is currently empty.

Therefore:

- Single-table queries are supported
- Multi-table joins are not allowed unless relationships are verified
- Similar column names must not be treated as valid joins automatically

---

## 7. Initial Oracle Data Sources

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

## 8. KPI Domains

### Output Success

- Classification, summarization, sentiment, and entity-extraction success
- Manual classification and sentiment changes
- Summary usage and case-review time

### User and Adoption

- Users with access and active users
- Intent IQ clicks and AI Insights views
- Usage by country, department, LOB, or case
- Unauthorized or non-enabled country access

### Sentiment and Complaints

- Potential complaints
- Negative sentiment trends
- Sentiment corrections and reclassification volumes

### Platform Performance

- API success and failure rates
- Response time and query duration
- Error counts, rate-limit usage, token usage, and agent calls

### Productivity

- Time saved
- FTE savings
- Handle-time and case-review-time reduction
- Throughput improvement

### Risk and Compliance

- User feedback and MRM monitoring
- Hallucination and guardrail metrics
- Prompt or model changes
- Attestation and access-control exceptions

---

## 9. Priority PoC KPIs

| KPI | Definition | Likely Source |
|---|---|---|
| Manual Sentiment Correction Rate | Percentage of cases where AI sentiment was manually changed | `CITI_DATA_AI_INSIGHTS` |
| Automated Urgency Accuracy | Percentage of AI-calculated urgency values accepted without manual change | AI Insights / NLP data |
| AI Insights Adoption Rate | Percentage of eligible cases where AI Insights was opened | UI event logs |
| Case Summarization Time Saved | Estimated time saved by using AI-generated summaries | Celonis / UI telemetry |
| AI Model Feedback Rate | Feedback cases per 1,000 processed cases | Feedback source |
| Manual Effort Reduction | Total time saved converted into FTE equivalent | Celonis |
| Average Handle Time Reduction | Difference between assisted and non-assisted case duration | Celonis / case lifecycle data |
| API Success Rate | Successful API calls divided by total API calls | `CITI_DATA_LOG` |

---

## 10. Example User Questions

- How many AI insight records were created this month?
- How many sentiment records were manually corrected?
- What is the API success rate this week?
- How many API calls failed?
- What are the most common API errors?
- How many active cases currently exist?
- What is the case count by status?
- How many NLP records were processed this month?
- How many classifications were changed by users?
- How much time has case summarization saved?

---

## 11. Security and Governance

- Read-only Oracle account
- Only `SELECT` and `WITH ... SELECT` queries allowed
- No insert, update, delete, merge, alter, drop, or truncate
- Only approved tables and columns can be used
- Sensitive columns must be blocked, masked, or aggregated
- SQL validation is mandatory before execution
- Joins must come from verified relationship metadata
- Query timeout and maximum row limits must be enforced
- User request, generated SQL, validation result, and execution status must be logged

---

## 12. Functional Requirements

| ID | Requirement |
|---|---|
| FR-01 | Users can submit natural-language questions through the Chat UI |
| FR-02 | The root agent orchestrates the end-to-end workflow |
| FR-03 | Metadata retrieval uses only approved schema context |
| FR-04 | SQL generation produces Oracle-compatible SQL |
| FR-05 | Validation blocks invalid or prohibited SQL |
| FR-06 | Execution uses read-only access |
| FR-07 | Results are summarized in business-friendly language |
| FR-08 | Unverified joins are blocked |
| FR-09 | Ambiguous questions trigger clarification |
| FR-10 | All agent and database activity is auditable |

---

## 13. Delivery Workstreams

### Workstream 1: Data Sourcing and KPI Definition

- Confirm KPI definitions
- Identify authoritative sources
- Map KPI attributes to physical columns
- Validate formulas
- Classify sensitive data
- Define verified relationships
- Document unavailable data and assumptions

### Workstream 2: Command Center and Agent Development

- Build the Chat UI
- Implement the six-agent workflow
- Connect agents to metadata
- Implement SQL validation
- Configure Oracle read-only execution
- Add summarization and audit logging
- Test approved business questions

---

## 14. Proposed PoC Phases

### Phase 1: Foundation

- Finalize metadata
- Configure read-only access
- Implement the agent workflow
- Support single-table queries

### Phase 2: Priority KPI Queries

- AI Insights
- Sentiment correction
- NLP reporting
- API performance
- Current case information

### Phase 3: Relationship Enablement

- Identify common business keys
- Validate cardinality
- Populate `AI_RELATIONSHIP_METADATA`
- Enable approved joins

### Phase 4: External Integrations

- Celonis
- GSSP
- User feedback
- MRM data
- User access and attestation data
- UI adoption telemetry

---

## 15. PoC Success Criteria

- Users can ask natural-language questions
- The correct source table is selected
- Generated SQL uses only approved metadata
- Invalid SQL and write operations are blocked
- Queries execute with read-only access
- Results match validated SQL output
- No unverified joins are generated
- Responses are understandable and useful
- Execution activity is logged
- Additional tables and KPIs can be onboarded without redesigning the architecture

---

## 16. Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Incomplete metadata | Review descriptions and synonyms with data owners |
| Empty relationship metadata | Start with single-table queries |
| Similar column names across tables | Require verified join metadata |
| Missing KPI data | Document dependency and mark as unavailable |
| Sensitive data exposure | Apply column-level controls and masking |
| Slow or complex SQL | Use validation, timeout, and row limits |
| Incorrect AI output | Restrict generation to approved metadata and returned results |
| External dependency delays | Deliver external integrations in later phases |

---

## 17. Open Decisions

- Confirm the common case identifier across tables
- Confirm verified relationships between current, history, email, AI, and NLP tables
- Finalize the priority KPI list
- Confirm Celonis and GSSP access
- Confirm the source for user access and attestation metrics
- Confirm the default reporting period
- Confirm response-time targets
- Confirm audit-log retention requirements
- Confirm production hosting and deployment approach

---

## 18. Immediate Next Steps

1. Approve the PoC scope
2. Finalize the priority KPI list
3. Review metadata for the seven Oracle tables
4. Identify and validate relationship keys
5. Populate approved relationships
6. Mark restricted and sensitive columns
7. Create a test-question catalogue
8. Implement and test the six-agent workflow
9. Configure Oracle read-only execution
10. Validate results with business and data owners

---

## 19. Conclusion

The Command Center PoC provides a governed conversational layer over approved Oracle data.

The initial implementation should focus on accurate single-table queries and priority KPIs. Multi-table and external-source analytics should be enabled only after relationships, source ownership, and calculation logic are formally validated.
