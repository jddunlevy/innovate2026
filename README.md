# GridGuard Network Intelligence
### Southern Company — UA Innovate 2026

**GridGuard** is a predictive lifecycle management platform for Southern Company's enterprise network — ingesting multi-source equipment data, scoring device risk, clustering co-located devices for batch refresh, and surfacing proactive investment guidance to leadership.

---

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run the app (from the project root)
streamlit run app/Home.py
```

The app auto-loads `UAInnovateDataset-SoCo.xlsx` from the project root on startup.
Upload a new file anytime via the sidebar file uploader.

---

## Project Structure

```
innovate/
├── app/
│   ├── Home.py                         ← Entry point, data quality report
│   └── pages/
│       ├── 1_Executive_Summary.py      ← KPI cards, risk breakdown, prioritization matrix
│       ├── 2_Geographic_Risk.py        ← Device map, choropleth, DBSCAN clustering
│       ├── 3_Device_Inventory.py       ← Filterable device table with risk highlighting
│       ├── 4_Lifecycle_Analysis.py     ← EoL/EoS expiration waves, risk distribution
│       ├── 5_Cost_Optimization.py      ← Cost exposure, truck-roll savings, budget optimizer
│       ├── 6_Exceptions.py             ← Exception register management (CSV-persisted)
│       └── 7_Predictive_Intelligence.py ← ML: lifecycle prediction + anomaly detection
├── utils/
│   ├── constants.py                    ← Brand colors, device type maps, cost estimates
│   ├── data_loader.py                  ← 13-step ingestion + cleaning pipeline
│   ├── risk_scoring.py                 ← Lifecycle risk feature engineering
│   ├── geo_clustering.py               ← DBSCAN radius clustering
│   ├── ml_models.py                    ← GradientBoosting predictor + IsolationForest
│   └── exceptions.py                   ← Exception register I/O
├── data/
│   └── exceptions_register.csv         ← Auto-created on first exception entry
├── UAInnovateDataset-SoCo.xlsx         ← Primary data source (place in project root)
└── requirements.txt
```

---

## Data Sources

| Source Tab | Device Types | Authority Level |
|------------|-------------|-----------------|
| **CatCtr** | Access Points, Wireless LAN Controllers | Source of truth for wireless |
| **PrimeAP** | Access Points | Source of truth for APs |
| **PrimeWLC** | Wireless LAN Controllers | Source of truth for WLCs |
| **NA** | Switches, Routers, Voice Gateways | Source of truth for wired |
| **SOLID** | Site master (address, state) | Reference |
| **SOLID-Loc** | Site geo-coordinates | Reference |
| **Decom** | Decommissioned site codes | Exclusion list |
| **ModelData** | Lifecycle dates + costs per model | Reference |

Deduplication priority when a hostname appears in multiple sources: `CatCtr > PrimeAP > PrimeWLC > NA`

---

## Key Assumptions

- Active device filter criteria differ by source — see WRITEUP.md §3 for full detail
- Reference date fixed at **2026-02-28** for reproducibility
- Hostname chars `[0:2]` = affiliate code; chars `[2:5]` = site code (joined to SOLID-Loc for lat/lon)
- ModelData joined via two passes: exact model match, then suffix-stripped fallback (`-K9`, `/K9`, etc.)
- Fallback cost estimates applied per device type when ModelData has no match
- Truck-roll savings estimated at **$1,500** per co-located device batched into a single project
- IsolationForest contamination rate: **5%**
- GradientBoosting probability thresholds: **≥0.65** → Likely Past EoL; **≥0.40** → Likely Past EoS

See **[WRITEUP.md](WRITEUP.md)** for the full development narrative, all assumptions logged, and methodology explanation.

---

## Tech Stack

| Component | Library |
|-----------|---------|
| Web app | Streamlit |
| Charts & maps | Plotly Express + Plotly Mapbox |
| Data ingestion | pandas + openpyxl |
| Geospatial clustering | scikit-learn DBSCAN (haversine) |
| ML — lifecycle predictor | scikit-learn GradientBoostingClassifier |
| ML — anomaly detection | scikit-learn IsolationForest |
| Exports | pandas `.to_csv()` |

---

*See [WRITEUP.md](WRITEUP.md) for full development narrative and methodology.*
*GridGuard Network Intelligence — Southern Company UA Innovate 2026*
