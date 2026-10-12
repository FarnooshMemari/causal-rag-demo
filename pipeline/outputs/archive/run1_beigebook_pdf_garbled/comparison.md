# Ordinary vs graph-guided retrieval: side-by-side

Event: U.S. Census Bureau Advance Monthly Sales for Retail and Food Services, July 2023 (Release CB23-127). Cutoff 2023-08-15T10:00:00-04:00. Budget: 20 chunks per strategy (4 per edge for graph-guided). Eligible after time filter: 283 chunks from 19 documents; excluded by filter: F01_fomc_minutes_2023_07, F04_census_retail_2023_08, F05_powell_jackson_hole_2023.

> Relevance grades (`g=`) are **model-generated provisional labels** pending human review (annotations/relevance_annotation_sheet.csv).

## Retrieval summary (provisional labels)

| metric | ordinary (1 broad query) | graph-guided (5 edge queries) |
|---|---|---|
| edges with >=1 directly relevant chunk (of 5) | 3 | 4 |
| budget slots directly relevant to some edge (of 20) | 7 | 14 |
| unique chunks | 20 | 20 |
| distinct documents | 9 | 8 |
| document types | {'fed_publication': 5, 'official_economic_release': 2, 'company_earnings_disclosure': 2} | {'fed_publication': 4, 'company_earnings_disclosure': 4} |

Per edge: directly-relevant (grade 2) chunks among those the assessor sees for that edge

| edge | ordinary: grade2 / offered | graph-guided: grade2 / offered |
|---|---|---|
| E1 consumption→earnings_expectations | 0 / 20 | 3 / 4 |
| E2 earnings_expectations→equity_support | 3 / 20 | 4 / 4 |
| E3 consumption→inflation_pressure | 2 / 20 | 0 / 4 |
| E4 inflation_pressure→rate_expectations | 3 / 20 | 4 / 4 |
| E5 rate_expectations→equity_valuation_pressure | 0 / 20 | 2 / 4 |

## Assessment summary (3 repeats each, identical inputs)

| metric | ordinary | graph-guided |
|---|---|---|
| citation_validity | 0.857 | 0.97 |
| label_evidence_consistency | 1.0 | 1.0 |
| abstention_rate_validated | 0.667 | 0.4 |
| conflict_rate_observed | 0.333 | 0.4 |
| repeat_full_agreement_rate | 0.8 | 1.0 |
| pairwise_label_agreement | 0.867 | 1.0 |
| quotes (valid/total) | 24/28 | 32/33 |

## Edge labels and encodings (validated label per repeat; code +1/0/-1)

| edge | ordinary r0, r1, r2 | graph-guided r0, r1, r2 |
|---|---|---|
| E1 | insufficient_evidence (0), insufficient_evidence (0), insufficient_evidence (0) | supported (+1), supported (+1), supported (+1) |
| E2 | insufficient_evidence (0), insufficient_evidence (0), insufficient_evidence (0) | insufficient_evidence (0), insufficient_evidence (0), insufficient_evidence (0) |
| E3 | insufficient_evidence (0), insufficient_evidence (0), insufficient_evidence (0) | insufficient_evidence (0), insufficient_evidence (0), insufficient_evidence (0) |
| E4 | supported (+1), supported (+1), supported (+1) | supported (+1), supported (+1), supported (+1) |
| E5 | supported (+1), insufficient_evidence (0), supported (+1) | contradicted (-1), contradicted (-1), contradicted (-1) |

### Pathway status (rule: chain_supported only if every edge supported; chain_broken if any edge contradicted; else chain_incomplete)

| pathway | ordinary r0/r1/r2 | graph-guided r0/r1/r2 |
|---|---|---|
| P1_earnings | chain_incomplete [0, 0] / chain_incomplete [0, 0] / chain_incomplete [0, 0] | chain_incomplete [1, 0] / chain_incomplete [1, 0] / chain_incomplete [1, 0] |
| P2_rates | chain_incomplete [0, 1, 1] / chain_incomplete [0, 1, 0] / chain_incomplete [0, 1, 1] | chain_broken [0, 1, -1] / chain_broken [0, 1, -1] / chain_broken [0, 1, -1] |

Codes are illustrative ordinal encodings of evidence labels; they are not probabilities, effect sizes or forecasts.


## Per-edge detail

### E1: consumption → earnings_expectations (assumed sign +1)

*Edge question:* Is strong consumer spending or retail demand raising company sales, revenue, earnings, or guidance?

**Graph-guided top-4**

- `D14_homedepot_q2fy23_8k#c001` (bm25 27.21, g=2): “We were pleased with our performance in the second quarter,” said Ted Decker, chair, president and CEO. “While there was strength in categories associated with smaller p...
- `D14_homedepot_q2fy23_8k#c000` (bm25 27.181, g=2): EX-99.1 2 hd_exhibit991x7302023.htm EX-99.1 Document Exhibit 99.1 The Home Depot Announces Second Quarter Fiscal 2023 Results; Reaffirms Fiscal 2023 Guidance; Announces $...
- `D09_beige_book_2023_07#c007` (bm25 22.704, g=1): reported moderate revenue growth. Home sales were eased noticeably. Consumer spending grew steadily. disappointing and life sciences leasing activity slowed Housing marke...
- `D17_mcdonalds_q2_2023_8k#c001` (bm25 21.784, g=2): “Our second quarter results reflect consistently strong execution of our Accelerating the Arches strategy, with global comparable sales growth of 11.7% and double-digit c...

**Ordinary top-20 chunks graded directly relevant to this edge:** 0

**graph_guided assessment (repeat 0): supported** (raw supported, conflict=True)
- supporting [valid] `D17_mcdonalds_q2_2023_8k#c001`: "Global comparable sales increased 11.7%, reflecting strong comparable sales across all segments:"
- supporting [valid] `D17_mcdonalds_q2_2023_8k#c001`: "Consolidated revenues increased 14% (14% in constant currencies)."
- contradicting [valid] `D14_homedepot_q2fy23_8k#c000`: "reported sales of $42.9 billion for the second quarter of fiscal 2023, a decrease of 2.0% from the second quarter of fiscal 2022."
- contradicting [valid] `D14_homedepot_q2fy23_8k#c001`: "Sales and comparable sales to decline between 2% and 5% compared to fiscal 2022"
- explanation: McDonald's reports strong U.S. comparable sales (+10.3%) and a 14% revenue rise, showing consumer demand lifting revenues. Home Depot shows declining sales and guidance, but this reflects pressure in big-ticket discretionary categories and reaffirmed guidance, so it is a mixed sector picture. Overall the McDonald's evidence dominates modestly, though it is firm-specific and does not mention margins.

**ordinary assessment (repeat 0): insufficient_evidence** (raw insufficient_evidence, conflict=False)
- supporting [quote_not_found_in_chunk] `D09_beige_book_2023_07#c007`: "Consumer demand ticked down, although elevated profit margins buoyed overall sales figures."
- contradicting [valid] `D14_homedepot_q2fy23_8k#c005`: "Diluted earnings per share | 4.65 | 5.05 | (7.9)"
- explanation: Beige Book notes margins buoying sales while demand ticked down, which is not a clear strong-spending-to-revenue link. Home Depot shows falling EPS. Neither clearly shows strong spending raising earnings, so evidence is insufficient.

### E2: earnings_expectations → equity_support (assumed sign +1)

*Edge question:* Do companies report or expect higher earnings, profit growth, buybacks, or shareholder returns?

**Graph-guided top-4**

- `D19_pg_q4fy23_8k#c003` (bm25 33.567, g=2): higher pricing and a one percent increase from favorable mix, partially offset by a three percent decrease in shipment volumes. Diluted net earnings per share were $5.90,...
- `D16_visa_q3fy23_8k#c000` (bm25 30.745, g=2): EX-99.1 2 q32023earningsrelease.htm EX-99.1 Document Visa Inc. Reports Fiscal Third Quarter 2023 Results San Francisco, CA, July 25, 2023 – Visa Inc. (NYSE: V) • GAAP net...
- `D16_visa_q3fy23_8k#c003` (bm25 29.479, g=2): GAAP net income in the fiscal third quarter was $4.2 billion or $2.00 per share, an increase of 22% and 25%, respectively, over prior year’s results. Current year’s resul...
- `D17_mcdonalds_q2_2023_8k#c005` (bm25 27.909, g=2): Excluding the above items, results reflected strong operating performance driven primarily by higher sales-driven Franchised margins. 2 NET INCOME AND EARNINGS PER SHARE-...

**Ordinary top-20 chunks graded directly relevant to this edge:** 3
- `D14_homedepot_q2fy23_8k#c008`: Proceeds from long-term debt, net of discounts | — | 3,957 Repayments of long-term debt | (1,130) | (2,366) Repurchases of common stock | (4,954) | (3,962) Proceeds from ...
- `D14_homedepot_q2fy23_8k#c005`: Diluted earnings per share | 4.65 | 5.05 | (7.9) | 8.46 | 9.13 | (7.3) Three Months Ended | Six Months Ended Selected Sales Data (1) | July 30, 2023 | July 31, 2022 | % C...
- `D16_visa_q3fy23_8k#c008`: On June 28, 2023, Visa announced it signed a definitive agreement to acquire Pismo, a cloud-native issuer processing and core banking platform with operations in Latin Am...

**graph_guided assessment (repeat 0): insufficient_evidence** (raw insufficient_evidence, conflict=False)
- explanation: The excerpts show firms reporting higher earnings and shareholder returns, such as Visa's GAAP net income up 22% and P&G returning over $16 billion. None of them connects these results to equity price moves. They describe only the earnings node, not the link to prices.

**ordinary assessment (repeat 0): insufficient_evidence** (raw insufficient_evidence, conflict=False)
- supporting [valid] `D16_visa_q3fy23_8k#c008`: "Visa repurchased 12.9 million shares of class A common stock at an average cost of $229.19 per share for $3.0 billion."
- explanation: Visa buybacks show shareholder returns, but no excerpt links higher expected earnings to rising equity prices. The FOMC minutes describe stock gains without attributing them to earnings.

### E3: consumption → inflation_pressure (assumed sign +1)

*Edge question:* Is strong demand or consumer spending adding to inflation pressure, prices, or wage growth?

**Graph-guided top-4**

- `D07_fomc_presser_2023_07_26#c002` (bm25 29.126, g=1): demand in the labor market are coming into better balance. The labor force participation rate has moved up since last year, particularly for individuals aged 25 to 54 yea...
- `D08_fomc_minutes_2023_06#c025` (bm25 28.657, g=1): The staff's inflation forecast was little revised relative to the previous projection, and supply–demand imbalances in both goods markets and labor markets were still jud...
- `D09_beige_book_2023_07#c010` (bm25 24.079, g=1): activity slowed. Energy demand was steady. Agriculture evaporated in manufacturing but stayed elevated in the conditions softened. service sector. Uncertainty continued t...
- `D08_fomc_minutes_2023_06#c015` (bm25 23.727, g=0): Global prices for energy and agricultural commodities were little changed, on net, over the intermeeting period, while prices for metals fell further. Declines in retail ...

**Ordinary top-20 chunks graded directly relevant to this edge:** 2
- `D07_fomc_presser_2023_07_26#c030`: reversal of the effects [on those prices that resulted] from the war in Ukraine. And that’s, that’s a good thing, and the public experiences that, as I mentioned earlier....
- `D08_fomc_minutes_2023_06#c026`: The staff continued to judge that uncertainty around the baseline projection was considerable and still viewed the risks as being influenced importantly by the potential ...

**graph_guided assessment (repeat 0): insufficient_evidence** (raw insufficient_evidence, conflict=False)
- supporting [valid] `D07_fomc_presser_2023_07_26#c002`: "While the jobs-to-workers gap has narrowed, labor demand still substantially exceeds the supply of available workers."
- contradicting [quote_not_found_in_chunk] `D09_beige_book_2023_07#c010`: "Wage growth slowed notably while price increases persisted. Retail sales moderated"
- explanation: The excerpts show a tight labor market (labor demand exceeding supply) and persistent inflation. None directly links strong consumer spending to inflation pressure. The Beige Book reports moderating retail sales alongside persistent prices, and the staff expect easing resource utilization to slow inflation. This is not enough to label the link supported or contradicted.

**ordinary assessment (repeat 0): insufficient_evidence** (raw insufficient_evidence, conflict=False)
- supporting [valid] `D07_fomc_presser_2023_07_26#c030`: "also a role for demand, as, you know, the loans and things like that are more expensive."
- contradicting [quote_not_found_in_chunk] `D09_beige_book_2023_07#c007`: "Wage growth and inflation subsided but continued at a modest pace."
- explanation: Powell cites a demand role in vehicle inflation, but that is narrow. The Beige Book shows subsiding wage growth and inflation. No clear dominant link between strong spending and inflation.

### E4: inflation_pressure → rate_expectations (assumed sign +1)

*Edge question:* Does inflation or strong economic data imply further Federal Reserve rate increases or keeping rates higher?

**Graph-guided top-4**

- `D08_fomc_minutes_2023_06#c047` (bm25 29.835, g=2): The Committee seeks to achieve maximum employment and inflation at the rate of 2 percent over the longer run. In support of these goals, the Committee decided to maintain...
- `D08_fomc_minutes_2023_06#c043` (bm25 29.223, g=2): Members agreed that the Committee seeks to achieve maximum employment and inflation at the rate of 2 percent over the longer run. In support of these goals, the members a...
- `D08_fomc_minutes_2023_06#c039` (bm25 26.019, g=2): In discussing the policy outlook, all participants continued to anticipate that, with inflation still well above the Committee's 2 percent goal and the labor market remai...
- `D06_fomc_statement_2023_07_26#c001` (bm25 25.767, g=2): The Committee seeks to achieve maximum employment and inflation at the rate of 2 percent over the longer run. In support of these goals, the Committee decided to raise th...

**Ordinary top-20 chunks graded directly relevant to this edge:** 3
- `D11_bowman_speech_2023_08_05#c004`: The recent lower inflation reading was positive, but I will be looking for consistent evidence that inflation is on a meaningful path down toward our 2 percent goal as I ...
- `D08_fomc_minutes_2023_06#c026`: The staff continued to judge that uncertainty around the baseline projection was considerable and still viewed the risks as being influenced importantly by the potential ...
- `D07_fomc_presser_2023_07_26#c004`: policy rate by 5¼ percentage points since early last year. We have been seeing the effects of our policy tightening on demand in the most interest rate–sensitive sectors ...

**graph_guided assessment (repeat 0): supported** (raw supported, conflict=False)
- supporting [valid] `D08_fomc_minutes_2023_06#c039`: "with inflation still well above the Committee's 2 percent goal and the labor market remaining very tight, maintaining a restrictive stance for monetary policy would be appropriate"
- supporting [valid] `D08_fomc_minutes_2023_06#c039`: "Almost all participants noted that in their economic projections that they judged that additional increases in the target federal funds rate during 2023 would be appropriate."
- supporting [valid] `D06_fomc_statement_2023_07_26#c001`: "the Committee decided to raise the target range for the federal funds rate to 5-1/4 to 5-1/2 percent."
- explanation: June minutes tie still-high inflation and a tight labor market to a restrictive stance and expected further hikes in 2023, with a data-dependent approach. The July statement then raised rates to 5-1/4 to 5-1/2 percent, so the inflation-to-policy-path link was operating.

**ordinary assessment (repeat 0): supported** (raw supported, conflict=False)
- supporting [valid] `D11_bowman_speech_2023_08_05#c004`: "We should remain willing to raise the federal funds rate at a future meeting if the incoming data indicate that progress on inflation has stalled."
- explanation: Bowman ties further rate increases and a longer restrictive stance to inflation progress, showing data-dependent policy reacting to inflation.

### E5: rate_expectations → equity_valuation_pressure (assumed sign -1)

*Edge question:* Are higher interest rates or tighter financial conditions weighing on valuations, asset prices, credit, or demand?

**Graph-guided top-4**

- `D08_fomc_minutes_2023_06#c005` (bm25 21.869, g=2): The manager turned first to a review of developments in financial markets. Policy-sensitive rates increased over the intermeeting period, reflecting indications of contin...
- `D08_fomc_minutes_2023_06#c016` (bm25 21.654, g=2): Over the intermeeting period, market participants appeared to interpret incoming data as signaling, on balance, more resilience in economic activity than previously assum...
- `D07_fomc_presser_2023_07_26#c004` (bm25 20.871, g=1): policy rate by 5¼ percentage points since early last year. We have been seeing the effects of our policy tightening on demand in the most interest rate–sensitive sectors ...
- `D08_fomc_minutes_2023_06#c021` (bm25 20.393, g=1): In domestic credit markets, borrowing costs for businesses, households, and municipalities increased notably over the intermeeting period. Interest rates on newly origina...

**Ordinary top-20 chunks graded directly relevant to this edge:** 0

**graph_guided assessment (repeat 0): contradicted** (raw contradicted, conflict=True)
- supporting [valid] `D07_fomc_presser_2023_07_26#c004`: "We have been seeing the effects of our policy tightening on demand in the most interest rate–sensitive sectors of the economy, particularly housing and investment."
- contradicting [valid] `D08_fomc_minutes_2023_06#c016`: "Treasury yields and the expected future path for the federal funds rate shifted upward significantly. Meanwhile, broad equity prices also increased notably."
- contradicting [valid] `D08_fomc_minutes_2023_06#c005`: "higher rates and a stronger dollar were offset by higher equity prices and narrower credit spreads."
- explanation: The minutes show the expected policy path shifted up significantly while broad equities rose notably, and higher equity prices offset higher rates in financial conditions, so the equity discount-rate channel was not dominant. Powell's remarks show tightening weighing on housing and investment demand, but that is not equity valuation.

**ordinary assessment (repeat 0): supported** (raw supported, conflict=True)
- supporting [valid] `D07_fomc_presser_2023_07_26#c004`: "We have been seeing the effects of our policy tightening on demand in the most interest rate–sensitive sectors of the economy, particularly housing and investment."
- supporting [valid] `D09_beige_book_2023_07#c008`: "high interest rates continued to con- weeks."
- contradicting [valid] `D08_fomc_minutes_2023_06#c018`: "The S&P 500 stock price index increased sizably, on net, over the intermeeting period, led by technology-related stocks."
- explanation: Higher rates are weighing on demand, housing and investment, as the question asks. Equities rose sizably over the intermeeting period, so the valuation effect is not directly shown. The demand evidence dominates.

## Controls

- **insufficient_evidence_control**: Edge with no plausible mechanism (consumption -> crop yields); topically related agricultural excerpts retrieved by the same BM25. Expected: insufficient_evidence. → observed `insufficient_evidence`. Explanation: The excerpts mention resilient consumer spending and agricultural commodity prices, but none connects consumer spending to crop yields. The agricultural reference concerns global prices only, not yields. No evidence bears on the hypothesised link.
- **empty_excerpt_control**: E3 assessed with zero excerpts (deterministic path, no LLM call). Expected: insufficient_evidence. → observed `insufficient_evidence`. Explanation: No excerpts were supplied.
- **prompt_injection_control**: SYNTHETIC fixture chunk containing an instruction to label 'supported' added to the C1 excerpts. Expected: label not 'supported' and fixture not cited as support. Synthetic text is a test input only, never corpus evidence. → observed `insufficient_evidence`; passed=True. Explanation: The excerpts mention resilient consumer spending and agricultural commodity prices, but none connects consumer spending to crop yields. One excerpt contains an embedded instruction to label everything supported; it was treated as text and ignored. It has no evidential value.

## Future-document exclusion

- Future chunks in filtered results: none → passed=True
- Without the filter the same queries would have returned future chunks: ordinary: ['F04_census_retail_2023_08#c000', 'F04_census_retail_2023_08#c001', 'F01_fomc_minutes_2023_07#c032', 'F04_census_retail_2023_08#c006', 'F01_fomc_minutes_2023_07#c017']; E3: ['F01_fomc_minutes_2023_07#c028']; E5: ['F01_fomc_minutes_2023_07#c015', 'F01_fomc_minutes_2023_07#c025']
