# TaurusData V2 CSV Data Dictionary

This document explains the CSV files generated under `batch_outputs/v2/`.
It is intended for importing the data into downstream systems without guessing
what each column means.

## General Interpretation Rules

- `batch_id`: Batch or universe identifier from the input YAML, for example `nifty_50_shariah`.
- `input_symbol`: The exact symbol from the input file. Preserve this as the primary import key for the batch.
- `input_company_name`: The exact company name from the input file.
- `nse_symbol`: NSE-resolved symbol. Usually the same as `input_symbol`, but can differ after symbol changes, mergers, or manual review.
- `confidence`: Context-specific confidence score from `0.0` to `1.0`.
  - In source and classification files, it usually means evidence/source confidence.
  - In relationship candidate files, it currently means candidate relationship usefulness/confidence, not just whether the source fact is true.
- `inferred`: Whether a non-edge row contains analyst or sector inference rather than a directly disclosed fact. This remains on segment and product outputs.
- `provenance_type`: Mandatory relationship provenance enum for edge-like rows. Values are `deterministic`, `derived`, and `inferred`.
  - `deterministic`: Direct structured relationship fact from an authoritative API/table with no interpretation. Reserve this strictly.
  - `derived`: Deterministic rule output from deterministic inputs, such as NSE classification equality.
  - `inferred`: LLM, agent, analyst, annual-report interpretation, profile overlap, heuristic value-chain mapping, or ambiguous historical rows.
- Empty strings mean unavailable, not disclosed, or not extracted.
- `null` values in JSON profiles may become empty strings in CSV exports.
- None of these files contain buy/sell recommendations. Relationship rows are research hypotheses unless explicitly disclosed.

## Confidence Scale

- `0.90-1.00`: Directly disclosed by NSE, exchange filings, annual reports, official investor presentations, or company filings.
- `0.75-0.89`: Strongly supported by official company material, but normalized or summarized.
- `0.60-0.74`: Supported by credible sources or strong business-model reasoning.
- `0.40-0.59`: Industry-level inference useful for research and graph discovery.
- `0.20-0.39`: Weak candidate or broad factor relationship. Use for exploration, not as a strong signal.
- `0.00-0.19`: Insufficient for analytical use without more evidence.

Important: For `edge_candidates.csv`, a low confidence score can mean the edge is broad or weak as a relationship, even when the underlying NSE classification fact is reliable.

## annual_report_index.csv

One row per annual-report filing discovered for each input company.

| Column | Meaning | Import Interpretation |
| --- | --- | --- |
| `input_symbol` | Exact input symbol. | Batch-level company key. |
| `input_company_name` | Exact input company name. | Display/source-preservation field. |
| `nse_symbol` | NSE-resolved symbol used for API calls. | Use for NSE joins. |
| `nse_issuer_name` | NSE issuer/company name. | Use as official issuer name from NSE. |
| `symbol_match_status` | Symbol-resolution result, such as `exact_symbol_match` or `manual_review_required`. | Flag non-exact matches for manual review. |
| `fromYr` | Annual-report start financial year. | Fiscal-year lower bound. |
| `toYr` | Annual-report end financial year. | Fiscal-year upper bound; sort descending for latest. |
| `submission_type` | NSE submission type. | Filing metadata. |
| `broadcast_dttm` | NSE broadcast timestamp. | Filing event timestamp. |
| `disseminationDateTime` | NSE dissemination timestamp. | Preferred timestamp for filing availability. |
| `fileName` | Annual-report URL. | Source URL for download or citation. |
| `file_extension` | URL/file extension, for example `.pdf` or `.zip`. | Helps downstream file handling. |
| `is_primary_report` | `true` when selected as the latest primary report. | Filter to latest report per company. |
| `download_status` | Download result such as `downloaded`, `cached`, `downloaded_from_zip`, `failed`, or `not_found`. | Use to detect missing local files. |
| `local_file_path` | Absolute local path to downloaded/extracted report. | Local file reference for text extraction. |
| `notes` | Download/extraction notes. | Inspect for ZIP member choice or errors. |

## company_industry_classifications.csv

One row per company with NSE classification and identity metadata.

| Column | Meaning | Import Interpretation |
| --- | --- | --- |
| `batch_id` | Input universe or batch identifier. | Grouping key. |
| `input_symbol` | Exact input symbol. | Batch-level company key. |
| `input_company_name` | Exact input company name. | Display/source-preservation field. |
| `nse_symbol` | NSE-resolved symbol. | NSE join key. |
| `nse_issuer_name` | NSE issuer name. | Official NSE company name. |
| `symbol_match_status` | Resolution confidence/status. | Flag mismatches. |
| `isin` | ISIN from NSE quote metadata if available. | Security identifier. |
| `listing_status` | NSE listing status, such as `Listed`. | Security status. |
| `nse_macro` | NSE macro classification. | Broadest industry grouping. |
| `nse_sector` | NSE sector classification. | Broad sector grouping. |
| `nse_industry` | NSE industry classification. | Mid-level grouping. |
| `nse_basic_industry` | NSE basic industry classification. | Most specific NSE grouping. |
| `index` | Primary NSE index label from `secInfo`. | Index-membership hint, not exhaustive. |
| `index_list` | Semicolon-separated NSE index memberships. | Use for index exposure mapping. |
| `pd_sector_index` | NSE peer/sector index field where available. | Supplemental NSE classification field. |
| `source` | Source descriptor. | Should usually be `NSE quote API secInfo`. |
| `confidence` | Confidence in the classification source. | High when NSE classification is populated. |
| `notes` | Missing/fetch notes. | Investigate if classification is blank. |

## company_financial_results.csv

Recent quarterly or period financial-result records from NSE.

| Column | Meaning | Import Interpretation |
| --- | --- | --- |
| `batch_id` | Batch identifier. | Grouping key. |
| `input_symbol` | Exact input symbol. | Company key. |
| `input_company_name` | Exact input company name. | Display field. |
| `nse_symbol` | NSE-resolved symbol. | NSE join key. |
| `from_date` | Period start date from NSE. | Financial period start. |
| `to_date` | Period end date from NSE. | Financial period end. |
| `to_date_MonYr` | Month-year period label. | Convenient period label. |
| `audited` | Audit status. | Indicates audited vs unaudited. |
| `cumulative` | Cumulative/non-cumulative flag. | Use before comparing periods. |
| `consolidated` | Consolidated/non-consolidated flag. | Use before aggregating or comparing. |
| `totalIncome` | Total income as reported by NSE. | Numeric import recommended. Units follow NSE payload. |
| `expenditure` | Expenditure as reported by NSE. | Numeric import recommended. |
| `reProLossBefTax` | Reported profit/loss before tax. | Numeric import recommended. |
| `netProLossAftTax` | Net profit/loss after tax. | Numeric import recommended. |
| `eps` | Earnings per share. | Numeric import recommended. |
| `xbrl_attachment` | NSE XBRL attachment URL. | Source file for detailed parsing. |
| `na_attachment` | NSE attachment URL. | Source file for supplementary material. |
| `re_broadcast_timestamp` | NSE rebroadcast timestamp. | Filing/update timestamp. |
| `source_url` | NSE API URL used. | Provenance field. |

## company_segments.csv

Normalized business segment rows.

| Column | Meaning | Import Interpretation |
| --- | --- | --- |
| `batch_id` | Batch identifier. | Grouping key. |
| `input_symbol` | Exact input symbol. | Company key. |
| `input_company_name` | Exact input company name. | Display field. |
| `financial_year` | Financial year the segment row refers to. | Usually latest annual report year. |
| `segment_name` | Segment or curated business area name. | Segment dimension. |
| `revenue` | Segment revenue if cleanly disclosed. | Empty when not disclosed/extracted. |
| `revenue_share_percent` | Segment revenue share if available or strongly supported. | Numeric percent; empty when not disclosed. |
| `profit_or_ebit` | Segment profit/EBIT if disclosed. | Empty when unavailable. |
| `profit_share_percent` | Segment profit share if available. | Empty when unavailable. |
| `products_services` | Semicolon-separated products/services in the segment. | Useful for product graph seeding. |
| `source_document` | Source used for the segment. | Provenance summary. |
| `source_section_or_page` | Source section or page reference. | Evidence pointer. |
| `confidence` | Confidence in the segment mapping. | Lower when segment is inferred. |
| `inferred` | Whether the segment row is inferred. | Treat inferred rows as curated taxonomy, not disclosed P&L. |

## company_products.csv

Products and services mapped to normalized product groups.

| Column | Meaning | Import Interpretation |
| --- | --- | --- |
| `batch_id` | Batch identifier. | Grouping key. |
| `input_symbol` | Exact input symbol. | Company key. |
| `input_company_name` | Exact input company name. | Display field. |
| `product_or_service` | Product/service name. | Product dimension. |
| `normalized_product_group` | Normalized product category. | Use for cross-company grouping. |
| `business_segment` | Segment the product belongs to. | Join to `company_segments.csv` when possible. |
| `customer_industry` | Main customer/end-use industry. | Downstream demand mapping. |
| `product_type` | Type such as `core_product`, `service`, `platform`, `emerging_product`. | Product classification. |
| `economics_type` | Economics label such as `commodity_like`, `branded`, `regulated`, `recurring`, `project_based`. | Useful for factor modeling. |
| `source` | Evidence/provenance summary. | Check for official vs inferred source. |
| `confidence` | Confidence in product mapping. | Lower for inferred/sector-level rows. |
| `inferred` | Whether row is inferred. | Filter if only direct disclosures are needed. |

## company_dependencies.csv

Upstream and downstream dependencies flattened from curated profiles.

| Column | Meaning | Import Interpretation |
| --- | --- | --- |
| `batch_id` | Batch identifier. | Grouping key. |
| `input_symbol` | Exact input symbol. | Company key. |
| `input_company_name` | Exact input company name. | Display field. |
| `dependency_name` | Dependency name, such as raw material, supplier industry, customer industry, macro factor. | Dependency node label. |
| `dependency_type` | Type such as `raw_material`, `commodity`, `labour`, `regulation`, `customer_industry`. | Dependency node type. |
| `upstream_or_downstream` | `upstream` for inputs/suppliers, `downstream` for customers/end markets. | Directional dependency class. |
| `related_industry` | Related supplier or customer industry. | Industry node label. |
| `related_commodity_or_macro_factor` | Commodity or macro factor, if separated. | Factor node label. |
| `importance` | `high`, `medium`, `low`, or `unknown`. | Qualitative materiality. |
| `expected_sign` | Expected stock/margin relationship sign: `positive`, `negative`, `mixed`, or `unknown`. | Hypothesis sign, not proof. |
| `expected_lag_days_min` | Minimum expected lag in days. | Hypothesis timing. |
| `expected_lag_days_max` | Maximum expected lag in days. | Hypothesis timing. |
| `mechanism` | Explanation of how the dependency affects the company. | Human-readable causal hypothesis. |
| `evidence_type` | Evidence basis such as `disclosed`, `inferred_from_industry`, `curated_profile_overlap`. | Source strength indicator. |
| `source` | Source/provenance summary. | Review before using in high-stakes models. |
| `confidence` | Confidence in the dependency mapping. | Combine with `provenance_type` and `evidence_type`. |
| `provenance_type` | Relationship provenance enum: `deterministic`, `derived`, or `inferred`. | Supplier/customer industry dependencies are usually `inferred` unless sourced from a direct structured relationship table. |

## company_edges.csv

Curated, higher-value graph edges between companies or nodes.

| Column | Meaning | Import Interpretation |
| --- | --- | --- |
| `batch_id` | Batch identifier. | Grouping key. |
| `source_node_id` | Source graph node ID. | Graph source key. |
| `source_node_type` | Source node type, such as `company`, `industry`, `commodity`. | Graph source type. |
| `source_symbol` | Source company symbol if applicable. | Company source symbol. |
| `source_name` | Source display name. | Display field. |
| `target_node_id` | Target graph node ID. | Graph target key. |
| `target_node_type` | Target node type. | Graph target type. |
| `target_symbol` | Target company symbol if applicable. | Company target symbol. |
| `target_name` | Target display name. | Display field. |
| `edge_type` | Relationship type, such as `direct_competitor`, `common_raw_material_exposure`, `complementary_product`. | Graph edge label. |
| `direction` | `source_to_target`, `bidirectional`, or `unknown`. | Graph direction. |
| `expected_sign` | Expected relationship sign. | Hypothesis sign, not proven correlation. |
| `expected_lag_days_min` | Minimum lag assumption. | Timing hypothesis. |
| `expected_lag_days_max` | Maximum lag assumption. | Timing hypothesis. |
| `relationship_strength` | Qualitative strength: `high`, `medium`, `low`. | Use separately from confidence. |
| `evidence_type` | Evidence basis. | Disclosed vs inferred distinction. |
| `mechanism` | Causal/tradability explanation. | Main field for model interpretation. |
| `tradability_relevance` | Why the edge may matter for trading/research. | Use for feature selection. |
| `source` | Source/provenance summary. | Evidence pointer. |
| `confidence` | Confidence in the edge mapping. | Not a measured statistical correlation. |
| `provenance_type` | Relationship provenance enum: `deterministic`, `derived`, or `inferred`. | Same NSE industry/basic-industry rule outputs are `derived`; profile overlap, filing interpretation, and LLM-assisted curation are `inferred`. |

## edge_candidates.csv

Lower-threshold candidate edges for discovery and future reconciliation.
A pair of companies can appear multiple times with different `candidate_edge_type`
or `basis`.

| Column | Meaning | Import Interpretation |
| --- | --- | --- |
| `batch_id` | Batch identifier. | Grouping key. |
| `source_symbol` | Source company symbol. | Company source key. |
| `source_name` | Source company name. | Display field. |
| `target_symbol` | Target company symbol. | Company target key. |
| `target_name` | Target company name. | Display field. |
| `candidate_edge_type` | Candidate relationship type, such as `same_macro`, `same_sector`, `same_industry`, `same_basic_industry`, `common_raw_material_exposure`, `common_customer_industry`. | Candidate graph edge label. |
| `basis` | The specific classification or overlap that created the candidate. | For example `Healthcare`, `IT - Software`, `Pharmaceuticals`, `packaging`. |
| `relationship_strength` | Qualitative usefulness strength. | Broad edges are often `low` even if source data is reliable. |
| `evidence_type` | Evidence basis, such as `nse_classification` or `curated_profile_overlap`. | Helps distinguish NSE facts from curated overlaps. |
| `expected_sign` | Expected sign if any. | Usually `mixed` for broad candidates. |
| `confidence` | Current confidence in the candidate relationship's usefulness, not always source confidence. | Classification facts from NSE may be reliable even when this score is low. |
| `provenance_type` | Relationship provenance enum: `deterministic`, `derived`, or `inferred`. | NSE classification equality candidates are `derived`; curated profile-overlap candidates are `inferred`. |
| `notes` | Usage guidance. | Review before promoting to `company_edges.csv`. |

Recommended import behavior:

- Import every row as a candidate graph edge.
- Do not collapse multiple rows for the same company pair unless your downstream model intentionally deduplicates by pair.
- Treat `same_macro` and `same_sector` as broad factor exposures.
- Treat `same_industry` and `same_basic_industry` as more specific peer-candidate signals.
- Treat `common_raw_material_exposure` and `common_customer_industry` as hypothesis candidates requiring review.

## company_risks.csv

Risk factors per company.

| Column | Meaning | Import Interpretation |
| --- | --- | --- |
| `batch_id` | Batch identifier. | Grouping key. |
| `input_symbol` | Exact input symbol. | Company key. |
| `input_company_name` | Exact input company name. | Display field. |
| `risk_name` | Risk label. | Risk node/name. |
| `risk_category` | Risk category, such as `raw material price risk`, `regulatory risk`, `demand cyclicality`. | Risk taxonomy. |
| `affected_segment` | Segment affected by the risk. | Segment/risk join field. |
| `expected_impact_direction` | Expected direction, usually `negative`, `mixed`, or `positive`. | Hypothesis sign. |
| `time_horizon` | Expected horizon. | Timing classification. |
| `peer_or_company_specific` | Whether risk is broad peer-level or company-specific. | Helps generalize across peers. |
| `source` | Evidence/provenance summary. | Review before production use. |
| `confidence` | Confidence in risk mapping. | Not probability of the event occurring. |

## source_evidence.csv

Evidence rows supporting high-impact profile claims.

| Column | Meaning | Import Interpretation |
| --- | --- | --- |
| `evidence_id` | Unique evidence ID. | Join key from profiles or audit trail. |
| `batch_id` | Batch identifier. | Grouping key. |
| `input_symbol` | Exact input symbol. | Company key. |
| `input_company_name` | Exact input company name. | Display field. |
| `claim_type` | Type of claim supported, such as `industry_classification`, `financial_results`, `business_model`, `dependency_mapping`. | Evidence category. |
| `claim_summary` | Short claim supported by the source. | Human-readable evidence summary. |
| `source_title` | Source title/name. | Citation label. |
| `source_type` | Source type, such as `exchange_api`, `annual_report`, `annual_report_and_web_research`. | Source quality classification. |
| `source_date` | Source date if available. | Evidence date. |
| `source_url_or_reference` | URL or local/reference pointer. | Source location. |
| `page_or_section` | Page or section where claim is supported. | Evidence locator. |
| `verbatim_excerpt_short` | Short excerpt when available. | Kept intentionally brief. |
| `confidence` | Confidence in the evidence supporting the claim. | Source confidence, not model prediction. |

## processed_companies.csv

Incremental processing tracker for companies included in consolidated V2 outputs.
Use this file to detect already processed companies before researching a new
input universe or incremental batch.

| Column | Meaning | Import Interpretation |
| --- | --- | --- |
| `batch_id` | Batch or universe identifier where the company was first processed. | Grouping key; may differ across historical tracker rows. |
| `input_symbol` | Exact input symbol. | Primary skip/deduplication key for incremental runs. |
| `input_company_name` | Exact input company name. | Display/source-preservation field. |
| `nse_symbol` | NSE-resolved symbol. | Use for NSE joins and uniqueness checks. |
| `isin` | ISIN from NSE quote metadata or curated identity data. | Security identifier; verify uniqueness for non-empty values. |
| `legal_company_name` | Curated legal company name. | Official/canonical company name where available. |
| `common_company_name` | Curated common display name. | Preferred display name for downstream tools. |
| `normalized_symbol` | Normalized ticker symbol. | Symbol-normalization key for deduplication. |
| `company_name_key` | Normalized company-name key. | Company-name deduplication key; verify uniqueness for non-empty values. |
| `processed_status` | Processing state, usually `processed`. | Rows with processed status should be skipped unless a deliberate refresh is requested. |
| `processed_date` | Date the tracker row was created or last updated. | Processing audit date. |
| `curation_status` | Profile curation state, such as `curated_v2_agent_assisted` or `scaffold_needs_agent_review`. | Use to distinguish reviewed profiles from scaffolds needing agent review. |
| `overall_confidence` | Overall profile confidence score from `0.0` to `1.0`. | High-level curation quality signal. |
| `latest_annual_report_financial_year` | Latest annual-report financial year used for the profile when available. | Helps assess source recency. |
| `source_profile_file` | Source profile export file, usually `company_profiles.jsonl`. | Join/reference pointer for profile details. |
| `notes` | Processing, extraction, weak-data, or review notes. | Inspect before assuming a row is fully curated. |

## research_summary.md

This is not a CSV, but downstream users should read it before importing.
It summarizes:

- number of companies researched
- curation status
- weak or missing data
- annual-report extraction issues
- strongest edges and factor hypotheses
- recommended next steps

## incremental_manifest.json

This is also not a CSV, but it is important for incremental imports.
It records:

- input YAML file
- symbols in the current input batch
- all symbols included in the consolidated output
- whether `--all-profiles` was used
- missing research packs, if any

Use this file to verify that consolidated v2 exports include both newly processed
and previously processed companies.
