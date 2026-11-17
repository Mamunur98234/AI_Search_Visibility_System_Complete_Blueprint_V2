# Metrics & Methodology

Status: **Proposed (Phase 0)**. This document becomes the seed for the in-app Methodology Knowledge Base (Module S).

## Rules that apply to every metric

1. Every metric is displayed with: **numerator, denominator, scope, source, method, period, timestamp, confidence label**.
2. If the denominator is 0 or inputs are missing, the value is **"No data"** with a reason — never `0%`.
3. Sample metrics state: provider(s), model(s), date range, market, language/locale, prompt set + version, n runs.
4. No sample metric is described as representing all users, all answers or the whole market.
5. No metric implies causation. Before/after comparisons are labelled "observed change".

## Eligibility of a prompt run

A `PromptRun` is **eligible** when: status = completed; prompt was active in the set version;
provider/model is within the report's selected scope; run time within the period; response parsed
without error; not marked excluded by an analyst (reason required). Failed and excluded runs are
counted and shown, not hidden.

## Definitions

| Metric | Formula | Notes |
|---|---|---|
| Observed mention rate | eligible runs with ≥1 brand mention ÷ eligible runs | Brand = brand name or configured alias; `detection_method` shown; unreviewed LLM-detected mentions labelled `ai_extracted_unverified` |
| Observed citation rate | eligible runs with ≥1 qualifying owned-domain citation ÷ eligible runs | Owned domain = verified `Domain` of the client (and configured subdomains). Qualifying: valid URL, owned host, present in provider's citation field or answer text |
| Competitor observed presence | eligible runs with ≥1 mention of competitor C ÷ **same** eligible runs | Always computed over the identical run set as the brand |
| Citation share within sample | owned-domain qualifying citations ÷ all qualifying citations in the same run set | Counts citations, not runs. "Within sample" always shown in label |
| Share of observed AI voice (advanced) | eligible runs with brand presence ÷ eligible runs, broken down by provider/topic | Never called "share of voice" without "observed" + sample disclosure |
| Topic coverage | tracked topics with ≥1 mapped relevant owned page ÷ tracked topics | Mapping rule recorded per mapping (`analyst`, `gsc_query_match`, `title_heading_match`) |
| Technical issue rate | URLs affected by rule R ÷ URLs eligible for rule R in that audit run | Eligibility per rule (e.g. canonical rule only on 200 HTML pages) |
| Organic sessions / conversions | as reported by connected GA4/GSC or import | Source, property, attribution model, date window, sampling/thresholding notes shown |

## Confidence labels

| Label | Meaning |
|---|---|
| `first_party_verified` | Directly from an authorized first-party system (own crawl of verified domain, GSC/GA4 API) |
| `customer_import` | Supplied by the customer as a file; not independently verified |
| `public_observation` | Collected from permitted public access |
| `observed_sample` | Controlled prompt sample via an approved provider API |
| `third_party_estimate` | From a licensed third-party data provider; methodology is theirs |
| `ai_extracted_unverified` | Derived by a model and not yet reviewed |
| `analyst_reviewed` | Reviewed or corrected by a named analyst (who/when recorded) |

## Known limitations (to show in reports)

- LLM API responses can differ from consumer chat interfaces (personalization, retrieval layers,
  model versions, location). API samples are indicators, not measurements of user exposure.
- Answers are non-deterministic; repeated runs of the same prompt may differ. Small samples have wide uncertainty.
- Google Search Console data is aggregated and may omit anonymized queries; GA4 may apply thresholding.
- Crawls respect robots.txt and caps; pages not crawled are not evaluated.
- Correlation between implemented changes and observed changes is not evidence of causation.
