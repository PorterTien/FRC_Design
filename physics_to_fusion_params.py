import json
import math
from pathlib import Path

import pandas as pd

from physics_engine import FuturePhysicsEngine


def _load_design_inputs(path: Path) -> dict:
    if path.exists():
        df = pd.read_csv(path)
        if not df.empty:
            row = df.iloc[0].to_dict()
            return {
                "r": float(row.get("r", 0.2)),
                "L": float(row.get("L", 10.0)),
                "B": float(row.get("B", 10.0)),
                "Ti_keV": float(row.get("Ti_keV", 10.0)),
                "He3_to_D": float(row.get("He3_to_D", 1.0)),
                "m_dot": float(row.get("m_dot", 0.2)),
            }
    # Defaults if no optimized design exists
    return {
        "r": 0.25,  # Acta Astronautica 2014: 0.25 m plasma radius
        "L": 5.0,  # Acta Astronautica 2014: 5 m length
        "B": 4.7,  # Acta Astronautica 2014: 4.7 T axial field
        "Ti_keV": 100.0,  # DFD core target
        "He3_to_D": 1.0,
        "m_dot": 0.2,
    }


def _derive_cad_params(physics: FuturePhysicsEngine, result, inputs: dict) -> dict:
    # Basic geometry mapping from physics results (meters -> mm)
    r_m = inputs["r"]
    L_m = inputs["L"]
    bore_radius_mm = r_m * 1000.0
    outer_radius_mm = bore_radius_mm + 4.0  # base wall

    # Structural sizing driven by magnetic pressure and material stress
    pressure = (inputs["B"] ** 2) / (2 * physics.mu0)
    allowable = physics.materials["Inconel"]["allowable_stress_pa"]
    structure_thickness_m = pressure / max(allowable, 1.0)
    wall_thickness_mm = max(2.0, structure_thickness_m * 1000.0)

    # Shield thickness driven by wall heat flux
    shield_thickness_mm = max(2.0, result.details["Shield_Thickness_m"] * 1000.0)

    # Coil sizing driven by B-field (simple proxy)
    coil_inner_mm = outer_radius_mm + 5.0
    coil_outer_mm = coil_inner_mm + max(12.0, inputs["B"] * 2.0)

    chamber_length_mm = max(200.0, L_m * 1000.0 * 0.6)
    outer_length_mm = max(400.0, L_m * 1000.0)
    nozzle_length_mm = max(80.0, outer_length_mm * 0.2)
    gas_box_length_mm = max(40.0, chamber_length_mm * 0.15)

    # Coil placement driven by chamber length and B-field
    coil_main_count = max(6, int(chamber_length_mm / 60.0))
    coil_main_spacing_mm = chamber_length_mm / coil_main_count
    coil_main_thickness_mm = max(8.0, coil_main_spacing_mm * 0.35)
    coil_main_start_mm = max(20.0, (outer_length_mm - chamber_length_mm) * 0.2)

    coil_nozzle_count = max(2, int(nozzle_length_mm / 40.0))
    coil_nozzle_spacing_mm = nozzle_length_mm / coil_nozzle_count
    coil_nozzle_thickness_mm = max(6.0, coil_nozzle_spacing_mm * 0.4)
    coil_nozzle_start_mm = coil_main_start_mm + chamber_length_mm + 10.0

    # Field-shaping and mirror coils (physics-aligned placements)
    mirror_count = 2
    mirror_offset_mm = max(30.0, chamber_length_mm * 0.08)
    mirror_radius_mm = coil_outer_mm + max(8.0, inputs["B"] * 1.5)
    mirror_thickness_mm = max(10.0, coil_main_thickness_mm * 1.2)
    mirror_start_mm = coil_main_start_mm - mirror_offset_mm
    mirror_spacing_mm = chamber_length_mm + (2 * mirror_offset_mm)

    shaping_count = max(4, int(chamber_length_mm / 80.0))
    shaping_start_mm = coil_main_start_mm + (coil_main_spacing_mm * 0.5)
    shaping_spacing_mm = chamber_length_mm / shaping_count
    shaping_radius_mm = coil_outer_mm + max(4.0, inputs["B"])
    shaping_thickness_mm = max(6.0, coil_main_thickness_mm * 0.7)

    # Thruster tube taper based on magnetic profile
    tube_taper_mm = max(4.0, inputs["B"] * 1.5)

    return {
        "outer_length": f"{outer_length_mm:.2f} mm",
        "outer_radius": f"{outer_radius_mm:.2f} mm",
        "wall_thickness": f"{wall_thickness_mm:.2f} mm",
        "liner_thickness": "2 mm",
        "bore_radius": f"{bore_radius_mm:.2f} mm",
        "chamber_length": f"{chamber_length_mm:.2f} mm",
        "nozzle_length": f"{nozzle_length_mm:.2f} mm",
        "gas_box_length": f"{gas_box_length_mm:.2f} mm",
        "thermal_shield_thickness": f"{shield_thickness_mm:.2f} mm",
        "coil_inner_radius": f"{coil_inner_mm:.2f} mm",
        "coil_outer_radius": f"{coil_outer_mm:.2f} mm",
        "coil_main_count": f"{coil_main_count}",
        "coil_main_spacing": f"{coil_main_spacing_mm:.2f} mm",
        "coil_main_thickness": f"{coil_main_thickness_mm:.2f} mm",
        "coil_main_start": f"{coil_main_start_mm:.2f} mm",
        "coil_nozzle_count": f"{coil_nozzle_count}",
        "coil_nozzle_spacing": f"{coil_nozzle_spacing_mm:.2f} mm",
        "coil_nozzle_thickness": f"{coil_nozzle_thickness_mm:.2f} mm",
        "coil_nozzle_start": f"{coil_nozzle_start_mm:.2f} mm",
        "mirror_coil_count": f"{mirror_count}",
        "mirror_coil_radius": f"{mirror_radius_mm:.2f} mm",
        "mirror_coil_thickness": f"{mirror_thickness_mm:.2f} mm",
        "mirror_coil_start": f"{mirror_start_mm:.2f} mm",
        "mirror_coil_spacing": f"{mirror_spacing_mm:.2f} mm",
        "shaping_coil_count": f"{shaping_count}",
        "shaping_coil_radius": f"{shaping_radius_mm:.2f} mm",
        "shaping_coil_thickness": f"{shaping_thickness_mm:.2f} mm",
        "shaping_coil_start": f"{shaping_start_mm:.2f} mm",
        "shaping_coil_spacing": f"{shaping_spacing_mm:.2f} mm",
        "tube_taper": f"{tube_taper_mm:.2f} mm",
        "rmf_antenna_count": "4",
        "rmf_antenna_radius": f"{(outer_radius_mm + 10.0):.2f} mm",
        "rmf_antenna_length": f"{(chamber_length_mm * 0.15):.2f} mm",
        "rmf_antenna_spacing": f"{(chamber_length_mm * 0.35):.2f} mm",
        "target_thrust": f"{result.thrust:.2f} N",
        "target_power": f"{result.p_fusion/1000.0:.2f} kW",
        "target_mass": f"{result.details['Total_Mass_kg']:.2f} kg",
    }


def main():
    inputs = _load_design_inputs(Path("optimized_design.csv"))
    engine = FuturePhysicsEngine()
    result = engine.evaluate(
        inputs["r"],
        inputs["L"],
        inputs["B"],
        inputs["Ti_keV"],
        inputs["He3_to_D"],
        inputs["m_dot"],
    )

    params = _derive_cad_params(engine, result, inputs)
    output = {
        "inputs": inputs,
        "physics_details": result.details,
        "cad_params": params,
        "violations": result.details.get("violations", []),
    }

    out_path = Path("DFD_fusion360") / "physics_params.json"
    out_path.write_text(json.dumps(output, indent=2))
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
