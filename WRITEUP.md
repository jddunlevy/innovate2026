# GridGuard Network Intelligence
## Development Narrative & Technical Methodology
### Southern Company — UA Innovate 2026

---

## 1. Executive Overview

**GridGuard Network Intelligence** is a predictive enterprise network lifecycle management platform built for Southern Company's UA Innovate 2026 competition. The platform ingests multi-source networking equipment data, applies a composite risk scoring model, clusters co-located devices for batch refresh, and exposes a seven-page Streamlit dashboard for leadership-level decision-making.

### The Business Problem

Southern Company operates thousands of Cisco network devices — switches, routers, access points, wireless controllers, and voice gateways — across offices, data centers, and field locations spanning 19 states. Lifecycle data (End-of-Sale, End-of-Life, Last Day of Support) is fragmented across multiple inventory systems, reactive in practice, and nearly impossible to visualize at scale. As a result, planning for device refreshes is ad-hoc and expensive: devices are often replaced only after failure, without batching co-located replacements together, and without proactive budget allocation based on risk.

The four business questions driving this platform:

1. What equipment is approaching EoS/EoL — and where is the highest geographic risk? Can devices within a defined radius be refreshed together for cost savings?
2. Which devices are past recommended lifecycle but still in production, and how are exceptions tracked?
3. How does lifecycle status correlate with support coverage, security risk, and cost?
4. Where should refresh investment be prioritized to reduce operational risk?

### Key Findings (Dataset Summary)

- **15,008 active devices** across 19 states and 1,850+ sites
- **$83.8M total fleet replacement cost**
- **$24.6M risk-weighted cost exposure**
- **1,179 Critical-risk devices** — all confirmed past End of Life
- **6,004 devices** confirmed past EoS or EoL
- **9,004 devices** lack lifecycle tracking data — a significant blind spot
- **983 refresh clusters** identified at 5-mile radius → **$20.9M estimated truck-roll savings**
- **99.7% location data coverage** via SOLID site code join

---

## 2. Phase 1 — Data Exploration & Schema Understanding

### Approach: Glossary First, Code Second

Before writing a single line of transformation code, the full dataset was inspected manually. The Excel file contains eight worksheet tabs, each representing a different source system:

| Tab | Contents |
|-----|----------|
| **NA** | Network Analytics — switches, routers, voice gateways |
| **CatCtr** | Catalyst Center — access points and wireless controllers |
| **PrimeAP** | Prime Infrastructure — access points |
| **PrimeWLC** | Prime Infrastructure — wireless LAN controllers |
| **SOLID** | Site master (site name, address, city, state, zip) |
| **SOLID-Loc** | Site geo-coordinates (lat/lon, county, owner) |
| **Decom** | Decommissioned site codes to be excluded |
| **ModelData** | Cisco lifecycle dates (EoS, EoL) and cost data per model |

Every field name was verified against the Glossary tab before any transformation was applied. This prevented misidentifying column semantics — for example, the `reachabilityStatus` field in CatCtr is a hardware reachability status, distinct from an alarm status in PrimeAP, and the two require different filtering logic.

### Key Discovery: Multi-Source Overlap

The dataset has no single authoritative source for all device types. Access points and wireless controllers appear in both the NA tab and in CatCtr/Prime, with the CatCtr/Prime records containing richer hardware-level data. Switches, routers, and voice gateways are exclusively in NA. This required building an explicit source-of-truth hierarchy before combining sources.

### Key Discovery: Hostname-Encoded Geography

No explicit geographic identifier (state, site name) was present directly in the NA or CatCtr inventory records. However, every hostname followed a consistent naming convention: characters 0–1 encode the affiliate code (e.g., `GA` = Georgia Power), and characters 2–4 encode the site code (e.g., `LSB`). The site code could then be joined to SOLID-Loc to retrieve latitude, longitude, state, and county. This meant hostname parsing was not optional — it was the key that unlocked all geographic analysis.

---

## 3. Phase 2 — Data Pipeline (`utils/data_loader.py`)

The data pipeline is a 13-step function (`load_data()`) that accepts raw Excel file bytes and returns a clean, enriched DataFrame plus a quality report dictionary. It is decorated with `@st.cache_data` so it runs exactly once per file hash across the session.

### Steps 1–4: Source-Specific Ingestion

Each source required different filtering logic before it could be combined.

**NA tab** — Active devices only. The `Device Status` field was compared case-insensitively to `'active'`. Wireless Controllers were additionally excluded from the NA source (58 rows), since CatCtr is authoritative for that device type and NA records for WLCs were known to be stale. The quality report logs `na_inactive_excluded` and `na_wireless_ctrl_excluded` counts.

**CatCtr tab** — Filter to AP and WLC families only (`{'unified ap', 'wireless controller'}`), then filter to reachable devices (`reachabilityStatus IN {'reachable', 'ping reachable'}`). CatCtr contains many non-wireless device records that are out of scope for this source; those were dropped rather than overriding NA records.

**PrimeWLC tab** — Filter to `reachability == 'REACHABLE'` (uppercase). Unreachable WLC records were excluded. The quality report logs `prime_wlc_unreachable_excluded`.

**PrimeAP tab** — All records included. The AP alarm status field in PrimeAP represents application-layer alerts, not physical reachability. Filtering on alarm status would incorrectly exclude reachable-but-alarming APs, so no active/reachable filter was applied to this source. This was a deliberate decision documented in the quality report.

After per-source processing, each source's columns were normalized to a common 11-column schema (`_STANDARD_COLS`) before concatenation.

### Step 5: Deduplication by Hostname

All four sources were concatenated (15,600+ rows at this point) and deduplicated on hostname using a priority sort:

```
CatCtr (priority 0) > PrimeAP (1) > PrimeWLC (2) > NA (3)
```

Hostname was chosen as the dedup key rather than any device ID because device IDs are source-specific prefixes (`CC-`, `PA-`, `WL-`, `NA-`) and not comparable across systems. Hostname, by contrast, is a stable hardware identifier consistent across all four sources. The quality report logs `deduped_by_hostname` — the number of lower-priority records dropped when a higher-priority record for the same hostname existed.

### Step 6: Hostname Parsing → Geography

```python
affiliate_code = hostname[0:2]   # e.g., 'GA' = Georgia Power
site_code      = hostname[2:5]   # e.g., 'LSB' = site identifier
```

This was applied to all 15,000+ hostnames. The site code then served as the join key to SOLID and SOLID-Loc in the next step.

### Step 7: Decommissioned Site Exclusion

The Decom tab contains `Site Cd` values for sites that have been formally decommissioned. Even if a device from a decommissioned site passes the "active" filter (because its inventory record hasn't been cleaned up), it should be excluded from lifecycle planning. Site codes were normalized to uppercase for the comparison. The quality report logs `decom_excluded`.

### Steps 8–9: SOLID + SOLID-Loc Join

Two left joins were performed on the normalized site code:

1. **SOLID** → `site_name`, `street_address`, `city`, `state`, `zip`
2. **SOLID-Loc** → `latitude`, `longitude`, `county`, `call_group`, `owner`

Coverage reached **99.7%** on this dataset — nearly every device hostname resolved to a known site with geographic coordinates. The quality report logs `site_join_matched`, `site_join_no_match`, and `lat_lon_available`.

### Step 10: Two-Pass ModelData Join (EoS, EoL, Costs)

ModelData contains lifecycle dates and real cost data for 167 curated Cisco models. The join was performed on normalized model number strings with two passes:

**Pass 1 — Exact match.** Model strings from the device inventory were stripped and uppercased, then joined to ModelData's normalized `Model` column. This matched the majority of records.

**Pass 2 — Suffix-stripped fallback.** Many Cisco model numbers have trailing variant suffixes that differ between how Cisco's internal database lists the model and how it appears in field inventory systems (e.g., `C9300-48P-K9` in inventory vs. `C9300-48P` in ModelData). A regex pattern stripped common suffixes (`-K9`, `/K9`, `-K9M`, `-K8`, `-B`, `-E`, `-I`, `-T`, `-L`, `-S`, `-D`) before a second join attempt on unmatched rows. This two-pass strategy meaningfully improved lifecycle date coverage without sacrificing match precision.

The quality report logs `model_join_matched` and `model_join_no_match`.

### Step 11: Cost Gap Filling

For devices that still had no match after both join passes, fallback cost estimates were applied per device type using a hardcoded lookup table in `constants.py`. This was a non-negotiable requirement: the budget optimizer on Page 5 and Page 7 requires a non-zero cost for every device to compute ROI. A device with `total_cost = 0` would appear to have infinite ROI and would dominate the optimizer incorrectly.

### Steps 12–13: Risk Feature Engineering + Final Audit

Risk features were computed via `engineer_risk_features()` (see Phase 3). A final check asserts `duplicate_device_ids == 0` in the quality report.

The complete quality report (20+ metrics) is displayed on the Home page on every data load.

---

## 4. Phase 3 — Risk Scoring Model (`utils/risk_scoring.py`)

### Design Decision: Composite Score, Not a Binary Flag

A single "is past EoL" boolean flag would correctly identify the most urgent devices but would create a cliff effect — a device expiring tomorrow and a device expiring in 11 months would be treated identically. A composite score captures the gradient of urgency, which is more useful for budget prioritization.

### Score Components

| Condition | Points |
|-----------|--------|
| Past End of Life | 50 |
| Past End of Sale (not yet EoL) | 20 |
| Approaching EoL (≤ 365 days) | 15 |
| Approaching EoS (≤ 180 days) | 8 |
| Device age from uptime (0–7 pts, max at 10 yr / 3,650 days) | 7 |

Maximum possible raw score: **100 points** (a device that is past EoL, past EoS, and 10+ years old). The raw score is then normalized to 0–100 relative to the observed dataset maximum so that scores are comparable across different dataset snapshots.

### Risk Tiers

```
Critical  ≥ 75
High      ≥ 50
Medium    ≥ 25
Low       < 25
```

### Lifecycle Stage Categories (6 stages)

| Stage | Condition |
|-------|-----------|
| Critical - Past EoL | `is_past_eol == True` |
| High Risk - Past EoS | `is_past_eos == True` (and not past EoL) |
| Approaching EoL (<1yr) | `days_to_eol` between 0 and 365 |
| Approaching EoS (<6mo) | `days_to_eos` between 0 and 180 |
| Active - Supported | Has lifecycle dates; none of the above apply |
| Unknown - No Lifecycle Data | `eos_date` and `eol_date` both null |

"Unknown - No Lifecycle Data" is not an error state — it is a valid and important signal. The 9,004 devices in this category represent a genuine blind spot in the fleet's lifecycle visibility. The ML layer (Phase 8) was built specifically to address this population.

### Risk Cost Exposure

```python
risk_cost_exposure = total_cost × (risk_score / 100)
```

This metric represents the replacement cost weighted by how urgent the device's refresh need is. A $10,000 switch at risk_score 80 has $8,000 in risk exposure; a $10,000 switch at risk_score 10 has $1,000. This is the primary sorting key for executive-level prioritization.

---

## 5. Phase 4 — Geospatial Clustering (`utils/geo_clustering.py`)

### Business Motivation

When a field technician travels to a site to replace one device, the incremental cost of replacing additional devices at the same location is only the cost of the hardware — the truck roll and labor are already sunk. Batching co-located devices into a single refresh project eliminates redundant dispatches. Each additional device in a batch saves an estimated **$1,500** in truck-roll cost.

### Algorithm: DBSCAN with Haversine Distance

DBSCAN (Density-Based Spatial Clustering of Applications with Noise) was chosen over K-means for two reasons:

1. **No need to specify cluster count.** Southern Company's network spans 1,850+ sites; the number of meaningful geographic clusters is not known in advance and varies with the chosen radius.
2. **Noise handling.** Devices at isolated sites (no nearby neighbors within the radius) are labeled as noise (`cluster_id = -1`) rather than being forced into a cluster. This is the correct behavior — an isolated device should not appear in the batch savings estimate.

Geographic distance was computed using the haversine metric on coordinates converted to radians, with epsilon derived from the user-selected radius in miles. The `ball_tree` algorithm was specified for efficient neighbor lookup on geographic data.

### Cluster ID Conventions

| cluster_id | Meaning |
|------------|---------|
| -2 | No location data (lat/lon missing) |
| -1 | Noise — isolated device, no nearby neighbors within radius |
| ≥ 0 | Clustered — batch refresh candidate |

### Savings Estimate

```
estimated_savings = (device_count - 1) × $1,500
```

The cluster summary is updated in real time as the user adjusts the radius slider in the Geographic Risk and Cost Optimization pages.

---

## 6. Phase 5 — Streamlit App: Home + Executive Summary

### Architecture: Single Load, Session State

All pages read from `st.session_state["df"]` — a single DataFrame loaded once by `load_data()` on the Home page. Pages are pure consumers: they apply sidebar filters and render charts. They do not re-transform data. This clean separation was critical for performance (see Phase 7).

`@st.cache_data` on `load_data()` keys on the raw file bytes hash. Re-uploading the same file is a no-op; uploading a new file triggers a full pipeline re-run.

### Home Page

Handles auto-loading (`UAInnovateDataset-SoCo.xlsx` in the project root), upload via sidebar, and displays the quality report in an expandable section. The quality report shows all 20+ pipeline metrics: rows loaded per source, rows excluded per source and reason, dedup count, model join coverage, lat/lon coverage, and the final device count.

### Executive Summary (Page 1)

Eight KPI metric cards across two rows: total devices, critical devices, risk cost exposure, past EoL count, total fleet cost, sites covered, devices in clusters, and estimated cluster savings. Below the KPIs:

- **Risk tier donut** — proportion of fleet in each tier
- **Lifecycle stage bar chart** — device count by stage
- **Prioritization matrix scatter** (the "wow moment") — average risk score (y) vs. total replacement cost (x) by state; bubble size = device count; dashed median crosshairs; "PRIORITIZE NOW" annotation in the high-risk/high-cost quadrant

The prioritization matrix is the single chart that tells leadership exactly where to invest first.

---

## 7. Phase 6 — Pages 2–6 (Sequential Build)

### Page 2: Geographic Risk

Two map views: a choropleth by state (critical device count, Southern Company blue scale) and a scatter_mapbox of individual devices (carto-darkmatter basemap, risk tier color coding). A cascading sidebar filter lets users drill from state to county to specific sites. The radius slider runs DBSCAN on-demand and overlays cluster center markers on the device scatter map.

### Page 3: Device Inventory

Full filterable device table with 7 sidebar filters (state, affiliate, device type, risk tier, lifecycle stage, source, model). Risk score cells are styled with a gradient (green→yellow→red) using pandas Styler. "Download as CSV" button on all filtered views.

### Page 4: Lifecycle Analysis

Stacked bar chart showing devices by lifecycle stage grouped by quarter of expiration — the "expiration wave" view. A vertical line marks TODAY so leadership can see the approaching wave of expirations. A separate bar shows risk score distribution by device type.

### Page 5: Cost Optimization

Three panels: (1) risk-weighted cost exposure by state as a horizontal bar, (2) cluster savings table at the selected radius, (3) interactive budget slider that re-runs the greedy optimizer and shows which devices are selected at a given spend level, sorted by ROI ratio. Key framing: "At $5M budget, GridGuard selects N devices and eliminates $X in risk exposure — a Y:1 ROI."

### Page 6: Exceptions

Three-click exception workflow: select device from dropdown → enter reason and owner → click Save. The exception is written to `data/exceptions_register.csv` with a 6-month auto-review date. The sidebar "Include Exceptions" checkbox toggles whether excepted devices appear in all other pages' analysis.

---

## 8. Phase 7 — Performance Crisis and Resolution

### The Problem

As development progressed toward 15,000+ devices, several pages became unacceptably slow — taking 10–30 seconds to render even with caching in place. Profiling revealed the root cause: page scripts were re-applying validation logic, re-checking column types, re-running type coercions, and in some cases re-joining lookup tables against the already-cleaned `session_state["df"]`. Each page was treating the incoming DataFrame as if it were raw data rather than a clean artifact.

For example, one early version of the Device Inventory page re-applied `pd.to_datetime()` to the lifecycle date columns, re-computed lifecycle flags, and re-ran the device type normalization function — all operations that `data_loader.py` had already completed definitively during the single pipeline pass. With 15,000 rows, these redundant operations were compounding to multi-second delays per page load and per filter interaction.

### The Fix

All transformation logic was consolidated into `data_loader.py` as the single authoritative pass. Pages were simplified to trust the cleaned `session_state["df"]` completely and eliminated all secondary transformation calls. Pages became thin: filter the DataFrame by sidebar selections, format columns for display, render charts. No re-validation, no re-typing, no re-joining.

### The Result

After this refactor, all pages render in under one second after the initial `load_data()` call. The initial load (pipeline run) takes 3–5 seconds for the full 15,000-device dataset, after which everything is instant. The cache ensures this cost is paid exactly once per session.

### The Lesson

In a Streamlit data application with a non-trivial dataset, the ETL pipeline must do one complete, clean pass and produce a DataFrame that pages can consume directly. The moment a page starts re-transforming data, you have a latent performance problem that only surfaces at scale. The right architecture is: **pipeline does everything once, pages display what they receive.**

---

## 9. Phase 8 — ML Layer (`utils/ml_models.py` + Page 7)

### Motivation: 9,004 Devices in the Dark

Rule-based risk scoring is effective for the 6,004 devices with lifecycle dates — those devices get accurate scores. But 9,004 devices had no lifecycle data at all, leaving them in the "Unknown - No Lifecycle Data" stage with a risk score of 0. This is not a safe assumption — many of those devices are likely old enough to be past EoS or EoL; they simply haven't been enrolled in Cisco's lifecycle tracking system.

A machine learning layer was built to predict lifecycle status for these unknown devices using only the features available on all devices — removing the blind spot without requiring manual data enrichment.

### Capability 1: GradientBoosting Lifecycle Predictor

**Training set:** The 6,004 devices with at least one lifecycle date (EoS or EoL known).

**Target:** `is_past_eol` — binary, whether the device is confirmed past End of Life. This is a harder and more useful prediction than EoS alone.

**Feature selection rationale:** Features were restricted to fields that exist on all devices, including the 9,004 unlabeled ones. Lifecycle-derived columns (`risk_score`, `days_to_eos`, `is_past_eos`) were explicitly excluded as features — they would leak the label and are, by definition, absent on unlabeled devices. The final feature set:

```
device_type, affiliate_code, state, source,
uptime_days, total_cost, device_cost, labor_cost
```

Categorical features were label-encoded. Numeric NaNs were filled with training-set medians. At inference time, the training medians were applied to transform unlabeled rows consistently.

**Model configuration:**
```python
GradientBoostingClassifier(
    n_estimators=150,
    learning_rate=0.1,
    max_depth=4,
    subsample=0.8,
    random_state=42,
)
```

GradientBoosting was chosen over Random Forest and Logistic Regression for its stronger performance on tabular data with a small feature set (~8 features), its ability to capture non-linear interactions between device type and cost, and its interpretability through feature importance. An 80/20 stratified split was used to preserve class balance in the holdout set.

**Output for unlabeled devices:**

| Probability | Predicted Tier |
|-------------|---------------|
| ≥ 0.65 | Likely Past EoL |
| ≥ 0.40 | Likely Past EoS Only |
| < 0.40 | Likely Active |

### Capability 2: Permutation Feature Importance

Permutation importance was used rather than the default Gini/split importance provided by sklearn's `feature_importances_` attribute. The difference: Gini importance measures how often a feature was used to split a tree, which can inflate the apparent importance of high-cardinality features. Permutation importance measures the actual drop in holdout accuracy when a feature's values are randomly shuffled — a direct measure of each feature's contribution to predictive power on unseen data. Ten permutation repeats were used to produce stable importance estimates with standard deviations.

### Capability 3: IsolationForest Anomaly Detection

IsolationForest runs on the full fleet (all 15,000+ devices) using three features: `uptime_days`, `total_cost`, and `risk_score`. These three features capture the "hidden risk" story: a device that is low-scored (no lifecycle data, so risk_score ≈ 0) but has very long uptime (installed long ago) and unusually low replacement cost is a candidate anomaly — it may be an old, cheap device flying below the radar of lifecycle planning.

`contamination=0.05` designates approximately 5% of the fleet as anomalous. The raw `decision_function` output (more negative = more anomalous) was normalized to a 0–100 anomaly score for display.

Features were standardized with `StandardScaler` before fitting to prevent the cost variable (in dollars) from dominating the distance calculation over uptime (in days).

### Capability 4: Budget Optimizer (Greedy ROI)

The budget optimizer accepts a user-defined spend cap and selects devices from the Critical and High risk tiers to maximize risk exposure eliminated per dollar spent.

```
priority_ratio = risk_cost_exposure / total_cost
```

Devices are sorted descending by `priority_ratio` (best ROI first) and selected greedily until the budget is exhausted. If the budget is smaller than any single device's cost, the cheapest qualifying device is selected as a floor. The output includes cumulative cost and cumulative exposure eliminated columns for waterfall-style visualization.

### Caching Strategy

`@st.cache_resource` is used for the trained model object (in-memory, not serialized), and `@st.cache_data` is used for the prediction results. This means the model is trained once per session and predictions are computed once per model, with both persisting across page navigation.

---

## 10. Key Design Decisions & Tradeoffs

| Decision | Chosen Approach | Alternative Considered | Why |
|----------|----------------|----------------------|-----|
| Dedup key | `hostname` | Source-specific device ID | Hostname is consistent across all 4 sources; source IDs are not comparable |
| Source authority (wireless) | CatCtr > PrimeAP > PrimeWLC > NA | Merge all | CatCtr/Prime have hardware-level data with richer model strings for WLCs/APs |
| Active filter (PrimeAP) | Include all records | Filter on alarm status | Alarm status ≠ device reachability in PrimeAP; filtering would lose valid devices |
| Risk score model | Composite weighted (5 factors) | Single EoL flag | Captures gradient of urgency; enables meaningful differentiation within Critical tier |
| Lifecycle score normalization | Relative to dataset max | Fixed scale | Makes scores portable across dataset snapshots without hardcoded ceilings |
| ModelData join | Two-pass (exact + suffix-stripped) | Exact only | Suffix stripping recovers significant coverage at no accuracy cost |
| Cost model | ModelData + fallback table | ModelData only | 100% cost coverage required for budget optimizer; no device can have $0 cost |
| ML algorithm | GradientBoostingClassifier | Random Forest, Logistic Regression | Best accuracy on structured tabular data with small feature set |
| Feature importance | Permutation (holdout-based) | Gini/split importance | Permutation importance is more rigorous; unbiased toward high-cardinality features |
| Anomaly features | `uptime_days`, `total_cost`, `risk_score` | All features | Minimal, interpretable feature set targets the specific "hidden risk" narrative |
| Cluster savings metric | $(N-1) \times \$1{,}500$ | Total cost / cluster | Captures marginal savings from batching, not absolute cost |
| Page caching | `@st.cache_data` (file bytes hash) | No caching | Prevents re-running 3–5 second pipeline on every page navigation |

---

## 11. Data Quality & Assumptions Log

All assumptions are recorded here for full reproducibility and audit trail.

**Reference date:** Fixed at `2026-02-28` (competition date). All lifecycle status flags and days-to-milestone calculations use this date.

**Active device filter criteria (by source):**
- NA: `Device Status == 'Active'` (case-insensitive)
- CatCtr: `reachabilityStatus IN {'Reachable', 'Ping Reachable'}` (case-insensitive)
- PrimeWLC: `reachability == 'REACHABLE'` (uppercase exact)
- PrimeAP: all records included (alarm status does not represent device reachability)

**Decommissioned sites:** Excluded by matching hostname site code (chars 2–4) against the `Site Cd` column in the Decom tab. Match is case-insensitive uppercase.

**Wireless controller exclusion from NA:** All rows with `Device Type == 'Wireless Controller'` were removed from NA before combination. CatCtr and PrimeWLC are authoritative for this device type.

**Deduplication:** Performed on `hostname` after normalizing to uppercase. When the same hostname appeared in multiple sources, the higher-priority source's record was kept (CatCtr=0, PrimeAP=1, PrimeWLC=2, NA=3).

**Hostname geography encoding:**
- Characters `[0:2]` → affiliate code (e.g., `GA` = Georgia Power, `AL` = Alabama Power)
- Characters `[2:5]` → site code (joined to SOLID-Loc for coordinates and state)
- Hostnames shorter than 5 characters have site code set to null

**ModelData join — suffix stripping:** Regex pattern applied to unmatched model strings: `r"[/\-](K9|K9M|K8|B|E|I|T|L|S|D)$"`. This strips the most common Cisco variant suffixes to recover a base model string for the second join pass.

**Fallback cost estimates (applied when ModelData has no match):**
- Switch: from constants.py `FALLBACK_DEVICE_COST`
- Router: from constants.py `FALLBACK_DEVICE_COST`
- Voice Gateway: from constants.py `FALLBACK_DEVICE_COST`
- Access Point: from constants.py `FALLBACK_DEVICE_COST`
- Wireless LAN Controller: from constants.py `FALLBACK_DEVICE_COST`
- Unknown: from constants.py `FALLBACK_DEVICE_COST`
- Labor fallback applied similarly from `FALLBACK_LABOR_COST`

**Truck-roll savings constant:** $1,500 per additional co-located device batched into a single refresh project. This is a conservative estimate representing the marginal dispatch cost avoided (fuel, technician time, scheduling overhead for a separate trip).

**DBSCAN parameters:** `min_samples=2` (a cluster requires at least 2 devices), `algorithm='ball_tree'`, `metric='haversine'`. Epsilon derived from user-selected radius in miles: `epsilon = (radius_miles × 1.60934) / 6371`.

**IsolationForest:** `n_estimators=100`, `contamination=0.05` (5% of fleet flagged as anomalous), `random_state=42`. Features standardized with `StandardScaler` before fitting.

**GradientBoosting lifecycle predictor:** `n_estimators=150`, `learning_rate=0.1`, `max_depth=4`, `subsample=0.8`, `random_state=42`. 80/20 stratified split. Training set = devices with at least one lifecycle date (EoS or EoL not null). Target = `is_past_eol` (binary).

**Prediction probability thresholds:** `≥ 0.65` → "Likely Past EoL"; `≥ 0.40` → "Likely Past EoS Only"; `< 0.40` → "Likely Active". Thresholds chosen to match the label class distribution in the training set (approximately 20% past EoL, 40% past EoS, 40% active among labeled devices).

**Uptime-based age score:** Normalized using a 3,650-day (10-year) cap. Devices with null uptime (common for PrimeAP records) receive 0 points for this component — a conservative assumption that does not inflate their risk score.

---

## 12. Verification & Testing

### Integration Test (`integration_test.py`)

A smoke-test script runs the full pipeline from file bytes through ML inference and asserts:
- `len(df) > 0` — pipeline produces rows
- `df['device_id'].is_unique` — no duplicate device IDs
- `df['risk_score'].between(0, 100).all()` — all risk scores in valid range
- `df['risk_tier'].isin(['Low','Medium','High','Critical']).all()` — all tiers valid
- `df['total_cost'].ge(0).all()` — no negative costs
- ML training completes without exception; model accuracy is logged
- Anomaly detection produces `anomaly_score` for all rows

### Quality Report (Home Page)

Every pipeline run produces a quality report dictionary with 20+ metrics:

| Metric | What It Logs |
|--------|-------------|
| `na_raw_rows` | Rows loaded from NA tab |
| `na_inactive_excluded` | NA rows dropped (not Active) |
| `na_wireless_ctrl_excluded` | NA WLC rows dropped (CatCtr authoritative) |
| `na_active_kept` | NA rows retained |
| `catctr_raw_rows` | Rows loaded from CatCtr |
| `catctr_non_ap_wlc_excluded` | CatCtr non-wireless rows dropped |
| `catctr_unreachable_excluded` | CatCtr unreachable rows dropped |
| `catctr_ap_wlc_kept` | CatCtr rows retained |
| `prime_ap_rows` | PrimeAP rows loaded and kept |
| `prime_wlc_rows` | PrimeWLC rows loaded |
| `prime_wlc_unreachable_excluded` | PrimeWLC unreachable rows dropped |
| `prime_wlc_kept` | PrimeWLC rows retained |
| `combined_pre_dedup` | Rows before hostname dedup |
| `deduped_by_hostname` | Rows removed by dedup |
| `decom_excluded` | Rows removed (decommissioned sites) |
| `site_join_matched` | Devices matched to a SOLID site |
| `site_join_no_match` | Devices with unresolved site code |
| `lat_lon_available` | Devices with valid lat/lon |
| `model_join_matched` | Devices matched in ModelData (either pass) |
| `model_join_no_match` | Devices with no ModelData match (fallback cost applied) |
| `duplicate_device_ids` | Final assertion — should always be 0 |
| `final_device_count` | Rows in final clean DataFrame |

This report is displayed on the Home page in an expandable section on every data load, providing full transparency into every transformation decision.

### Manual Cross-Verification

Key output metrics were manually cross-checked against expected ranges:
- Total device count (15,008) verified against sum of per-source retained counts minus dedup minus decom exclusions
- Critical device count (1,179) verified by filtering `risk_tier == 'Critical'` in the raw DataFrame
- Fleet cost ($83.8M) verified by summing `total_cost` across all rows
- Cluster count (983 at 5-mile radius) verified against `cluster_id.nunique()` excluding -1 and -2

---

*GridGuard Network Intelligence — Southern Company UA Innovate 2026*
*Full source code in `app/`, `utils/`. Run instructions in README.md.*
