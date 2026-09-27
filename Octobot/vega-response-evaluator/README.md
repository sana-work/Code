# VEGA Hybrid Response Evaluator

This evaluator combines deterministic Python checks with a single semantic evaluator. It reads all `gssp_agentic.audit_table` rows for one `x_correlation_id`, reconstructs the execution, and creates a JSON evaluation report.

## 1. Remote environment setup

Use environment variables for the database connection. Do not place credentials in the script.

```bash
export VEGA_DB_HOST='<remote-postgresql-host>'
export VEGA_DB_PORT='1524'
export VEGA_DB_NAME='gssp_agentic'
export VEGA_DB_USER='<database-user>'
export VEGA_DB_PASSWORD='<database-password>'
export VEGA_DB_SSLMODE='require'

# Set these according to how audit timestamps are stored and interpreted.
export VEGA_DB_TIMEZONE='UTC'
export VEGA_BUSINESS_TIMEZONE='Asia/Kolkata'
```

Install the PostgreSQL driver:

```bash
python -m pip install -r requirements.txt
```

## 2. Run deterministic evaluation

```bash
python vega_response_evaluator.py \
  --correlation-id '<x-correlation-id>' \
  --agent-payload-out evaluator_request.json \
  --output evaluation_report.json
```

Without an evaluator result, the report status is `AWAITING_AGENT`. The objective score and agent request are still generated.

## 3. Connect the single evaluator

Use `evaluator_agent_prompt.md` as the evaluator's instruction. Configure the evaluator endpoint to accept the generated JSON and return the documented output schema.

For direct integration with the synchronous executor endpoint, configure its URL and required headers:

```bash
export EVALUATOR_AGENT_URL='https://<host>/api/v1/agentic-orchestration/sync/task-executor'
export EVALUATOR_CONFIG_ID='<single-evaluator-config-id>'
export EVALUATOR_APPLICATION_ID='<application-id>'
export EVALUATOR_SOEID='<required-soeid>'

# Optional location headers
export EVALUATOR_COUNTRY='<country>'
export EVALUATOR_REGION='<region>'
export EVALUATOR_AGENT_TOKEN='<bearer-token-if-required>'

# Recommended: generate the required COIN token automatically.
# Include the required scope query parameter in the URL.
export EVALUATOR_TOKEN_URL='https://<coin-host>/token/<client-id>?scope=<scope>'
export EVALUATOR_CLIENT_SECRET='<client-secret>'

python vega_response_evaluator.py \
  --correlation-id '<x-correlation-id>' \
  --output evaluation_report.json
```

The script sends `{"clientSecret": "<client-secret>"}` to the token endpoint and passes the returned token to the executor as:

```text
X-Authorization-Coin: Bearer <token>
```

Alternatively, provide an already-generated token and omit the token URL and client secret:

```bash
export EVALUATOR_AUTHORIZATION_COIN='<token>'
```

Do not store the client secret or generated token in source files. When `EVALUATOR_AUTHORIZATION_COIN` is provided, the token endpoint is not called.

The script calls the endpoint with this request shape:

```json
{
  "context": "<serialized evaluator request JSON>",
  "parts": [],
  "metadata": {},
  "state": {},
  "additional_tool_headers": {}
}
```

`context` contains the question, execution timestamp, actual tool results, VEGA final response, deterministic scores, and approved business rules. A new `X-Correlation-ID` is generated for every evaluator call unless `EVALUATOR_CORRELATION_ID` is explicitly set.

If the platform invokes the evaluator separately, save its JSON output and merge it:

```bash
python vega_response_evaluator.py \
  --correlation-id '<x-correlation-id>' \
  --agent-result evaluator_result.json \
  --output evaluation_report.json
```

## 4. Optional business rules

Status-code meanings must be provided explicitly. Example:

```json
{
  "statusMappings": {
    "PRJCTD": {
      "description": "Projected",
      "clientPaid": false
    }
  }
}
```

Pass the file with `--rules approved_business_rules.json`. Undocumented codes remain unevaluated rather than being guessed.

## 5. Local fixture mode

The script can be tested without database access using a JSON array whose objects use the audit table column names:

```bash
python vega_response_evaluator.py \
  --rows-json synthetic_audit_rows.json \
  --output evaluation_report.json
```

## Scoring

- Deterministic Python checks: 70%
- Semantic evaluator: 30%
- Overall score of 80 or greater: `PASS`
- Overall score from 65 to 79.99: `REVIEW`
- Lower score: `FAIL`
- Any critical failure forces `FAIL`

The report does not include database credentials. Source records are sent to the evaluator only when an evaluator URL is configured.
