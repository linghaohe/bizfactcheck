# Usage and interpretation

[简体中文](USAGE.zh-CN.md)

## Choose a reference

Select an approved, current source and identify the business context. Split documents by project or reporting scope when the same label is reused. The tool cannot decide which conflicting source is authoritative.

## Direct mode

```bash
bizfactcheck check --source reference.md --draft proposal.md handover.docx --lang en --format md --output review.md
```

Use `Label: value`, `字段：值` or two-column tables. Keep one fact per field. Bilingual aliases cover project budget, revenue, reporting period, project stage, service term and service scope. Other labels pair only when their normalized names are identical. Repeated labels are ambiguous even if a person could infer the intended project.

Markdown table example:

```markdown
| Field | Value |
|---|---|
| Project budget | USD 1.2 million |
| Reporting period | H1 2025 |
```

Supported documents are UTF-8 `.md` / `.txt` and `.docx` body paragraphs/tables. Source locations identify extracted lines or body items; they are not physical Word page numbers. Headers, footers, drawings/text boxes and revision interpretation are not supported. Reading a DOCX does not execute macros. PDF/OCR, spreadsheets and presentations are not supported in this release.

## Prose mode

Use the skill to prepare evidence pairs or author a JSON manifest yourself. The paths are relative to the manifest file, not the current working directory. Each `value` must be copied literally from its `quote`.

```json
{
  "checks": [{
    "field": "Project budget",
    "kind": "money",
    "source": {
      "path": "reference.md",
      "quote": "The approved budget is USD 1.2 million.",
      "value": "USD 1.2 million"
    },
    "draft": {
      "path": "proposal.md",
      "quote": "The proposal gives a budget of USD 120 million.",
      "value": "USD 120 million"
    }
  }]
}
```

```bash
bizfactcheck verify checks.json --format json
```

Kinds: `auto`, `money`, `duration`, `percentage`, `period`, `status`, `text`. Missing quotes, repeated quote locations or values outside the cited quote require review. A verified literal anchor proves textual occurrence, not real-world truth or a correct semantic pairing. Use `text` or human review for different conditions, uncertain scope, negation, or unsupported forms.

The checker detects supported numeric-boundary errors and some common qualifiers/negations. These are bounded lexical rules, not general language understanding. Preserve the full original context; complex references, double negation, modality and mathematical typography still need human review.

## Supported normalization

- Decimal quantities with explicit CNY/USD units and recognized Chinese/English scales; different currencies are not exchanged.
- Recognized elapsed durations; months and years are not treated as fixed day counts.
- Percentages and percentage-points remain distinct.
- Recognized calendar years, halves and quarters. Fiscal or unusual periods need review.
- Explicit project-stage vocabulary. Different stages are review suggestions, not verified claims about a real deployment.
- Unsupported qualifiers or value forms are retained for review rather than stripped to produce a match.

The checker does not infer arbitrary arithmetic, convert currencies, establish entity identity, or resolve a source's business authority.

## Output and exit codes

Formats: `text` (default), `json`, `md`, `html`. Languages: `en` (default), `zh`. JSON keys and reason codes remain stable; human-facing reports are translated. Standalone HTML uses no remote scripts, fonts or analytics.

| Exit | Meaning |
|---|---|
| 0 | At least one comparable pair; no discrepancy or review item in those comparisons |
| 1 | At least one comparable pair, plus a discrepancy or review item |
| 2 | Invalid/unreadable/unsupported input or no comparable pair; review details may still be shown |

Reports list coverage limits, including reference fields not paired and draft fields without a corresponding reference. Omission can be intentional, so an absent field is not automatically a discrepancy. Do not present a partial comparison as a whole-document review.

`--output` creates a **new** report. It refuses existing paths, input paths and symbolic links. Without `--output`, the report goes to standard output. Be mindful that reports contain excerpts from the inputs.
