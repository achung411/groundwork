# Extraction response contract — version 1.0

Return a single object with exactly these top-level keys:

- `schema_version`: the string `"1.0"`.
- `document_filename`: the exact selected filename.
- `facts`: 1–50 fact objects. Each is reviewed independently.

Each fact has `fact_type`, `value`, `effective_from` (YYYY-MM-DD or null if unknown), `effective_to` (inclusive YYYY-MM-DD or null for open-ended), `status` (`"proposed"`), `uncertainty` (a nonempty explanation or null), and `evidence` (1–10 citations). An unknown effective start requires an uncertainty explanation and cannot be approved until corrected. Omitted `effective_to` or `uncertainty` means null. Do not include app IDs or extra fields.

Each citation has exactly `page` (positive integer from a supplied page marker), `section` (the exact numbered heading), and `quote` (nonempty contiguous verbatim text within that page and section). Whitespace differences are tolerated; paraphrases and quotes from a different section are rejected. Include all passages needed for the value and its effective period.

For a source page without numbered headings of the form `1. HEADING`, set `section` to the literal `Page text`; the quote must occur on that page. This fallback is rejected when the page has numbered headings. Uploaded TXT without page markers is represented as page 1; PDF markers correspond to original PDF pages. Use the app's displayed reference filename, which may differ from the original uploaded filename to distinguish properties.

| fact_type | value shape | Constraints |
|---|---|---|
| `monthly_base_rent` | `{"amount":"5050.00","currency":"USD"}` | Positive USD dollars, at most two decimal places. Decimal string preferred; JSON number also accepted. No currency symbol or commas. |
| `rent_due_day` | `{"day":1}` | Integer 1–31. |
| `grace_period` | `{"days":5}` | Integer 0–365, only if an explicit calendar-day rule supports it. Absence is omitted, not zero. |
| `lease_start` | `{"date":"2022-09-01"}` | Actual lease commencement date. |
| `lease_end` | `{"date":"2027-08-31"}` | Actual stated expiration date, not a computed or assumed exercised extension. |
| `extension_option` | `{"options_count":1,"term_months":36,"notice_earliest_months":12,"notice_latest_months":9}` | Identical options only; positive integer count and term; integer notice months ≥0, earliest ≥ latest. This describes rights, not whether they were exercised. |

For `lease_end`, `effective_from` is when that expiration term governs (typically lease commencement), not the expiration date itself. The same principle applies to option rights. Store stated dates in `value.date`. Do not infer future rent for an option period. `effective_to` is an inclusive validity end for the fact; a monthly rent rule normally remains open-ended unless the source states otherwise. An amendment replacing an open-ended rule normally uses null; lease expiration is tracked separately as `lease_end`.

The machine-readable schema is [schema.json](schema.json), generated from `app.models.ExtractionProposal`. It is an optional reference for tools; this contract contains the model-facing format and is included in the app's copyable prompt.

Format example for a separate invented source, not one of the demo packet's leases:

```json
{
  "schema_version": "1.0",
  "document_filename": "example-lease.txt",
  "facts": [
    {
      "fact_type": "monthly_base_rent",
      "value": {"amount": "2300.00", "currency": "USD"},
      "effective_from": "2026-01-01",
      "effective_to": null,
      "status": "proposed",
      "uncertainty": null,
      "evidence": [
        {
          "page": 1,
          "section": "2. RENT",
          "quote": "Beginning January 1, 2026, monthly base rent is $2,300.00."
        }
      ]
    }
  ]
}
```
