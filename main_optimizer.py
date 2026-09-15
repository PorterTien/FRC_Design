import math
import os
from datetime import datetime

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.optimize import differential_evolution

from cost_analyzer import CostEstimator
from physics_engine import FuturePhysicsEngine
from tech_gap_analyzer import TechGapAnalyzer


class DFDOptimizer:
    def __init__(self, random_seed=42, enforce_tech_limits=True, enable_cad=True):
        self.rng = np.random.default_rng(random_seed)
        self.engine = FuturePhysicsEngine()
        self.costs = CostEstimator()
        self.gaps = TechGapAnalyzer()
        self.history = []
        self.enforce_tech_limits = enforce_tech_limits
        self.enable_cad = False

        self.bounds = [
            (0.2, 2.0),   # r
            (1.0, 20.0),  # L
            (5.0, 30.0),  # B
            (10.0, 150.0),  # Ti (keV)
            (0.2, 5.0),   # He3:D ratio
            (0.01, 2.0),  # m_dot (kg/s)
        ]

    def _seed_population(self, popsize):
        ndim = len(self.bounds)
        total = popsize * ndim
        pop = np.zeros((total, ndim))
        for i in range(total):
            for j, (low, high) in enumerate(self.bounds):
                pop[i, j] = self.rng.uniform(low, high)

        # Seed with Helion Polaris-inspired parameters
        pop[0, :] = np.array([0.5, 4.0, 12.0, 40.0, 1.0, 0.2])
        return pop

    def objective(self, x):
        r, L, B, ti_keV, ratio, m_dot = x
        result = self.engine.evaluate(r, L, B, ti_keV, ratio, m_dot)
        score, difficulty = self._score_result(r, L, B, result)
        if score is None:
            return 1e9

        specs = {
            "B": B,
            "wall_heat_flux": result.wall_heat_flux,
            "current_density": result.current_density,
            "rf_specific_mass": result.rf_specific_mass,
        }
        self.history.append((result.twr, difficulty))
        # Hard tech caps to force a specific, buildable design when enabled.
        if self.enforce_tech_limits:
            penalties = 0.0
            for key, limit in self.gaps.limits.items():
                req = {
                    "Max B-Field (T)": specs["B"],
                    "Max Wall Heat Flux (MW/m2)": specs["wall_heat_flux"] / 1e6,
                    "Max Current Density (A/mm2)": specs["current_density"] / 1e6,
                    "RF Specific Mass (kg/kW)": specs["rf_specific_mass"],
                }[key]
                if req > limit:
                    penalties += (req - limit) * 1e3
            return -(score) + penalties
        return -score

    def _score_result(self, r, L, B, result):
        if not np.isfinite(result.twr) or result.twr <= 0:
            return None, None
        if not np.isfinite(result.isp) or result.isp <= 0:
            return None, None
        if result.stability_risk >= 1000.0:
            return None, None

        specs = {
            "B": B,
            "wall_heat_flux": result.wall_heat_flux,
            "current_density": result.current_density,
            "rf_specific_mass": result.rf_specific_mass,
        }
        difficulty = self.gaps.difficulty_score(specs)
        stability_risk = result.stability_risk
        score = (result.twr * math.log10(max(result.isp, 1.0))) / (
            1.0 + stability_risk + difficulty / 50.0
        )
        return score, difficulty

    def _fallback_search(self, samples=400):
        best = None
        best_score = -float("inf")
        best_x = None
        for _ in range(samples):
            x = []
            for low, high in self.bounds:
                x.append(self.rng.uniform(low, high))
            r, L, B, ti_keV, ratio, m_dot = x
            result = self.engine.evaluate(r, L, B, ti_keV, ratio, m_dot)
            score, _ = self._score_result(r, L, B, result)
            if score is not None and score > best_score:
                best_score = score
                best = result
                best_x = x
        return best_x, best

    def run(self):
        popsize = 15
        init_pop = self._seed_population(popsize)
        solution = differential_evolution(
            self.objective,
            self.bounds,
            maxiter=40,
            popsize=popsize,
            init=init_pop,
            polish=True,
            seed=42,
        )

        r, L, B, ti_keV, ratio, m_dot = solution.x
        result = self.engine.evaluate(r, L, B, ti_keV, ratio, m_dot)

        if not result.masses or not np.isfinite(result.twr) or result.twr <= 0:
            alt_x, alt_result = self._fallback_search(samples=500)
            if alt_result is None:
                print(
                    "\nOptimizer converged to an invalid design. Try widening bounds or "
                    "disabling tech limits with --no-tech-limits."
                )
                return solution, result
            r, L, B, ti_keV, ratio, m_dot = alt_x
            result = alt_result

        dashboard = {
            "Thrust (N)": result.thrust,
            "TWR": result.twr,
            "Isp (s)": result.isp,
            "Q_plasma": result.q_plasma,
            "Q_engineering": result.q_engineering,
            "Fuel Burn D (kg/yr)": result.fuel_burn_kg_per_year["D"],
            "Fuel Burn He3 (kg/yr)": result.fuel_burn_kg_per_year["He3"],
            "Stored Energy (J)": result.stored_energy,
            "Wall Heat Flux (MW/m2)": result.wall_heat_flux / 1e6,
            "Neutron Rate (1/s)": result.details.get("Neutron_Rate_per_s", float("nan")),
            "Scintillator Rate (1/s)": result.details.get("Scintillator_Detected_per_s", float("nan")),
            "Specific Power (kW/kg)": result.details.get("Specific_Power_kW_per_kg", float("nan")),
            "Specific Power alpha (kg/kW)": result.details.get("Specific_Power_alpha_kg_per_kW", float("nan")),
            "Divertor Heat Flux (MW/m2)": result.details.get("q_divertor_W_m2", float("nan")) / 1e6,
            "Synchrotron Power (MW)": result.details.get("P_syn_W", float("nan")) / 1e6,
            "RMF Penetration (m)": result.details.get("RMF_Penetration_m", float("nan")),
            "RMF Penetration OK": result.details.get("RMF_Penetration_OK", False),
            "S-Factor": result.details["S_factor"],
            "Elongation": result.details["Elongation"],
            "Total Mass (kg)": result.details.get("Total_Mass_kg", float("nan")),
        }

        df_dashboard = pd.DataFrame([dashboard])

        fusion_bom_path = os.path.join("DFD_fusion360", "DFD_Thruster_Materials_Stats.csv")
        if os.path.exists(fusion_bom_path):
            bom = self.costs.generate_bom_from_fusion_csv(fusion_bom_path)
            bom_source = "Fusion 360 materials CSV"
        else:
            bom = self.costs.generate_bom(result.masses)
            bom_source = "Physics mass model"
        total_cost = bom["Total Cost"].sum()
        unit_cost_str = f"${total_cost:,.0f}"

        specs = {
            "B": B,
            "wall_heat_flux": result.wall_heat_flux,
            "current_density": result.current_density,
            "rf_specific_mass": result.rf_specific_mass,
        }
        gap_table = self.gaps.analyze(specs)
        design_description = self._design_description(
            r, L, B, ti_keV, ratio, m_dot, result
        )

        cad_error = "STEP CAD generation disabled (Fusion 360 model is source of truth)."

        # Persist the optimized design for specificity and traceability.
        design_row = {
            "r": r,
            "L": L,
            "B": B,
            "Ti_keV": ti_keV,
            "He3_to_D": ratio,
            "m_dot": m_dot,
            "Te_keV": result.details["Te_keV"],
            "Thrust_N": result.thrust,
            "Isp_s": result.isp,
            "TWR": result.twr,
            "Q_plasma": result.q_plasma,
            "Q_engineering": result.q_engineering,
            "Wall_Heat_Flux_MW_m2": result.wall_heat_flux / 1e6,
            "S_factor": result.details["S_factor"],
            "Elongation": result.details["Elongation"],
            "Shield_Thickness_m": result.details["Shield_Thickness_m"],
            "Radiator_Area_m2": result.details["Radiator_Area_m2"],
            "Total_Mass_kg": result.details.get("Total_Mass_kg", float("nan")),
            "Unit_Cost_USD": total_cost,
            "Neutron_Rate_per_s": result.details.get("Neutron_Rate_per_s", float("nan")),
            "Scintillator_Detected_per_s": result.details.get("Scintillator_Detected_per_s", float("nan")),
            "Scintillator_Area_m2": result.details.get("Scintillator_Area_m2", float("nan")),
            "Scintillator_Distance_m": result.details.get("Scintillator_Distance_m", float("nan")),
            "Scintillator_Efficiency": result.details.get("Scintillator_Efficiency", float("nan")),
            "Specific_Power_kW_per_kg": result.details.get("Specific_Power_kW_per_kg", float("nan")),
            "RMF_Field_T": result.details.get("RMF_Field_T", float("nan")),
            "Specific_Power_alpha_kg_per_kW": result.details.get("Specific_Power_alpha_kg_per_kW", float("nan")),
            "q_divertor_W_m2": result.details.get("q_divertor_W_m2", float("nan")),
            "P_syn_W": result.details.get("P_syn_W", float("nan")),
            "RMF_Penetration_m": result.details.get("RMF_Penetration_m", float("nan")),
            "RMF_Penetration_OK": result.details.get("RMF_Penetration_OK", False),
        }
        design_df = pd.DataFrame([design_row])
        design_df.to_csv("optimized_design.csv", index=False)

        report_path = self._write_report(
            df_dashboard=df_dashboard,
            bom=bom,
            unit_cost_str=unit_cost_str,
            gap_table=gap_table,
            design_description=design_description,
            design_df=design_df,
            equations=self.engine.equations_summary(),
            bom_source=bom_source,
            cad_error=cad_error if "cad_error" in locals() else None,
        )

        # Plot Pareto frontier (TWR vs Difficulty)
        if self.history:
            twr_vals = [h[0] for h in self.history]
            diff_vals = [h[1] for h in self.history]
            plt.figure(figsize=(7, 5))
            plt.scatter(diff_vals, twr_vals, alpha=0.6)
            plt.xlabel("Difficulty Score")
            plt.ylabel("TWR")
            plt.title("Pareto Frontier: TWR vs Difficulty")
            plt.grid(True, alpha=0.3)
            plt.tight_layout()
            plt.savefig("pareto_frontier.png", dpi=150)

        print(f"\nReport saved to: {report_path}")
        return solution, result

    def _design_description(self, r, L, B, ti_keV, ratio, m_dot, result):
        return (
            "This optimized D-He3 Field-Reversed Configuration (FRC) uses a cylindrical"
            f" plasma chamber with radius {r:.2f} m and length {L:.2f} m, confined by a"
            f" {B:.1f} T axial magnetic field. The plasma operates at an ion temperature"
            f" of {ti_keV:.1f} keV and a D:He3 ratio of 1:{ratio:.2f}, with propellant"
            f" injected at {m_dot:.3f} kg/s. The beta-limited plasma pressure is balanced"
            " by the magnetic pressure, and the electron temperature is solved to satisfy"
            " heating-cooling equilibrium (alpha + auxiliary heating vs bremsstrahlung and"
            " ion-electron drag). Charged fusion products are magnetically expanded through"
            " the rear nozzle to generate thrust, while the neutron fraction drives the"
            " shielding and radiator sizing. Stability is enforced via the S-factor"
            " (tilt instability) and elongation (tearing mode) constraints. The system"
            f" produces ~{result.thrust:,.0f} N of thrust at ~{result.isp:,.0f} s Isp with"
            f" a total dry mass of ~{result.details['Total_Mass_kg']:,.0f} kg."
        )

    def _write_report(
        self,
        df_dashboard,
        bom,
        unit_cost_str,
        gap_table,
        design_description,
        design_df,
        equations,
        bom_source=None,
        cad_error=None,
    ):
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        report_name = "dfd_report.html"
        report_path = os.path.abspath(report_name)

        css = """
        <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 32px; color: #111; }
        h1, h2 { color: #0b3d91; }
        table { border-collapse: collapse; width: 100%; margin: 12px 0 24px; }
        th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
        th { background: #f4f6f8; }
        .note { color: #555; font-size: 0.95em; }
        code { background: #f4f6f8; padding: 2px 4px; border-radius: 4px; }
        </style>
        """

        sections = [
            f"<h1>DFD Inverse Design Report</h1><p class='note'>Generated {timestamp}</p>",
            "<h2>Mission-Ready Engineering Dashboard</h2>",
            df_dashboard.to_html(index=False, border=0),
            "<h2>Master Bill of Materials (BOM)</h2>",
            f"<p class='note'>BOM source: {bom_source or 'Unknown'}</p>",
            bom.to_html(index=False, border=0),
            f"<p><strong>Unit Cost:</strong> {unit_cost_str}</p>",
            "<h2>Technology Gap Report</h2>",
            gap_table.to_html(index=False, border=0),
            "<h2>Design Description</h2>",
            f"<p>{design_description}</p>",
            "<h2>Equations Used</h2>",
            "<ul>" + "".join(f"<li>{eq}</li>" for eq in equations) + "</ul>",
            "<h2>Optimized Design Parameters</h2>",
            design_df.to_html(index=False, border=0),
            "<h2>Outputs</h2>",
            "<p>CAD: <code>Fusion 360 (DFD_fusion360/fusion360_dfd_thruster.py)</code></p>",
            "<p>Pareto plot: <code>pareto_frontier.png</code></p>",
        ]
        if cad_error:
            sections.append(f"<p class='note'>{cad_error}</p>")

        with open(report_path, "w", encoding="utf-8") as f:
            f.write(css + "\n".join(sections))

        return report_path


def quickstart(enforce_tech_limits=True, random_seed=42, enable_cad=True):
    """
    One-call entry point to run the optimizer and produce all outputs.
    Returns the optimization solution and physics result.
    """
    optimizer = DFDOptimizer(
        random_seed=random_seed,
        enforce_tech_limits=enforce_tech_limits,
        enable_cad=enable_cad,
    )
    return optimizer.run()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run the DFD optimizer.")
    parser.add_argument("--no-cad", action="store_true", help="Disable CAD output.")
    parser.add_argument(
        "--no-tech-limits", action="store_true", help="Disable tech limit enforcement."
    )
    parser.add_argument("--seed", type=int, default=42, help="Random seed.")
    args = parser.parse_args()

    quickstart(
        enforce_tech_limits=not args.no_tech_limits,
        random_seed=args.seed,
        enable_cad=not args.no_cad,
    )

