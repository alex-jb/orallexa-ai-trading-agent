# Official headline development pilot — October 5, 2026

Four **real, short Federal Reserve headline excerpts**, each paired with WFC and JPM, provide eight cases for testing source preparation and the annotation workflow. There are only **two event groups**: three updates to one Wells Fargo enforcement lifecycle, and one FOMC statement. Repeated ticker queries are not independent events. No human label, adjudicated gold, model output, accuracy estimate or return result is included.

## Sources and selection

| Source ID | Official release time in UTC | Selected scope |
| --- | --- | --- |
| [fed-wfc-20180202](https://www.federalreserve.gov/newsevents/pressreleases/enforcement20180202a.htm) | 2018-02-02 23:15 | First sentence of headline; second sentence omitted. |
| [fed-wfc-20250603](https://www.federalreserve.gov/newsevents/pressreleases/enforcement20250603a.htm) | 2025-06-03 20:00 | Complete short headline. |
| [fed-wfc-20260305](https://www.federalreserve.gov/newsevents/pressreleases/enforcement20260305a.htm) | 2026-03-05 16:00 | Complete short headline. |
| [fed-fomc-20260916](https://www.federalreserve.gov/newsevents/pressreleases/monetary20260916a.htm) | 2026-09-16 18:00 | Complete short headline. |

The [Board's publication policy](https://www.federalreserve.gov/disclaimer.htm), checked October 5, describes its information as public domain unless otherwise indicated. This selection contains Board-authored headline text only, with attribution and original URLs. It contains no logos, photographs, linked third-party materials or full article bodies. The first release uses a deliberately shortened excerpt; it must not be mistaken for a complete release.

Source/ticker aliases are documented in `acquisition_receipts.json` against the companies' official publications. The manifest defines company relevance using explicit identity or an unambiguous alias, not general sector exposure. This is the rubric to be applied independently; no resulting classification has been supplied here.

## Provenance and times

Snapshots were created October 5 from official pages opened through web retrieval. The extraction preserves the selected punctuation, encodes UTF-8 and appends one LF. `bundle.json` binds exact snapshot bytes and the `headline` span, which excludes that terminal LF. `acquisition_receipts.json` records the source URLs, session-local retrieval references, extraction/version/scope and timestamp basis. Raw HTML is **not** archived; these are selected model-input text files with retrieval metadata, not complete original-page archives or authenticated receipts.

`published_at_utc` converts each page's stated release time and EST/EDT offset. `available_at_utc` is the current availability of this selected input to this repository, recorded at extraction; it does not claim the first historical market availability. Capture and freeze use the actual October 5 clock. This retrospective collection cannot establish an earlier forecast's information set.

## Run and continue

```bash
python -m eval.news_source_preflight --manifest eval/data/news_source_pilot_2026-10-05/manifest.json --source-bundle eval/data/news_source_pilot_2026-10-05/bundle.json
python -m eval.news_annotation prepare --manifest eval/data/news_source_pilot_2026-10-05/manifest.json --source-bundle eval/data/news_source_pilot_2026-10-05/bundle.json --output-dir /path/new-review-work
```

`blank_reviews/` preserves the initial preflight and two entirely unreviewed templates. Work in a new directory, leaving this committed blank seed intact. Follow [independent review and explicit adjudication](../../../docs/NEWS_ANNOTATION.md); even two agreeing reviews need explicit adjudication before gold is generated.

`sample_kind:development_pilot` means purposive, publicly exposed workflow material. The schema's `test` split selects rows to annotate/score; it does not make this seed held out. The `unselected` model entry is a schema placeholder with `configuration_status:not_selected`, no configured provider and no predictions. A proper prospective study must separately freeze its selection policy, model configurations and inputs. These four English titles do not establish broad news coverage, bilingual capability or financial judgement.
