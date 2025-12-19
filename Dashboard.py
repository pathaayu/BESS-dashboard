import streamlit as st
import pandas as pd
import plotly.graph_objects as go

# --------------------------------------------------
# PAGE SETUP
# --------------------------------------------------
st.set_page_config(
    page_title="Jhagadiya BESS Decision Dashboard",
    layout="wide"
)

st.title("🔋 Jhagadiya BESS Decision Dashboard (DGVCL)")
st.caption("PV vs Grid charging | Date filter | Optimal decision logic")

# --------------------------------------------------
# LOAD DATA
# --------------------------------------------------
@st.cache_data
def load_data():
    df = pd.read_excel("Usage Data.xlsx", header=None)
    df.columns = df.iloc[1]
    df = df[2:].reset_index(drop=True)

    df = df.rename(columns={
        "Current Demand(kWh)(3000 MF)": "Demand",
        "Solar Data(50% for Jhaghadiya)": "Solar",
        "Imp": "Import",
        "Exp": "Export"
    })

    for c in ["Demand", "Solar", "Import", "Export"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)

    df["Datetime"] = pd.to_datetime(
        df["Date"].astype(str) + " " + df["Time"].astype(str)
    )

    return df

df = load_data()

# --------------------------------------------------
# SIDEBAR CONTROLS (POWER BI STYLE)
# --------------------------------------------------
st.sidebar.header("⚙ Controls")

date_range = st.sidebar.date_input(
    "📅 Select Date Range",
    [df["Datetime"].min().date(), df["Datetime"].max().date()]
)

battery_mwh = st.sidebar.selectbox(
    "🔋 Battery Size (MWh)",
    [10, 15]
)

battery_mw = 5 if battery_mwh == 10 else 7.5

charge_mode = st.sidebar.radio(
    "🔌 Charging Mode",
    ["PV ONLY", "GRID ONLY", "PV + GRID"]
)

# --------------------------------------------------
# FILTER DATA
# --------------------------------------------------
mask = (
    (df["Datetime"].dt.date >= date_range[0]) &
    (df["Datetime"].dt.date <= date_range[1])
)
df = df.loc[mask].copy()

# --------------------------------------------------
# BATTERY SIMULATION
# --------------------------------------------------
CAP = battery_mwh * 1000
PWR = battery_mw * 1000 / 4  # per 15-min

soc = 0
pv_chg, grid_chg, dis, soc_pct = [], [], [], []

for _, r in df.iterrows():
    excess = max(r["Solar"] - r["Demand"], 0)
    deficit = max(r["Demand"] - r["Solar"], 0)

    pv = grid = 0

    if charge_mode == "PV ONLY":
        pv = min(excess, PWR, CAP - soc)

    elif charge_mode == "GRID ONLY":
        grid = min(PWR, CAP - soc)

    elif charge_mode == "PV + GRID":
        pv = min(excess, PWR, CAP - soc)
        rem = PWR - pv
        if rem > 0:
            grid = min(rem, CAP - soc - pv)

    discharge = min(deficit, PWR, soc)

    soc += pv + grid - discharge

    pv_chg.append(pv)
    grid_chg.append(grid)
    dis.append(discharge)
    soc_pct.append((soc / CAP) * 100)

df["PV_Charge"] = pv_chg
df["Grid_Charge"] = grid_chg
df["Discharge"] = dis
df["SOC_%"] = soc_pct

# --------------------------------------------------
# KPI CALCULATIONS
# --------------------------------------------------
total_demand = df["Demand"].sum()
total_solar = df["Solar"].sum()
total_import = df["Import"].sum()
total_export = df["Export"].sum()
pv_to_bess = df["PV_Charge"].sum()
grid_to_bess = df["Grid_Charge"].sum()
bess_dis = df["Discharge"].sum()
avg_soc = df["SOC_%"].mean()

# --------------------------------------------------
# KPI CARDS
# --------------------------------------------------
c1, c2, c3, c4, c5, c6 = st.columns(6)

c1.metric("🔌 Demand (kWh)", f"{total_demand:,.0f}")
c2.metric("☀ Solar (kWh)", f"{total_solar:,.0f}")
c3.metric("⬆ Import (kWh)", f"{total_import:,.0f}")
c4.metric("⬇ Export (kWh)", f"{total_export:,.0f}")
c5.metric("🔋 PV → BESS (kWh)", f"{pv_to_bess:,.0f}")
c6.metric("⚡ Grid → BESS (kWh)", f"{grid_to_bess:,.0f}")

# --------------------------------------------------
# DEMAND vs SOLAR
# --------------------------------------------------
fig1 = go.Figure()
fig1.add_trace(go.Scatter(x=df["Datetime"], y=df["Demand"], name="Demand"))
fig1.add_trace(go.Scatter(x=df["Datetime"], y=df["Solar"], name="Solar"))

fig1.update_layout(
    title="Demand vs Solar",
    height=300,
    yaxis_title="kWh"
)

st.plotly_chart(fig1, use_container_width=True)

# --------------------------------------------------
# BATTERY CHARGE / DISCHARGE
# --------------------------------------------------
fig2 = go.Figure()
fig2.add_trace(go.Bar(x=df["Datetime"], y=df["PV_Charge"], name="Charge from PV"))
fig2.add_trace(go.Bar(x=df["Datetime"], y=df["Grid_Charge"], name="Charge from Grid"))
fig2.add_trace(go.Bar(x=df["Datetime"], y=-df["Discharge"], name="Discharge"))

fig2.update_layout(
    title="Battery Charge / Discharge",
    barmode="relative",
    height=300,
    yaxis_title="kWh"
)

st.plotly_chart(fig2, use_container_width=True)

# --------------------------------------------------
# SOC %
# --------------------------------------------------
fig3 = go.Figure()
fig3.add_trace(go.Scatter(
    x=df["Datetime"], y=df["SOC_%"],
    fill="tozeroy", name="SOC (%)"
))
fig3.update_layout(
    title="State of Charge (%)",
    height=300,
    yaxis=dict(range=[0, 100])
)

st.plotly_chart(fig3, use_container_width=True)

# --------------------------------------------------
# OPTIMAL DECISION LOGIC
# --------------------------------------------------
export_avoided_pct = pv_to_bess / total_export * 100 if total_export > 0 else 0
grid_dependency = grid_to_bess / (pv_to_bess + grid_to_bess) * 100 if (pv_to_bess + grid_to_bess) > 0 else 0

st.subheader("🧠 BESS Decision Verdict")

if export_avoided_pct > 60 and avg_soc > 65 and grid_dependency < 40:
    st.success(
        f"✅ OPTIMAL CONFIGURATION\n\n"
        f"• Export avoided: {export_avoided_pct:.1f}%\n"
        f"• Average SOC: {avg_soc:.1f}%\n"
        f"• Grid charging: {grid_dependency:.1f}%"
    )
else:
    st.warning(
        f"⚠ NOT OPTIMAL\n\n"
        f"• Export avoided: {export_avoided_pct:.1f}%\n"
        f"• Average SOC: {avg_soc:.1f}%\n"
        f"• Grid charging: {grid_dependency:.1f}%\n\n"
        f"Reason: Low export utilization or high grid dependency"
    )
