import pandas as pd


class TechGapAnalyzer:
    """
    Compares optimized reactor specs to 2026 technology limits.
    """

    def __init__(self):
        self.limits = {
            "Max B-Field (T)": 20.0,
            "Max Wall Heat Flux (MW/m2)": 10.0,
            "Max Current Density (A/mm2)": 400.0,
            "RF Specific Mass (kg/kW)": 1.5,
        }
        self.rd_paths = {
            "Max B-Field (T)": "Artificial pinning centers and HTS tapes",
            "Max Wall Heat Flux (MW/m2)": "Advanced liquid metal cooling",
            "Max Current Density (A/mm2)": "High-current HTS stabilization",
            "RF Specific Mass (kg/kW)": "Integrated solid-state RF packaging",
        }

    def analyze(self, specs: dict) -> pd.DataFrame:
        rows = []
        req_b = specs.get("B", 0.0)
        req_flux = specs.get("wall_heat_flux", 0.0) / 1e6
        req_j = specs.get("current_density", 0.0) / 1e6
        req_rf = specs.get("rf_specific_mass", 0.0)

        required = {
            "Max B-Field (T)": req_b,
            "Max Wall Heat Flux (MW/m2)": req_flux,
            "Max Current Density (A/mm2)": req_j,
            "RF Specific Mass (kg/kW)": req_rf,
        }

        for component, limit in self.limits.items():
            need = required[component]
            status = "OK" if need <= limit else "INVENT NEW"
            rd_path = "Off-the-shelf" if status == "OK" else self.rd_paths[component]
            rows.append(
                {
                    "Component": component,
                    "Current_Limit": limit,
                    "Required_Spec": need,
                    "Margin": limit - need,
                    "Status": status,
                    "Suggested_RD_Path": rd_path,
                }
            )

        return pd.DataFrame(rows)

    def difficulty_score(self, specs: dict) -> float:
        score = 0.0
        req_b = specs.get("B", 0.0)
        req_flux = specs.get("wall_heat_flux", 0.0) / 1e6
        req_j = specs.get("current_density", 0.0) / 1e6
        req_rf = specs.get("rf_specific_mass", 0.0)

        required = {
            "Max B-Field (T)": req_b,
            "Max Wall Heat Flux (MW/m2)": req_flux,
            "Max Current Density (A/mm2)": req_j,
            "RF Specific Mass (kg/kW)": req_rf,
        }

        for key, limit in self.limits.items():
            need = required[key]
            ratio = need / max(limit, 1e-9)
            score += max(0.0, ratio - 1.0) * 100.0
        return score

