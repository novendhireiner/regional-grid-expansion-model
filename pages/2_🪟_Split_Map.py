import pypsa
import pandas as pd
import matplotlib.pyplot as plt
import streamlit as st

plt.style.use("bmh")

st.title("Decarbonizing Electricity Supply with PyPSA")

st.markdown("""
## Project Overview
This project models and optimizes Germany’s electricity system using PyPSA (Python for Power System Analysis). 
It allows users to:

✅ Adjust CO₂ emission limits  
✅ Modify transmission expansion costs  
✅ Optimize renewable energy generation & grid capacity  
✅ Analyze energy dispatch & system costs  
✅ Perform sensitivity analysis on CO₂ policies  

The optimization minimizes total system costs while satisfying electricity demand using renewables (solar, wind) and transmission expansion.
""")

st.sidebar.header("Model Settings")

# 1️⃣ User-Controlled CO₂ Limit
co2_limit = st.sidebar.slider("Set CO₂ Emission Limit (MtCO₂)", min_value=0, max_value=200, value=50, step=10) * 1e6  # Convert to tons

# 2️⃣ Modify Transmission Expansion Costs
transmission_cost = st.sidebar.number_input("Transmission Expansion Cost (€/MW-km)", min_value=0, value=500)

st.markdown("""
## Data Overview
This model uses:
- **Technology Costs (from PyPSA technology data, 2030)**
- **Electricity Demand (Germany 2015)**
- **Renewable Generation Time Series**
""")

# Load and Visualize Data
year = 2030
url = f"https://raw.githubusercontent.com/PyPSA/technology-data/master/outputs/costs_{year}.csv"
costs = pd.read_csv(url, index_col=[0, 1])

costs.loc[costs.unit.str.contains("/kW"), "value"] *= 1e3
costs.unit = costs.unit.str.replace("/kW", "/MW")

defaults = {
    "FOM": 0,
    "VOM": 0,
    "efficiency": 1,
    "fuel": 0,
    "investment": 0,
    "lifetime": 25,
    "CO2 intensity": 0,
    "discount rate": 0.07,
}
costs = costs.value.unstack().fillna(defaults)

costs.at["OCGT", "fuel"] = costs.at["gas", "fuel"]
costs.at["CCGT", "fuel"] = costs.at["gas", "fuel"]
costs.at["OCGT", "CO2 intensity"] = costs.at["gas", "CO2 intensity"]
costs.at["CCGT", "CO2 intensity"] = costs.at["gas", "CO2 intensity"]

def annuity(r, n):
    return r / (1.0 - 1.0 / (1.0 + r) ** n)

costs["marginal_cost"] = costs["VOM"] + costs["fuel"] / costs["efficiency"]
annuity_values = costs.apply(lambda x: annuity(x["discount rate"], x["lifetime"]), axis=1)
costs["capital_cost"] = (annuity_values + costs["FOM"] / 100) * costs["investment"]

# Display Costs Table
st.subheader("Technology Costs Overview")
st.write(costs.head())

# Load Time-Series Data
url = "https://tubcloud.tu-berlin.de/s/pKttFadrbTKSJKF/download/time-series-lecture-2.csv"
ts = pd.read_csv(url, index_col=0, parse_dates=True)
ts.load *= 1e3  # Convert load to MW
resolution = 4
ts = ts.resample(f"{resolution}h").first()

# Show Demand Time-Series
st.subheader("Electricity Demand Time Series")
fig, ax = plt.subplots()
ts.load.plot(ax=ax, figsize=(10, 4), title="Electricity Demand (MW)")
st.pyplot(fig)

st.subheader("Wind and Solar Capacity Factors")
fig, ax = plt.subplots()
ts[["onwind", "offwind", "solar"]].plot(ax=ax, figsize=(10, 4), title="Capacity Factors")
st.pyplot(fig)

# Initialize Network
n = pypsa.Network()
n.add("Bus", "electricity")
n.set_snapshots(ts.index)
n.snapshot_weightings.loc[:, :] = resolution

# Add Technologies
carriers = ["onwind", "offwind", "solar", "OCGT", "hydrogen storage underground", "battery storage"]
n.add("Carrier", carriers, co2_emissions=[costs.at[c, "CO2 intensity"] for c in carriers])

# Add Loads
n.add("Load", "demand", bus="electricity", p_set=ts.load)

# Store Initial Generator Capacities Before Optimization
initial_generator_capacities = n.generators.p_nom_opt.copy()
initial_storage_capacities = n.storage_units.p_nom_opt.copy()

# Add Generators
for tech in ["onwind", "offwind", "solar"]:
    n.add("Generator", tech, bus="electricity", carrier=tech, p_max_pu=ts[tech],
          capital_cost=costs.at[tech, "capital_cost"], marginal_cost=costs.at[tech, "marginal_cost"],
          efficiency=costs.at[tech, "efficiency"], p_nom_extendable=True)

n.add("Generator", "OCGT", bus="electricity", carrier="OCGT",
      capital_cost=costs.at["OCGT", "capital_cost"], marginal_cost=costs.at["OCGT", "marginal_cost"],
      efficiency=costs.at["OCGT", "efficiency"], p_nom_extendable=True)

# 3️⃣ Adjust Transmission Expansion (Placeholder - Modify in Future)
n.add("Link", "Transmission", bus0="electricity", bus1="electricity",
      p_nom_extendable=True, capital_cost=transmission_cost)

# 4️⃣ Optimize Model
st.sidebar.subheader("Run Optimization")
if st.sidebar.button("Optimize System"):
    # Set CO2 Limit
    n.add("GlobalConstraint", "CO2Limit", carrier_attribute="co2_emissions", sense="<=", constant=co2_limit)

    # Solve Optimization
    n.optimize(solver_name="highs")

    # 5️⃣ Show Before and After Optimization
    st.header("Generator Capacities: Before vs After Optimization")
    comparison_df = pd.DataFrame({
        "Before Optimization": initial_generator_capacities,
        "After Optimization": n.generators.p_nom_opt
    })
    st.write(comparison_df)

    st.header("Storage Capacities: Before vs After Optimization")
    storage_comparison_df = pd.DataFrame({
        "Before Optimization": initial_storage_capacities,
        "After Optimization": n.storage_units.p_nom_opt
    })
    st.write(storage_comparison_df)

    # Show System Cost Breakdown
    def system_cost(n):
        tsc = pd.concat([n.statistics.capex(), n.statistics.opex()], axis=1)
        return tsc.sum(axis=1).droplevel(0).div(1e9).round(2)  # billion €/a

    st.subheader("System Cost Breakdown")
    fig, ax = plt.subplots()
    system_cost(n).plot.pie(ax=ax, figsize=(4, 4))
    st.pyplot(fig)

    # Save Results
    n.export_to_netcdf("network-new.nc")
    st.success("Optimization Completed! Results Saved.")

st.markdown("""
## Results Analysis
- **Before Optimization:** Shows initial capacities before the solver runs.
- **After Optimization:** Displays optimized capacities after the model balances cost and emissions constraints.
""")
