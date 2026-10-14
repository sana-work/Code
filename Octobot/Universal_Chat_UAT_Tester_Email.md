Subject: UAT Guidance: Universal Chat / VEGA / Octobot Response Update

Hi Team,

Please use the guidance below when validating the updated Universal Chat prompt. Universal Chat, VEGA and Octobot refer to the same chatbot. The update focuses on answering client enquiries clearly, rather than presenting a fixed, wide table as the main response.

**Expected response structure**

The complete answer comes first, including relevant facts, explanations and any limitations. Important amounts, dates and statuses may be highlighted in bold. Supporting tables, when applicable, appear at the end under a relevant title.

Asset Services (AS) replies use only relevant labels, such as Payment details, Entitlement details, Key dates or Timing. Transaction Management (TM) replies retain Parties involved, Settlement information, and Current Status & Action Required, with Current, EOD and Settlement Instruction information kept distinct.

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
| Default reply with 1-10 supporting rows in total | Summary first, then supporting tables. Each AS/TM table shows all returned rows and at most six relevant source columns. |
| Default reply with more than 10 supporting rows in total | Summary only, followed by an offer to show the supporting details in a table. No partial table should be shown. |
| Explicit "Show the table", including acceptance of the preceding table offer | Complete returned tables with every original column and row, unchanged. The six-column and ten-row display limits do not apply. |
| No valid supporting data | No empty or fabricated table for that portion; explain the no-match result, limitation, error or missing input. Independently successful portions remain usable. |

The ten-row threshold is across the supporting results in the reply, not per table. For example, eight AS rows plus three TM rows triggers summary-only presentation by default. A required business clarification takes precedence over the optional table offer.

Full-table view means the complete table already returned, not every matching entry across unfetched pages. A lookup retrieves at most 50 rows per service per turn. "Show the table" is a view request; "next batch" requests a further page. Previously reviewed information must not be described as freshly retrieved unless a new lookup occurred.

For email replies, the closing precedes any evidence tables. If a large result triggers a table offer, that question appears outside the client email, after the closing.

**Key checks**

Please verify one final assistant response, accurate answers to every part of the question, relevant table columns, and unchanged source values. Null or blank values must not become zero, "No" or "no action required"; a passed Payment Date must not be treated as proof of payment. Retrieval announcements such as "50 records fetched" should not appear, although a requested business count may be given when supported.

Please cover invalid identifiers, no matches, unavailable fields, timeouts, mixed success/failure, and "today" or "yesterday" using the supplied local timestamp. Supported bold formatting and email replies should work; custom colours, fonts and HTML are not supported. A generic TM reference may return separately labelled information from multiple applicable TM services.

The synthetic check found minor "shown/provided below" wording flags, so please include these in presentation regression testing. This check does not replace validation against the deployed UAT model, services and UI.

For any discrepancy, capture the exact question, relevant conversation context, expected outcome, actual response and screenshot, using approved UAT data and reporting channels.

Kind regards,
