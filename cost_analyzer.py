import pandas as pd


class CostEstimator:
    """
    Generates a master BOM with raw vs manufacturing cost breakdown.
    """

    def __init__(self):
        self.material_db = {
            "Magnets (HTS)": {"raw_cost_per_kg": 1200.0, "mfg_multiplier": 5.0},
            "Vessel (Titanium)": {"raw_cost_per_kg": 40.0, "mfg_multiplier": 3.5},
            "Shielding (Tungsten)": {"raw_cost_per_kg": 80.0, "mfg_multiplier": 1.4},
            "RF System (GaN)": {"raw_cost_per_kg": 300.0, "mfg_multiplier": 4.0},
            "Structure (Inconel)": {"raw_cost_per_kg": 60.0, "mfg_multiplier": 2.2},
            "Radiators (Aluminum)": {"raw_cost_per_kg": 6.0, "mfg_multiplier": 1.4},
            "RF Antenna (Copper)": {"raw_cost_per_kg": 25.0, "mfg_multiplier": 2.5},
            "Copper Hardware": {"raw_cost_per_kg": 20.0, "mfg_multiplier": 2.0},
            "Aluminum 6061": {"raw_cost_per_kg": 6.0, "mfg_multiplier": 1.4},
            "Copper": {"raw_cost_per_kg": 20.0, "mfg_multiplier": 2.0},
            "Stainless Steel 316L": {"raw_cost_per_kg": 8.0, "mfg_multiplier": 2.2},
        }

    def _material_lookup(self, component):
        if "Magnet Conductor" in component:
            return "Magnets (HTS)"
        if "Magnet Structure" in component:
            return "Structure (Inconel)"
        if "Shielding" in component:
            return "Shielding (Tungsten)"
        if "RF System" in component:
            return "RF System (GaN)"
        if "Radiators" in component:
            return "Radiators (Aluminum)"
        if "RMF" in component or "Antenna" in component:
            return "RF Antenna (Copper)"
        if "Bias Ring" in component or "Ring" in component:
            return "Copper Hardware"
        return "Vessel (Titanium)"

    def generate_bom(self, masses: dict) -> pd.DataFrame:
        columns = [
            "Component",
            "Material",
            "Mass",
            "Raw Cost",
            "Mfg Cost",
            "Value Added",
            "Total Cost",
        ]
        rows = []
        for component, mass in masses.items():
            material = self._material_lookup(component)
            mat = self.material_db[material]
            raw_cost = mass * mat["raw_cost_per_kg"]
            mfg_cost = raw_cost * mat["mfg_multiplier"]
            value_added = mfg_cost - raw_cost
            total_cost = mfg_cost
            rows.append(
                {
                    "Component": component,
                    "Material": material,
                    "Mass": mass,
                    "Raw Cost": raw_cost,
                    "Mfg Cost": mfg_cost,
                    "Value Added": value_added,
                    "Total Cost": total_cost,
                }
            )

        if not rows:
            return pd.DataFrame(columns=columns)
        df = pd.DataFrame(rows)
        return df.sort_values("Total Cost", ascending=False).reset_index(drop=True)

    def generate_bom_from_fusion_csv(self, csv_path: str) -> pd.DataFrame:
        columns = [
            "Component",
            "Material",
            "Mass",
            "Raw Cost",
            "Mfg Cost",
            "Value Added",
            "Total Cost",
        ]
        try:
            df = pd.read_csv(csv_path)
        except Exception:
            return pd.DataFrame(columns=columns)

        rows = []
        for _, row in df.iterrows():
            component = str(row.get("Component", "")).strip()
            material = str(row.get("Material", "")).strip()
            mass_g = float(row.get("Mass (g)", 0.0))
            if not component or material == "N/A":
                continue
            mass_kg = mass_g / 1000.0
            mat = self.material_db.get(material)
            if not mat:
                # Fallback to generic material buckets
                if "Copper" in material:
                    mat = self.material_db["Copper"]
                elif "Aluminum" in material:
                    mat = self.material_db["Aluminum 6061"]
                elif "Steel" in material:
                    mat = self.material_db["Stainless Steel 316L"]
                else:
                    mat = self.material_db["Vessel (Titanium)"]
            raw_cost = mass_kg * mat["raw_cost_per_kg"]
            mfg_cost = raw_cost * mat["mfg_multiplier"]
            value_added = mfg_cost - raw_cost
            rows.append(
                {
                    "Component": component,
                    "Material": material,
                    "Mass": mass_kg,
                    "Raw Cost": raw_cost,
                    "Mfg Cost": mfg_cost,
                    "Value Added": value_added,
                    "Total Cost": mfg_cost,
                }
            )

        if not rows:
            return pd.DataFrame(columns=columns)
        out = pd.DataFrame(rows)
        return out.sort_values("Total Cost", ascending=False).reset_index(drop=True)

