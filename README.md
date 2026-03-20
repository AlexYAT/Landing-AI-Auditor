# Landing AI Auditor (v1)

CLI tool for conversion-focused landing page audits using parsed HTML and LLM reasoning.

## Features
- CLI landing audit
- HTML parsing
- Conversion-focused analysis
- Structured JSON output

## Architecture
- `parser` - fetches and parses landing HTML snapshot
- `analyzer` - validates/normalizes LLM output into stable schema
- `llm provider` - calls OpenAI and extracts strict JSON safely
- `exporter` - writes final pretty JSON report

## Installation
- `python -m venv .venv`
- `pip install -r requirements.txt`

## Setup
- Copy `.env.example` -> `.env`
- Set `OPENAI_API_KEY`

Required environment variables:

```env
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4.1-mini
REQUEST_TIMEOUT=20
MAX_TEXT_CHARS=12000
```

## Usage

Example:

`python main.py --url "https://example.com" --task "Improve conversion"`

Verbose example:

`python main.py --url "https://example.com" --task "Improve conversion" --verbose --output "output/report.json"`

## Example Output

```json
{
  "summary": {
    "overall_assessment": "The page communicates a core offer but likely loses conversion due to generic CTAs and limited trust evidence.",
    "primary_conversion_goal_guess": "Lead form submission",
    "top_strengths": [
      "Clear first-screen heading",
      "Form is present above fold content"
    ],
    "top_risks": [
      "CTA copy lacks concrete outcome language",
      "Trust and social proof signals are weak around key actions"
    ]
  },
  "issues": [
    {
      "id": "issue_1",
      "title": "CTA copy is generic",
      "severity": "high",
      "category": "cta",
      "evidence": "Detected CTA text is generic and does not state the user outcome.",
      "impact": "Lower click intent and reduced conversion progression.",
      "recommendation": "Rewrite primary CTA with explicit value and expected next-step outcome."
    }
  ],
  "recommendations": [
    {
      "priority": "high",
      "title": "Strengthen value near main form",
      "action": "Add concise benefit statement and trust proof near the main CTA/form block.",
      "expected_impact": "Higher CTA click-through and form completion rate."
    }
  ],
  "quick_wins": [
    {
      "title": "Improve CTA text",
      "action": "Replace generic CTA labels with specific value-oriented actions.",
      "why_it_matters": "Reduces ambiguity and improves action clarity."
    }
  ]
}
```

## Limitations v1
- no JS rendering
- no visual layout analysis
- HTML snapshot only

## Roadmap
- FastAPI
- UI
- screenshot analysis
- device emulation
