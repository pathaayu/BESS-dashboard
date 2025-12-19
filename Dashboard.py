import streamlit as st
import pandas as pd

# --------------------------------------------------
# PAGE CONFIG
# --------------------------------------------------
st.set_page_config(
    page_title="Jhagadiya BESS Decision Dashboard",
    layout="wide"
)

st.title("🔋 Jhagadiya BESS Decision Dashboard")
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
# SIDEBAR CONTROLS
# --------------------------------------------------
st.sidebar.header("⚙ Controls")

date_range = st.sidebar.date_input(
    "📅 Date Range",
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
df = df[
    (df["Datetime"].dt.date >= date_range[0]) &
    (df["Datetime"].dt.date <= date_range[1])
].copy()

# --------------------------------------------------
# BATTERY SIMULATION
# --------------------------------------------------
CAP = battery_mwh * 1000
PWR = battery_mw * 1000 / 4

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
    else:
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
# KPIs
# --------------------------------------------------
c1, c2, c3, c4, c5, c6 = st.columns(6)

c1.metric("Demand (kWh)", f"{df['Demand'].sum():,.0f}")
c2.metric("Solar (kWh)", f"{df['Solar'].sum():,.0f}")
c3.metric("Import (kWh)", f"{df['Import'].sum():,.0f}")
c4.metric("Export (kWh)", f"{df['Export'].sum():,.0f}")
c5.metric("PV → BESS (kWh)", f"{df['PV_Charge'].sum():,.0f}")
c6.metric("Grid → BESS (kWh)", f"{df['Grid_Charge'].sum():,.0f}")

# --------------------------------------------------
# DEMAND vs SOLAR
# --------------------------------------------------
st.subheader("Demand vs Solar")
st.line_chart(df.set_index("Datetime")[["Demand", "Solar"]])

# --------------------------------------------------
# BATTERY CHARGE / DISCHARGE
# --------------------------------------------------
st.subheader("Battery Charge / Discharge")
st.bar_chart(
    df.set_index("Datetime")[["PV_Charge", "Grid_Charge", "Discharge"]]
)

# --------------------------------------------------
# SOC (%)
# --------------------------------------------------
st.subheader("State of Charge (%)")
st.line_chart(df.set_index("Datetime")[["SOC_%"]])

# --------------------------------------------------
# DECISION LOGIC
# --------------------------------------------------
export_avoided_pct = (
    df["PV_Charge"].sum() / df["Export"].sum() * 100
    if df["Export"].sum() > 0 else 0
)

avg_soc = df["SOC_%"].mean()
grid_dependency = (
    df["Grid_Charge"].sum() /
    (df["PV_Charge"].sum() + df["Grid_Charge"].sum()) * 100
    if (df["PV_Charge"].sum() + df["Grid_Charge"].sum()) > 0 else 0
)

st.subheader("🧠 Decision Verdict")

if export_avoided_pct > 60 and avg_soc > 65 and grid_dependency < 40:
    st.success(
        f"✅ OPTIMAL\n\n"
        f"• Export avoided: {export_avoided_pct:.1f}%\n"
        f"• Avg SOC: {avg_soc:.1f}%\n"
        f"• Grid charging: {grid_dependency:.1f}%"
    )
else:
    st.warning(
        f"⚠ NOT OPTIMAL\n\n"
        f"• Export avoided: {export_avoided_pct:.1f}%\n"
        f"• Avg SOC: {avg_soc:.1f}%\n"
        f"• Grid charging: {grid_dependency:.1f}%\n\n"
        f"Reason: Low export utilization or high grid dependency"
    )
