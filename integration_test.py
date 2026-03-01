import sys
sys.path.insert(0, '.')

from utils.data_loader import load_from_path
df, qr = load_from_path('UAInnovateDataset-SoCo.xlsx')
print(f'OK: data_loader - {len(df)} devices')

from utils.geo_clustering import cluster_devices_by_radius, build_cluster_summary
geo_df = df[df['latitude'].notna() & df['longitude'].notna()]
clustered = cluster_devices_by_radius(geo_df, radius_miles=5)
summary = build_cluster_summary(clustered)
print(f'OK: geo_clustering - {len(summary)} clusters (5mi), ${summary["estimated_savings"].sum():,.0f} savings')

from utils.exceptions import load_exceptions
exc = load_exceptions()
print(f'OK: exceptions - {len(exc)} loaded')

print()
print('=== BUSINESS METRICS ===')
print(f'Total fleet cost:     ${df["total_cost"].sum():,.0f}')
print(f'Risk cost exposure:   ${df["risk_cost_exposure"].sum():,.0f}')
print(f'Critical devices:     {(df["risk_tier"]=="Critical").sum():,}')
print(f'Past EoL:             {df["is_past_eol"].sum():,}')
print(f'Past EoS:             {df["is_past_eos"].sum():,}')
print(f'States covered:       {df["state"].nunique()}')
print(f'Sites covered:        {df["site_name"].nunique():,}')
print(f'Lat/lon coverage:     {df["latitude"].notna().mean()*100:.1f}%')
