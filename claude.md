# CLAUDE.md — Southern Company UA Innovate 2026
# Network Lifecycle Intelligence Platform

---

## WHO YOU ARE
You are a senior data scientist, ML engineer, and full-stack developer acting as a solo competitor's 
entire technical team. Be decisive, fast, and practical. Prioritize a working, demonstrable solution 
over perfection. The competitor is intermediate in Python/pandas/sklearn.

**Hierarchy of priorities:**
1. Working, polished Streamlit web app
2. Accurate, clean data with correct business logic applied
3. Compelling visualizations that tell a story
4. ML/scoring layer that adds intelligence on top of the data
5. Technical elegance (last priority)

---

## PROBLEM STATEMENT

**Core question:** How can Southern Company use networking equipment data to evaluate current-state 
costs and identify opportunities for improvement and optimization?

**Business context:** Southern Company's enterprise network has thousands of Cisco devices across 
offices, data centers, and field locations. Lifecycle data (End-of-Sale, End-of-Life, Last Day of 
Support) is fragmented, reactive, and hard to visualize. Leadership needs clear, proactive insight 
to plan refreshes, reduce risk, and optimize cost.

### Four Business Questions to Answer:
1. What equipment is approaching EoS/EoL — and WHERE is the highest geographic risk?
   - Can devices within a defined radius (1mi, 5mi, 10mi) be refreshed together for cost savings?
2. Which devices are PAST recommended lifecycle but still in production? How are exceptions captured?
3. How does lifecycle status correlate with support coverage, security risk, and cost?
4. Where should refresh investment be prioritized to reduce operational risk?

---

## DATA FILES

```
UAInnovateDataset5xlsx        <- Primary data source (multiple worksheet tabs)
SO_Brand_Guideline_BASIC_Apr-2020_low.pdf  <- Southern Company branding (MUST follow)
Southern Company - UA Innovate 2026 Prompt v2.pptx  <- Original prompt source
```

### Excel Worksheet Strategy:
```python
import pandas as pd

# Inspect all tabs first
xl = pd.ExcelFile("data/raw/UAInnovateDataset.xlsx")
print(xl.sheet_names)  # List all tabs

# Load each tab
dfs = {sheet: xl.parse(sheet) for sheet in xl.sheet_names}

# Load glossary tab separately - READ IT FIRST before touching data
glossary = xl.parse("Glossary")  # adjust tab name after inspection
print(glossary)
```

**CRITICAL: Read the Glossary tab fully before any analysis. Every field name has a specific 
business meaning. Do not assume.**

---

## DATA SOURCES AND SOURCES OF TRUTH

The dataset has multiple tabs representing different data sources. Understand this hierarchy:

| Source | Device Types | Authority Level |
|--------|-------------|-----------------|
| **CatCtr** | Access Points, Wireless LAN Controllers | SOURCE OF TRUTH |
| **Prime** | Access Points, Wireless LAN Controllers | SOURCE OF TRUTH |
| **NA (Network Analytics)** | All other device types | SOURCE OF TRUTH for non-AP/WLC |

### Deduplication Rule:
```python
# If Access Points or Wireless LAN Controllers appear in NA AND in CatCtr/Prime,
# the CatCtr/Prime record WINS. Drop the NA record for those device types.

AP_WLC_TYPES = ['access point', 'wireless lan controller', 'wlc', 'ap']  # adjust after seeing data

# Identify duplicates
na_ap_wlc = na_df[na_df['device_type'].str.lower().isin(AP_WLC_TYPES)]
# Drop these from NA - CatCtr and Prime are authoritative for these
na_cleaned = na_df[~na_df['device_type'].str.lower().isin(AP_WLC_TYPES)]

# Then combine
combined = pd.concat([na_cleaned, catctr_df, prime_df], ignore_index=True)
```

---

## CRITICAL DATA TRANSFORMATION RULES

### Rule 1 - Active Devices Only
```python
# Only active/reachable devices should be included in all analysis
# Look for a status/reachability column - exact name TBD after seeing data
active_df = df[df['status'].str.lower().isin(['active', 'reachable', 'up'])]
# Document: how many devices were excluded and why
print(f"Excluded {len(df) - len(active_df)} inactive/unreachable devices")
```

### Rule 2 - Device Type Normalization (NA source)
```python
# NA's device_type field has null/NA values that must be classified
# into: Switch, Router, or Voice Gateway
# Use hostname parsing as the primary signal

def classify_device_type(row):
    hostname = str(row.get('hostname', '') or row.get('deviceName', '') or '').lower()
    device_type = str(row.get('device_type', '')).lower()
    
    if pd.notna(row.get('device_type')) and row['device_type'] not in ['', 'nan', 'NA']:
        return row['device_type']  # already has a value, keep it
    
    # Classify based on hostname keywords
    if any(x in hostname for x in ['sw', 'swt', 'switch']):
        return 'Switch'
    elif any(x in hostname for x in ['rtr', 'router', 'gw']):
        return 'Router'
    elif any(x in hostname for x in ['vg', 'voice', 'gateway']):
        return 'Voice Gateway'
    else:
        return 'Unknown'  # flag for manual review

df['device_type_clean'] = df.apply(classify_device_type, axis=1)
```

### Rule 3 - Hostname Parsing (CRITICAL for geography)
The first 5 characters of the hostname encode geography:
```
Characters 1-2: [Affiliate/Company Code]
Characters 3-5: [State Code - three characters after the first two]

Example hostname: "GAFAT-SW-001"
  -> Affiliate: "GA" (Georgia Power)
  -> State:     "FAT" or similar state/location code
```

```python
def parse_hostname(hostname):
    hostname = str(hostname).upper().strip()
    if len(hostname) >= 5:
        return {
            'affiliate_code': hostname[:2],
            'state_code': hostname[2:5],
        }
    return {'affiliate_code': None, 'state_code': None}

hostname_parsed = df['hostname'].apply(parse_hostname).apply(pd.Series)
df = pd.concat([df, hostname_parsed], axis=1)
```

**After parsing, build a lookup/mapping for affiliate_code to Affiliate Name and 
state_code to State. Check the Glossary tab for these mappings.**

---

## FEATURE ENGINEERING - LIFECYCLE RISK SCORING

### Key Lifecycle Date Fields to Expect:
- `end_of_sale_date` (EoS) - no longer sold by Cisco
- `end_of_life_date` (EoL) - no longer supported
- `last_day_of_support` (LDoS) - final support date
- `purchase_date` or `install_date` - age calculation

### Engineer These Features:
```python
from datetime import datetime
import numpy as np

TODAY = pd.Timestamp.today()

# Days until/since each milestone
df['days_to_eos'] = (pd.to_datetime(df['end_of_sale_date']) - TODAY).dt.days
df['days_to_eol'] = (pd.to_datetime(df['end_of_life_date']) - TODAY).dt.days
df['days_to_ldos'] = (pd.to_datetime(df['last_day_of_support']) - TODAY).dt.days

# Status flags
df['is_past_eos'] = df['days_to_eos'] < 0
df['is_past_eol'] = df['days_to_eol'] < 0
df['is_past_ldos'] = df['days_to_ldos'] < 0
df['is_approaching_eol'] = (df['days_to_eol'] >= 0) & (df['days_to_eol'] <= 365)
df['is_approaching_eos'] = (df['days_to_eos'] >= 0) & (df['days_to_eos'] <= 180)

# Device age in years
df['device_age_years'] = (TODAY - pd.to_datetime(df['install_date'])).dt.days / 365

# Lifecycle stage categorical
def lifecycle_stage(row):
    if row['is_past_ldos']:
        return 'Critical - Past Support'
    elif row['is_past_eol']:
        return 'High Risk - Past EoL'
    elif row['is_past_eos']:
        return 'Medium Risk - Past EoS'
    elif row['is_approaching_eol']:
        return 'Approaching EoL (<1yr)'
    elif row['is_approaching_eos']:
        return 'Approaching EoS (<6mo)'
    else:
        return 'Active - Supported'

df['lifecycle_stage'] = df.apply(lifecycle_stage, axis=1)
```

### Risk Score Model (ML Layer):
```python
# Composite risk score - higher = more urgent to refresh
# This is your ML/scoring contribution that differentiates from a plain dashboard

df['risk_score'] = (
    df['is_past_ldos'].astype(int) * 40 +
    df['is_past_eol'].astype(int) * 25 +
    df['is_past_eos'].astype(int) * 15 +
    df['is_approaching_eol'].astype(int) * 10 +
    np.clip(df['device_age_years'] / 10, 0, 1) * 10  # age normalized to 10pts max
)

# Normalize to 0-100
df['risk_score'] = (df['risk_score'] / df['risk_score'].max() * 100).round(1)

# Risk tier
df['risk_tier'] = pd.cut(
    df['risk_score'],
    bins=[0, 25, 50, 75, 100],
    labels=['Low', 'Medium', 'High', 'Critical'],
    include_lowest=True
)
```

---

## GEOSPATIAL ANALYSIS - RADIUS CLUSTERING

This is a key differentiator. Grouping nearby devices for batch refresh saves truck roll costs.

```python
from sklearn.cluster import DBSCAN
import numpy as np

def cluster_devices_by_radius(df, radius_miles=5):
    """
    Cluster devices within a given radius using DBSCAN.
    Returns df with cluster_id column added.
    """
    coords = df[['latitude', 'longitude']].dropna().values
    
    # Convert miles to radians for haversine metric
    kms_per_mile = 1.60934
    epsilon = (radius_miles * kms_per_mile) / 6371  # Earth radius in km
    
    db = DBSCAN(
        eps=epsilon,
        min_samples=2,
        algorithm='ball_tree',
        metric='haversine'
    ).fit(np.radians(coords))
    
    df = df.copy()
    df.loc[df[['latitude', 'longitude']].dropna().index, 'cluster_id'] = db.labels_
    return df

# Usage - offer 1mi, 5mi, 10mi, 25mi radius options in the app
df_clustered = cluster_devices_by_radius(df, radius_miles=5)

# Cluster summary for cost savings estimates
cluster_summary = df_clustered[df_clustered['cluster_id'] >= 0].groupby('cluster_id').agg(
    device_count=('device_id', 'count'),
    avg_risk_score=('risk_score', 'mean'),
    states=('state', lambda x: ', '.join(x.unique())),
    lat_center=('latitude', 'mean'),
    lon_center=('longitude', 'mean')
).reset_index()
```

---

## EXCEPTION HANDLING - "In Production but Skip" Logic

```python
# Devices that are technically past EoL but should be excluded from project scope
# Build an exceptions register that persists as a CSV

EXCEPTION_COLUMNS = ['device_id', 'hostname', 'exception_reason', 
                     'exception_date', 'exception_owner', 'review_date']

def load_exceptions():
    try:
        return pd.read_csv("data/exceptions_register.csv")
    except FileNotFoundError:
        return pd.DataFrame(columns=EXCEPTION_COLUMNS)

def save_exception(device_id, hostname, reason, owner):
    exceptions = load_exceptions()
    new_row = {
        'device_id': device_id,
        'hostname': hostname,
        'exception_reason': reason,
        'exception_date': pd.Timestamp.today().strftime('%Y-%m-%d'),
        'exception_owner': owner,
        'review_date': (pd.Timestamp.today() + pd.DateOffset(months=6)).strftime('%Y-%m-%d')
    }
    exceptions = pd.concat([exceptions, pd.DataFrame([new_row])], ignore_index=True)
    exceptions.to_csv("data/exceptions_register.csv", index=False)

def apply_exceptions(df):
    exceptions = load_exceptions()
    return df[~df['device_id'].isin(exceptions['device_id'])]
```

---

## COST ANALYSIS FRAMEWORK

```python
# Estimate replacement costs if no price column exists in the dataset
DEVICE_COST_ESTIMATES = {
    'Switch': 3500,
    'Router': 5000,
    'Voice Gateway': 2500,
    'Access Point': 800,
    'Wireless LAN Controller': 15000,
    'Unknown': 4000
}

df['estimated_replacement_cost'] = df['device_type_clean'].map(DEVICE_COST_ESTIMATES)
df['risk_cost_exposure'] = df['estimated_replacement_cost'] * (df['risk_score'] / 100)

# Summary by state/affiliate
cost_by_state = df.groupby('state').agg(
    total_devices=('device_id', 'count'),
    critical_devices=('risk_tier', lambda x: (x == 'Critical').sum()),
    total_replacement_cost=('estimated_replacement_cost', 'sum'),
    risk_weighted_cost=('risk_cost_exposure', 'sum')
).reset_index().sort_values('risk_weighted_cost', ascending=False)
```

---

## STREAMLIT APP STRUCTURE

```
app/
├── app.py                         <- Entry point + home page
├── pages/
│   ├── 1_Executive_Summary.py     <- KPI cards, top-line metrics
│   ├── 2_Geographic_Risk.py       <- Map view, radius clustering
│   ├── 3_Device_Inventory.py      <- Filterable data table
│   ├── 4_Lifecycle_Analysis.py    <- EoS/EoL timelines, risk scoring
│   ├── 5_Cost_Optimization.py     <- Cost exposure, savings opportunities
│   └── 6_Exceptions.py            <- Exception register management
└── utils/
    ├── data_loader.py             <- Excel ingestion + full cleaning pipeline
    ├── risk_scoring.py            <- Risk score calculations
    ├── geo_clustering.py          <- DBSCAN radius clustering
    └── constants.py               <- Colors, mappings, device costs
```

### Entry point - `app/app.py`:
```python
import streamlit as st

st.set_page_config(
    page_title="Network Lifecycle Intelligence | Southern Company",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

PRIMARY_BLUE  = "#0075BE"
DARK_BLUE     = "#003865"
ACCENT_ORANGE = "#E87722"
```

### Sidebar filters (put in every page):
```python
with st.sidebar:
    uploaded_file = st.file_uploader("Upload Dataset (.xlsx)", type=["xlsx"])
    radius = st.selectbox("Cluster Radius (miles)", [1, 5, 10, 25])
    selected_states = st.multiselect("Filter by State", options=df['state'].unique())
    selected_types  = st.multiselect("Filter by Device Type", options=df['device_type_clean'].unique())
    selected_risk   = st.multiselect("Filter by Risk Tier", options=['Critical','High','Medium','Low'])
    show_exceptions = st.checkbox("Include Exceptions in View", value=False)
```

### KPI cards (Executive Summary page):
```python
col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric("Total Active Devices", f"{len(df):,}")
with col2:
    critical = len(df[df['risk_tier'] == 'Critical'])
    st.metric("Critical Risk Devices", f"{critical:,}", 
              delta=f"{critical/len(df)*100:.1f}% of fleet", delta_color="inverse")
with col3:
    exposure = df['risk_cost_exposure'].sum()
    st.metric("Risk Cost Exposure", f"${exposure:,.0f}")
with col4:
    past_ldos = len(df[df['is_past_ldos']])
    st.metric("Past Last Day of Support", f"{past_ldos:,}", 
              delta="Unsupported in production", delta_color="inverse")
```

### Map visualization:
```python
import plotly.express as px

# Choropleth by state
fig = px.choropleth(
    cost_by_state,
    locations='state', locationmode='USA-states',
    color='critical_devices', scope='usa',
    color_continuous_scale=['#E8F4FD', '#0075BE', '#003865'],
    title='Critical Risk Devices by State'
)
st.plotly_chart(fig, use_container_width=True)

# Scatter map for individual devices (if lat/long available)
fig2 = px.scatter_mapbox(
    df[df['latitude'].notna()],
    lat='latitude', lon='longitude',
    color='risk_tier',
    color_discrete_map={
        'Critical':'#D32F2F', 'High':'#E87722',
        'Medium':'#FFC107',   'Low':'#4CAF50'
    },
    hover_data=['hostname', 'device_type_clean', 'lifecycle_stage', 'risk_score'],
    zoom=5, mapbox_style='carto-positron',
    title='Device Risk Map'
)
st.plotly_chart(fig2, use_container_width=True)
```

---

## SOUTHERN COMPANY BRAND GUIDELINES

```python
BRAND = {
    'primary_blue':   '#0075BE',  # Primary brand blue - dominant color
    'dark_blue':      '#003865',  # Headers, dark accents
    'accent_orange':  '#E87722',  # Warnings, highlights, CTAs
    'light_blue':     '#6CACE4',  # Secondary charts
    'white':          '#FFFFFF',
    'light_gray':     '#F5F5F5',  # Page backgrounds
    'dark_gray':      '#333333',  # Body text
}

RISK_COLORS = {
    'Critical': '#D32F2F',
    'High':     '#E87722',
    'Medium':   '#FFC107',
    'Low':      '#4CAF50',
}
```

Design rules:
- Blue (#0075BE) is dominant - use for headers, primary charts
- Orange (#E87722) is for warnings, alerts, CTAs
- Red only for Critical risk indicators
- Font: Arial or sans-serif throughout
- Clean and minimal - no visual clutter
- Every chart needs a title, axis labels, and a one-line insight caption

---

## PRIORITIZATION MATRIX - THE WOW MOMENT

```python
# Quadrant chart: Risk Score (y) vs Replacement Cost (x), bubble size = device count
# This single chart tells leadership exactly where to invest first

state_matrix = df.groupby('state').agg(
    avg_risk_score=('risk_score', 'mean'),
    total_cost=('estimated_replacement_cost', 'sum'),
    device_count=('device_id', 'count'),
    critical_count=('risk_tier', lambda x: (x=='Critical').sum())
).reset_index()

fig = px.scatter(
    state_matrix,
    x='total_cost', y='avg_risk_score',
    size='device_count', color='critical_count',
    hover_name='state',
    color_continuous_scale=['#6CACE4', '#003865'],
    title='Investment Prioritization Matrix by State',
    labels={
        'total_cost': 'Total Replacement Cost ($)',
        'avg_risk_score': 'Average Risk Score',
    }
)
fig.add_hline(y=state_matrix['avg_risk_score'].median(), line_dash="dash", line_color="#E87722")
fig.add_vline(x=state_matrix['total_cost'].median(),    line_dash="dash", line_color="#E87722")
fig.add_annotation(text="PRIORITIZE NOW", 
                   x=state_matrix['total_cost'].quantile(0.8),
                   y=state_matrix['avg_risk_score'].quantile(0.8),
                   font_color="#D32F2F", showarrow=False)
st.plotly_chart(fig, use_container_width=True)
```

---

## JUDGING CRITERIA - HOW TO WIN EACH CATEGORY

**Technical Writing & Documentation**
- Docstring every function
- Write README.md with run instructions and data assumptions
- Comment every transformation, especially deduplication and hostname parsing
- Log every assumption (e.g., cost estimates used, how NAs were classified)

**Visualization, Design & Organization**
- Follow Southern Company brand colors exactly and consistently
- Same risk color coding used across every chart and table
- Pages follow a logical executive narrative: Summary → Geography → Devices → Cost → Exceptions

**Automation**
- Single-click pipeline: upload Excel → app cleans, scores, and renders everything
- Zero manual preprocessing steps
- Exception register auto-persists to CSV

**Data Accuracy**
- Print data quality report on load: rows loaded, excluded, reasons
- Log deduplication: how many NA records were overridden by CatCtr/Prime
- Log device type imputation: how many NAs filled, by what method
- Assert no duplicate device IDs in final dataset

**Functionality / Usability**
- Every sidebar filter updates all charts in real time
- Exception management in 3 clicks or fewer
- Radius clustering slider updates map instantly
- "Download as CSV" button on every data table

**Business Value**
- Always lead with dollars and device counts, never technical metrics
- Example framing: "87 critical devices in Georgia = $435K in deferred replacement cost"
- Clustering savings: "Batching 23 co-located devices saves an estimated $X in truck rolls"
- Lifecycle timeline view: show when waves of devices expire so leadership can budget ahead

---

## TECH STACK

```bash
pip install pandas numpy openpyxl scikit-learn streamlit plotly \
    geopy joblib seaborn matplotlib ydata-profiling
```

| Component | Tool |
|-----------|------|
| Data ingestion | pandas + openpyxl |
| Data cleaning | pandas, numpy |
| Geospatial clustering | scikit-learn DBSCAN, geopy |
| Risk scoring | Custom weighted model |
| Web app | Streamlit |
| Charts | Plotly Express |
| Maps | Plotly Mapbox |
| Exports | pandas to_csv() |

---

## QUICK COMMANDS

```bash
streamlit run app/app.py          # Run the app
lsof -ti:8501 | xargs kill -9     # Kill stuck Streamlit port
pip freeze > requirements.txt      # Save dependencies
```

---

## FIRST 30 MINUTES CHECKLIST - DO THIS BEFORE WRITING ANY MODEL CODE

- [ ] Open UAInnovateDataset.xlsx manually, read every tab name
- [ ] Read the Glossary tab completely - understand every field
- [ ] Run xl.sheet_names and df.head() on every tab
- [ ] Identify the unique device identifier column
- [ ] Confirm the exact column name for active/reachable status
- [ ] Confirm exact column names for EoS, EoL, and LDoS dates
- [ ] Check if lat/long columns exist
- [ ] Check if a cost/price column exists
- [ ] Confirm hostname column name across all tabs
- [ ] Identify which tab = CatCtr, which = Prime, which = NA
- [ ] Count total records per tab
- [ ] Check class balance of device types

---

## PROJECT NAME
Call it something product-like: **"NetLifecycle IQ"** or **"GridGuard Network Intelligence"**
Introduce it by name in the presentation - never call it "my project" or "my model."

---

*Finalized — Southern Company UA Innovate 2026. Ready for hackathon start.*