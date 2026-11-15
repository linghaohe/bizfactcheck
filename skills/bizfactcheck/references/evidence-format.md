# Evidence manifest

Write a new UTF-8 JSON file. Paths resolve relative to that file. Include only pairs whose business entity, reporting scope and intended comparison you can explain.

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
      "quote": "The proposal lists USD 120 million.",
      "value": "USD 120 million"
    }
  }]
}
```

Kinds: auto, money, duration, percentage, period, status, text. Values are verbatim substrings of quotes. Do not convert `120万元` to `CNY 1200000` in a manifest; the checker normalizes supported values. Quotes must occur in the cited file; choose enough context to identify a unique passage. Ambiguous/missing anchors remain review items.

For context-sensitive claims, keep the full condition in the quote. If source says “up to 120万元 before tax” and draft says “120万元 after tax”, a pair containing only the numeric strings would hide the actual discrepancy. Preserve a text-level review item and explain the tax/limit condition. The offline tool does not infer tax calculations or general logical entailment.

A supported numeric equality does not settle whether claims refer to the same project, period or population. Use separate checks for those dimensions or leave the relationship unresolved. Never invent a source quote to make a manifest pass.
