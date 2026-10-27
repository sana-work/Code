Subject: UAT Guidance: Universal Chat / VEGA / Octobot Response Update

Hi Team,

Please use the guidance below when validating the updated Universal Chat prompt. Universal Chat, VEGA and Octobot refer to the same chatbot. The update focuses on answering client enquiries clearly, rather than presenting a fixed, wide table as the main response.

**Expected response structure**

The complete answer comes first, including relevant facts, explanations and any limitations. Important amounts, dates and statuses may be highlighted in bold. Supporting tables, when applicable, appear at the end under a relevant title.

Asset Services (AS) replies use only relevant labels, such as Payment details, Entitlement details, Key dates or Timing. Transaction Management (TM) replies retain Parties involved, Settlement information, and Current Status & Action Required, with Current, EOD and Settlement Instruction information kept distinct.

AS no longer returns default output columns. The chatbot must request every supported column explicitly asked for, plus the evidence, identifiers, currencies and units needed to answer correctly, in its first and only AS call. Input filters and their validation are unchanged. TM retains its registered default outputs, with relevant additional fields requested as needed.

**Questions and input formats to test**

Please use valid UAT identifiers and supported fields to test examples such as:

- AS: "Was cash paid for event [Event ID] and account [Account ID]? Confirm the amount and currency."
- AS: "Confirm the tax paid or shares delivered for event [Event ID]."
- AS: "What is the Payment Date, or latest available MT566 sent-to-client timestamp, for event [Event ID]?"
- TM: "Check the Current transaction for client reference [Reference]."
- TM: "Provide the EOD status for client reference [Reference] at close of business [Date]."
- TM: "Provide the settlement instruction status and settlement location for client reference [Reference]."

Also test combined AS/TM enquiries, multi-part questions, and follow-ups such as "the same account" where the reference is unambiguous. Unsupported facts must be explained, not invented or replaced with a different field.

Plain questions receive a structured chat answer. A pasted client email should receive an email-style reply even without a subject line. Alternatively, add "Draft a client email reply" to a plain question. Email replies include a greeting, summary/body and closing; a subject or signature must not be invented. The chatbot drafts the reply; it does not send an email.

**When to expect tables**

| Situation | Expected response |
| --- | --- |
| Default reply with 1-10 supporting rows in total | Summary first, then supporting tables. Each AS/TM table shows all returned rows and all supported requested or necessary evidence columns, including identifying fields and required currencies/units. There is no fixed column limit. Unrelated returned columns may be omitted. |
| Default reply with more than 10 supporting rows in total | Summary only, followed by an offer to show the supporting details in a table. No partial table should be shown. |
| Explicit "Show the table", including acceptance of the preceding table offer | Complete returned tables with every original column and row. Only the zero-time date formatting described below may change a displayed value. The ten-row display threshold does not apply. |
| No valid supporting data | No empty or fabricated table for that portion; explain the no-match result, limitation, error or missing input. Independently successful portions remain usable. |

The ten-row threshold is across the supporting results in the reply, not per table. For example, eight AS rows plus three TM rows triggers summary-only presentation by default. A required business clarification takes precedence over the optional table offer.

Full-table view means the complete table already returned, not every matching entry across unfetched pages. A lookup retrieves at most 50 rows per service per turn. "Show the table" is a view request; "next batch" requests a further page. Previously reviewed information must not be described as freshly retrieved unless a new lookup occurred.

Please test questions needing more than six columns, as well as narrow questions needing only a few. Requested and decisive evidence columns must not be dropped to make the table smaller. Asking for an additional column that was not originally retrieved requires a new lookup; the chatbot must not reconstruct it from earlier prose.

For email replies, the closing precedes any evidence tables. If a large result triggers a table offer, that question appears outside the client email, after the closing.

**Date display**

In answers and tables, a registered date/date-time value with an all-zero time is displayed as the date only: for example, `2026-01-01 00:00:00.000` becomes `2026-01-01`. This also applies to full-table views and values returned with `T` or no separator between date and time. Non-zero times, including non-zero fractional seconds, remain unchanged. This is display-only: original values remain available for comparisons and no timezone conversion or calendar-date shift is performed.

**Key checks**

Please verify one final assistant response, accurate answers to every part of the question, relevant table columns, and unchanged source values. Null or blank values must not become zero, "No" or "no action required"; a passed Payment Date must not be treated as proof of payment. Retrieval announcements such as "50 records fetched" should not appear, although a requested business count may be given when supported.

For final-delivery checks, the runtime-registered finalizer should be used once, without an additional direct answer. In the final payload, error must be a string: empty for non-failed outcomes and a safe non-empty message/code for FAILED, never JSON null. A literal "null" inside an original business-data cell remains source data and is not this control-field error. Please check for duplicate final events and avoid treating successful local prompt tests as confirmation that runtime publication is fixed.

Please cover invalid identifiers, no matches, unavailable fields, timeouts, mixed success/failure, and "today" or "yesterday" using the supplied local timestamp. Supported bold formatting and email replies should work; custom colours, fonts and HTML are not supported. A generic TM reference may return separately labelled information from multiple applicable TM services.

Earlier synthetic trials found minor "shown/provided below" wording flags, so please include these in presentation regression testing. The current prompt explicitly excludes that wording. Historical model trials do not validate this latest AS output-selection change or response speed; both need testing against the deployed UAT model, services and UI. Please compare response times on equivalent questions and confirm that faster replies still answer every requested point accurately.

For any discrepancy, capture the exact question, relevant conversation context, expected outcome, actual response and screenshot, using approved UAT data and reporting channels.

Kind regards,
