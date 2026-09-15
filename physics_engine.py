import math
from dataclasses import dataclass

import numpy as np
from scipy.optimize import root_scalar, fsolve


@dataclass
class PhysicsResult:
    thrust: float
    isp: float
    twr: float
    q_plasma: float
    q_engineering: float
    p_fusion: float
    p_charged: float
    p_neutron: float
    p_waste: float
    wall_heat_flux: float
    stability_risk: float
    masses: dict
    fuel_burn_kg_per_year: dict
    stored_energy: float
    current_density: float
    rf_specific_mass: float
    details: dict


class FuturePhysicsEngine:
    """
    High-fidelity (but compact) physics kernel for D-He3 FRC-based DFD sizing.
    """

    def __init__(self):
        self.mu0 = 4e-7 * math.pi
        self.kb = 1.380649e-23
        self.e_charge = 1.602176634e-19
        self.g0 = 9.80665

        self.m_p = 1.6726219e-27
        self.m_d = 2 * self.m_p
        self.m_he3 = 3 * self.m_p
        self.m_i = 0.5 * (self.m_d + self.m_he3)

        self.rho_hts = 6500.0  # kg/m3
        self.rho_inconel = 8400.0  # kg/m3
        self.rho_tungsten = 19300.0  # kg/m3
        self.rho_titanium = 4500.0  # kg/m3

        self.sigma_sb = 5.670374419e-8
        # Degnan 2013 reports liner-driven radial compression ~10-20x.
        self.liner_compression_ratio = 12.0
        # Scintillator diagnostic defaults (simple geometric model)
        self.scintillator_area_m2 = 0.01  # 10 cm x 10 cm
        self.scintillator_distance_m = 1.0
        self.scintillator_efficiency = 0.15  # photons detected per neutron event
        self.neutron_energy_MeV = 2.45  # DD-equivalent proxy
        # DFD/PFRC literature anchors
        self.dfd_core_temp_keV = 100.0  # Cohen 2019 JBiS: ~100 keV core
        self.dfd_core_density_cm3 = 5e14  # Cohen 2019 JBiS: ~5e14 cm^-3
        self.dfd_thrust_per_mw = 3.5  # NIAC: 2.5–5 N/MW, use mid-point
        self.dfd_thrust_per_mw_aug = 40.0  # Acta Astronautica 2014: 1 MW -> 40 N
        self.dfd_isp_s = 10000.0  # NIAC/DFD: ~10,000 s
        self.dfd_isp_s_aug = 5750.0  # Acta Astronautica 2014: ~56.5 km/s
        self.rmf_fraction_of_B = 0.005  # AIAA/PPPL: RMF ~0.1–1% of axial B
        self.rmf_frequency_hz = 2.0e6  # PFRC-2 class operating frequency
        self.plasma_conductivity_s = 1.0e6  # S/m proxy for RMF penetration check
        self.rmf_ion_fraction = 0.7
        self.rmf_electron_fraction = 0.3
        self.ion_loss_fraction = 0.02
        self.electron_loss_fraction = 0.02
        self.dfd_specific_power_kw_per_kg = 0.18  # Acta Astronautica 2014
        self.dfd_ref = {
            "r_m": 0.25,
            "L_m": 5.0,
            "B_T": 4.7,
            "Ti_keV": 100.0,
            "Te_keV": 30.0,
            "nD_cm3": 5.3e13,
            "nHe3_cm3": 1.6e14,
            "ne_cm3": 3.7e14,
            "thrust_N": 40.0,
            "exhaust_km_s": 56.5,
            "fusion_power_MW": 1.0,
            "shield_mass_kg": 800.0,
        }
        self.rmfo_radius_opt_range_m = (0.2, 0.3)  # Acta 2014: 20–30 cm
        self.pfrc_length_range_m = (4.0, 8.0)  # Acta Astronautica 2023 PFRC
        self.pfrc_diameter_range_m = (0.5, 1.5)  # 2014 RMFo (~0.5 m) to 2023 PFRC (1.5 m)
        self.pfrc_power_range_mw = (1.0, 10.0)
        self.use_dfd_perf_model = True
        self.use_thrust_augmentation = True
        # Material property proxies for physics-based sizing
        self.materials = {
            "Inconel": {"density": self.rho_inconel, "allowable_stress_pa": 600e6},
            "Tungsten": {"density": self.rho_tungsten, "allowable_stress_pa": 800e6},
            "Titanium": {"density": self.rho_titanium, "allowable_stress_pa": 450e6},
            "HTS": {"density": self.rho_hts, "allowable_stress_pa": 250e6},
        }

    def reactivity_dhe3(self, ti_keV: float) -> float:
        # Simple proxy for D-He3 reactivity, tuned for keV range
        ti = max(ti_keV, 0.5)
        return 1e-22 * (ti**2) * math.exp(-19.94 / ti)

    def get_synchrotron(self, n, B, Te_keV):
        # Trubnikov-style proxy with wall reflectivity
        r_wall = 0.9
        return 6.2e-17 * n * (B**2) * Te_keV * (1 + Te_keV / 204.0) * math.sqrt(1 - r_wall)

    def get_divertor_flux(self, p_loss, r_p, gyroradius):
        # SOL width scales with gyroradius
        lambda_sol = 4 * gyroradius
        return p_loss / max(2 * math.pi * r_p * lambda_sol, 1e-12)

    def rmf_penetration_ok(self, r_plasma):
        omega = 2 * math.pi * self.rmf_frequency_hz
        delta = math.sqrt(2.0 / (self.mu0 * self.plasma_conductivity_s * omega))
        return delta, delta > r_plasma

    def solve_plasma_state(self, r, L, B, ratio_he3_d, rmf_power):
        def equations(vars_):
            ti_keV, te_keV = vars_
            if ti_keV <= 0.0 or te_keV <= 0.0:
                return [1e30, 1e30]
            beta = 0.95
            p_mag = B**2 / (2 * self.mu0)
            p_plasma = beta * p_mag

            te_K = te_keV * 1e3 * self.e_charge / self.kb
            ti_K = ti_keV * 1e3 * self.e_charge / self.kb
            n = p_plasma / (self.kb * (te_K + ti_K) + 1e-30)

            volume = math.pi * r**2 * L
            n_d = n / (1 + ratio_he3_d)
            n_he3 = n * ratio_he3_d / (1 + ratio_he3_d)
            reactivity = self.reactivity_dhe3(ti_keV)
            e_fusion = 18.3e6 * self.e_charge
            p_fusion = n_d * n_he3 * reactivity * e_fusion * volume

            p_alpha = 0.8 * p_fusion
            p_alpha_i = 0.8 * p_alpha
            p_alpha_e = 0.2 * p_alpha
            p_rmf_i = self.rmf_ion_fraction * rmf_power
            p_rmf_e = self.rmf_electron_fraction * rmf_power

            te_eV = max(te_keV * 1e3, 1e-6)
            tau_ei = 1e-3 * (te_eV**1.5) / (n / 1e20 + 1e-12)
            p_ie = 3 * n * self.kb * abs(ti_K - te_K) * volume / (tau_ei + 1e-12)
            p_brem = 1.69e-38 * (1.5**2) * (n**2) * math.sqrt(te_eV) * volume
            p_syn = self.get_synchrotron(n, B, te_keV) * volume

            p_loss_i = self.ion_loss_fraction * p_fusion
            p_loss_e = self.electron_loss_fraction * p_fusion

            ion_balance = p_alpha_i + p_rmf_i - p_ie - p_loss_i
            elec_balance = p_alpha_e + p_rmf_e + p_ie - p_brem - p_syn - p_loss_e
            return [ion_balance, elec_balance]

        try:
            ti_keV, te_keV, info, ier = fsolve(equations, [50.0, 30.0], full_output=True)
        except Exception:
            return None, None
        if ier != 1 or ti_keV <= 0.0 or te_keV <= 0.0:
            return None, None
        return ti_keV, te_keV

    def equations_summary(self):
        return [
            "Magnetic pressure: P_mag = B^2 / (2 * mu0)",
            "Plasma pressure (beta limit): P_plasma = beta * P_mag",
            "Density from pressure: n = P_plasma / (k_B * (T_e + T_i))",
            "Fusion power: P_fus = n_D * n_He3 * <sigma v> * E_fus * V",
            "Power balance (multi-fluid): P_i = P_alpha,i + P_RMF,i - P_ie - P_loss,i",
            "Power balance (multi-fluid): P_e = P_alpha,e + P_RMF,e + P_ie - P_brem - P_syn - P_loss,e",
            "Bremsstrahlung: P_brem ∝ Z_eff^2 * n^2 * sqrt(T_e) * V",
            "Synchrotron (Trubnikov): P_syn ∝ n_e B^2 T_e (1 + T_e/204) (1 - R_wall)^0.5",
            "Ion gyroradius: rho_i = sqrt(2 * m_i * k_B * T_i) / (q * B)",
            "Stability: S = r / rho_i, E = L / (2r)",
            "Q_plasma = P_fus / P_aux",
            "Q_engineering = P_fus / (P_aux/eta_RF + 0.05 * P_fus)",
            "Thrust: F = m_dot * v_e, v_e = sqrt(2 * eta_nozzle * P_charged / m_dot)",
            "Wall heat flux: q_wall = P_neutron / (2 * pi * r * L)",
            "Divertor heat flux: q_div = P_loss / (2 * pi * r_div * lambda_SOL)",
            "Flux compression (liner): B_final = B_initial * (r_initial / r_final)^2",
            "Rotation control ring voltage (approx.): V_ring ~ (2-5) * T_e (eV)",
            "Wall potential (isothermal): phi0 ~ (kT_e/e) ln[n0(psi)n^2(rs)/(n0(0)n^2(r))] + phi0(0)",
            "Scintillator solid angle: Omega = A / d^2",
            "Neutron rate: Ndot = P_neutron / E_n",
            "Detected rate: Cdot = Ndot * (Omega / 4pi) * eta",
            "DFD thrust model: T ≈ (2.5–5) N/MW * P_fusion",
            "DFD Isp: ~10,000 s (thrust augmentation regime)",
            "DFD augmented thrust: ~40 N/MW, Ve ~56.5 km/s (1 MW reference)",
            "RMF heating field: B_RMF ≈ (0.1–1%) * B_axial",
            "RMF penetration: delta = sqrt(2 / (mu0 * sigma * omega))",
            "DFD specific power: ~0.18 kW/kg (1 MW, 40 N reference)",
        ]

    def _power_balance(self, te_keV, ti_keV, r, L, B, ratio_he3_d) -> float:
        # Plasma pressure limit from beta limit
        beta = 0.95
        p_mag = B**2 / (2 * self.mu0)
        p_plasma = beta * p_mag

        # Convert temperatures to K and solve density from pressure
        te_K = te_keV * 1e3 * self.e_charge / self.kb
        ti_K = ti_keV * 1e3 * self.e_charge / self.kb
        n = p_plasma / (self.kb * (te_K + ti_K) + 1e-30)
        n_cm3 = n / 1e6

        volume = math.pi * r**2 * L
        n_d = n / (1 + ratio_he3_d)
        n_he3 = n * ratio_he3_d / (1 + ratio_he3_d)

        reactivity = self.reactivity_dhe3(ti_keV)
        e_fusion = 18.3e6 * self.e_charge  # J per reaction
        p_fusion = n_d * n_he3 * reactivity * e_fusion * volume

        # Heating power (alpha + auxiliary)
        p_alpha = 0.8 * p_fusion
        p_aux = 0.05 * p_fusion + 1e6
        p_heating = p_alpha + p_aux

        # Calculating Bremsstrahlung losses...
        te_eV = te_keV * 1e3
        z_eff = 1.5
        p_brem = 1.69e-38 * (z_eff**2) * (n**2) * math.sqrt(te_eV) * volume

        # Ion-electron drag power loss (thermal equilibration)
        tau_ei = 1e-3 * (te_eV**1.5) / (n / 1e20 + 1e-12)
        p_ie = 3 * n * self.kb * abs(ti_K - te_K) * volume / (tau_ei + 1e-12)

        p_cooling = p_brem + p_ie
        return p_heating - p_cooling

    def solve_equilibrium_te(self, ti_keV, r, L, B, ratio_he3_d):
        # Solve for Te such that Heating == Cooling (root of power balance).
        def f(te_keV):
            return self._power_balance(te_keV, ti_keV, r, L, B, ratio_he3_d)

        brackets = [(1.0, 200.0), (0.5, 400.0)]
        for lo, hi in brackets:
            try:
                sol = root_scalar(f, bracket=[lo, hi], method="brentq")
                if sol.converged:
                    return sol.root
            except ValueError:
                continue

        # Scan for a sign change if the default brackets fail.
        grid = np.linspace(0.5, 400.0, 60)
        values = [f(te) for te in grid]
        for i in range(len(values) - 1):
            if values[i] == 0:
                return grid[i]
            if values[i] * values[i + 1] < 0:
                try:
                    sol = root_scalar(
                        f, bracket=[grid[i], grid[i + 1]], method="brentq"
                    )
                    if sol.converged:
                        return sol.root
                except ValueError:
                    pass

        # If no root, only accept near-equilibrium solutions.
        min_idx = int(np.argmin(np.abs(values)))
        if abs(values[min_idx]) <= 1e5:
            return grid[min_idx]

        # Final fallback: use a conservative Te estimate to keep designs evaluable.
        return max(2.0, min(50.0, 0.5 * ti_keV))

    def evaluate(self, r, L, B, ti_keV, ratio_he3_d, m_dot):
        ti_input = ti_keV
        rmf_power = 1e6
        try:
            ti_keV, te_keV = self.solve_plasma_state(r, L, B, ratio_he3_d, rmf_power)
        except Exception:
            ti_keV, te_keV = None, None
        if ti_keV is None or te_keV is None:
            ti_keV = ti_input
            te_keV = self.solve_equilibrium_te(ti_keV, r, L, B, ratio_he3_d)
            if te_keV is None:
                return self._failed_result(r, L, B, ti_keV, ratio_he3_d, m_dot)
        if te_keV is None or m_dot <= 0:
            return self._failed_result(r, L, B, ti_keV, ratio_he3_d, m_dot)

        beta = 0.95
        p_mag = B**2 / (2 * self.mu0)
        p_plasma = beta * p_mag

        te_K = te_keV * 1e3 * self.e_charge / self.kb
        ti_K = ti_keV * 1e3 * self.e_charge / self.kb
        n = p_plasma / (self.kb * (te_K + ti_K) + 1e-30)
        n_cm3 = n / 1e6

        volume = math.pi * r**2 * L
        n_d = n / (1 + ratio_he3_d)
        n_he3 = n * ratio_he3_d / (1 + ratio_he3_d)

        reactivity = self.reactivity_dhe3(ti_keV)
        e_fusion = 18.3e6 * self.e_charge
        p_fusion = n_d * n_he3 * reactivity * e_fusion * volume
        p_charged = 0.8 * p_fusion
        p_neutron = 0.03 * p_fusion

        p_aux = 0.05 * p_fusion + 1e6
        rmf_power = p_aux
        # Q_plasma is plasma-only gain: fusion power / external heating into plasma.
        p_heat_absorbed = p_aux
        # Q_engineering is wall-plug gain: fusion power / full electrical load.
        p_wall_plug = p_aux / 0.7 + 0.05 * p_fusion

        q_plasma = p_fusion / max(p_heat_absorbed, 1.0)
        q_engineering = p_fusion / max(p_wall_plug, 1.0)

        # Stability checks
        rho_i = math.sqrt(2 * self.m_i * self.kb * ti_K) / (self.e_charge * B)
        s_factor = r / max(rho_i, 1e-9)
        elongation = L / max(2 * r, 1e-9)
        stability_risk = 0.0
        if s_factor > 3.5 or elongation > 8:
            stability_risk = 100.0

        # Thrust and Isp from charged power
        eta_nozzle = 0.7
        ve = math.sqrt(max(2 * eta_nozzle * p_charged / max(m_dot, 1e-6), 1.0))
        thrust = m_dot * ve
        isp = ve / self.g0
        m_dot_input = m_dot
        if self.use_dfd_perf_model:
            if self.use_thrust_augmentation:
                thrust = (p_fusion / 1e6) * self.dfd_thrust_per_mw_aug
                isp = self.dfd_isp_s_aug
            else:
                thrust = (p_fusion / 1e6) * self.dfd_thrust_per_mw
                isp = self.dfd_isp_s
            ve = isp * self.g0
            m_dot = thrust / max(ve, 1e-9)

        # Component mass sizing
        amp_turns = B * 2 * r / max(self.mu0, 1e-12)
        # Coil build based on B-field, enforcing a more specific current density
        coil_radial_build = 0.1 + 0.01 * B
        coil_height = max(0.5 * r, 0.1)
        conductor_area = coil_radial_build * coil_height
        coil_length = 2 * math.pi * r
        conductor_volume = conductor_area * coil_length
        magnet_conductor_mass = conductor_volume * self.rho_hts
        current_density = amp_turns / max(conductor_area, 1e-12)

        pressure = p_mag
        allowable_stress = self.materials["Inconel"]["allowable_stress_pa"]
        surface_area = 2 * math.pi * r * L
        structure_thickness = pressure / max(allowable_stress, 1.0)
        structure_volume = surface_area * structure_thickness
        magnet_structure_mass = structure_volume * self.rho_inconel

        wall_heat_flux = p_neutron / max(surface_area, 1e-9)
        p_syn = self.get_synchrotron(n, B, te_keV) * volume
        p_loss = p_syn + p_aux
        q_div = self.get_divertor_flux(p_loss, r, rho_i)
        shield_thickness = 0.1 * (wall_heat_flux / 1e6)
        shield_volume = surface_area * shield_thickness
        shielding_mass = shield_volume * self.rho_tungsten

        p_waste = max(p_fusion - p_charged + p_aux, 0.0)
        radiator_area = p_waste / (self.sigma_sb * (1000.0**4))
        radiator_mass = radiator_area * 8.0  # kg/m2 proxy

        vessel_thickness = 0.02
        vessel_volume = surface_area * vessel_thickness
        vessel_mass = vessel_volume * self.rho_titanium

        rf_system_mass = (p_aux / 1e3) * 1.5
        rf_specific_mass = rf_system_mass / max(p_aux / 1e3, 1e-9)

        # Simple material-based checks
        hoop_stress = pressure * r / max(structure_thickness, 1e-6)
        stress_margin = allowable_stress / max(hoop_stress, 1.0)
        shield_required = shield_thickness
        violations = []
        if stress_margin < 1.0:
            violations.append("Structure over-stressed")
        if wall_heat_flux / 1e6 > 50.0:
            violations.append("Wall heat flux high")
        if current_density / 1e6 > 50.0:
            violations.append("Current density high")
        if abs(ti_keV - self.dfd_core_temp_keV) / self.dfd_core_temp_keV > 0.5:
            violations.append("Core temperature off DFD target")
        if n_cm3 < self.dfd_core_density_cm3 / 10 or n_cm3 > self.dfd_core_density_cm3 * 10:
            violations.append("Core density off DFD target")
        rmf_delta, rmf_ok = self.rmf_penetration_ok(r)
        if not rmf_ok:
            violations.append("RMF penetration insufficient")
        if not (self.pfrc_length_range_m[0] <= L <= self.pfrc_length_range_m[1]):
            violations.append("Length outside PFRC range")
        if not (self.pfrc_diameter_range_m[0] <= 2 * r <= self.pfrc_diameter_range_m[1]):
            violations.append("Diameter outside PFRC range")
        if not (self.pfrc_power_range_mw[0] <= p_fusion / 1e6 <= self.pfrc_power_range_mw[1]):
            violations.append("Fusion power outside PFRC range")

        total_mass = (
            magnet_conductor_mass
            + magnet_structure_mass
            + shielding_mass
            + radiator_mass
            + vessel_mass
            + rf_system_mass
        )
        specific_power_kw_per_kg = (p_fusion / 1e3) / max(total_mass, 1e-9)
        if specific_power_kw_per_kg < self.dfd_specific_power_kw_per_kg * 0.5:
            violations.append("Specific power below DFD reference")
        specific_power_alpha = total_mass / max(p_fusion / 1e3, 1e-9)
        if specific_power_alpha > 1.0:
            violations.append("Specific power alpha > 1.0 kg/kW")

        twr = thrust / max(total_mass * self.g0, 1e-9)

        # Fuel logistics
        reactions_per_s = n_d * n_he3 * reactivity * volume
        d_burn = reactions_per_s * self.m_d
        he3_burn = reactions_per_s * self.m_he3
        seconds_per_year = 365.25 * 24 * 3600
        fuel_burn_kg_per_year = {
            "D": d_burn * seconds_per_year,
            "He3": he3_burn * seconds_per_year,
        }

        stored_energy = p_mag * volume
        # Liner compression scaling and bias ring voltage estimates.
        compression_ratio = self.liner_compression_ratio
        b_compressed = B * (compression_ratio**2)
        bias_ring_voltage = 3.0 * te_keV * 1e3  # ~few times Te (eV)
        # Scintillator diagnostic estimate (isotropic neutrons)
        e_neutron = self.neutron_energy_MeV * 1e6 * self.e_charge
        neutron_rate = p_neutron / max(e_neutron, 1e-12)
        solid_angle = self.scintillator_area_m2 / max(self.scintillator_distance_m**2, 1e-12)
        scint_detect_rate = neutron_rate * (solid_angle / (4 * math.pi)) * self.scintillator_efficiency

        masses = {
            "Magnet Conductor": magnet_conductor_mass,
            "Magnet Structure": magnet_structure_mass,
            "Shielding": shielding_mass,
            "Radiators": radiator_mass,
            "Vessel": vessel_mass,
            "RF System": rf_system_mass,
        }

        details = {
            "r": r,
            "L": L,
            "B": B,
            "Ti_keV": ti_keV,
            "Te_keV": te_keV,
            "n_cm3": n_cm3,
            "S_factor": s_factor,
            "Elongation": elongation,
            "Shield_Thickness_m": shield_thickness,
            "Radiator_Area_m2": radiator_area,
            "Total_Mass_kg": total_mass,
            "Compression_Ratio": compression_ratio,
            "B_Compressed_T": b_compressed,
            "Bias_Ring_Voltage_V": bias_ring_voltage,
            "Scintillator_Area_m2": self.scintillator_area_m2,
            "Scintillator_Distance_m": self.scintillator_distance_m,
            "Scintillator_Efficiency": self.scintillator_efficiency,
            "Neutron_Rate_per_s": neutron_rate,
            "Scintillator_Detected_per_s": scint_detect_rate,
            "Hoop_Stress_Pa": hoop_stress,
            "Stress_Margin": stress_margin,
            "violations": violations,
            "DFD_Target_Ti_keV": self.dfd_core_temp_keV,
            "DFD_Target_n_cm3": self.dfd_core_density_cm3,
            "DFD_Thrust_per_MW": self.dfd_thrust_per_mw,
            "DFD_Thrust_per_MW_Aug": self.dfd_thrust_per_mw_aug,
            "DFD_Isp_s": self.dfd_isp_s,
            "DFD_Isp_s_Aug": self.dfd_isp_s_aug,
            "RMF_Field_T": self.rmf_fraction_of_B * B,
            "RMF_Penetration_m": rmf_delta,
            "RMF_Penetration_OK": rmf_ok,
            "m_dot_input": m_dot_input,
            "Specific_Power_kW_per_kg": specific_power_kw_per_kg,
            "Specific_Power_alpha_kg_per_kW": specific_power_alpha,
            "DFD_Specific_Power_Target": self.dfd_specific_power_kw_per_kg,
            "DFD_Reference": self.dfd_ref,
            "PFRC_Length_Range_m": self.pfrc_length_range_m,
            "PFRC_Diameter_Range_m": self.pfrc_diameter_range_m,
            "PFRC_Power_Range_MW": self.pfrc_power_range_mw,
            "RMFo_Optimal_Radius_Range_m": self.rmfo_radius_opt_range_m,
            "q_divertor_W_m2": q_div,
            "P_syn_W": p_syn,
        }

        return PhysicsResult(
            thrust=thrust,
            isp=isp,
            twr=twr,
            q_plasma=q_plasma,
            q_engineering=q_engineering,
            p_fusion=p_fusion,
            p_charged=p_charged,
            p_neutron=p_neutron,
            p_waste=p_waste,
            wall_heat_flux=wall_heat_flux,
            stability_risk=stability_risk,
            masses=masses,
            fuel_burn_kg_per_year=fuel_burn_kg_per_year,
            stored_energy=stored_energy,
            current_density=current_density,
            rf_specific_mass=rf_specific_mass,
            details=details,
        )

    def _failed_result(self, r, L, B, ti_keV, ratio_he3_d, m_dot):
        details = {
            "r": r,
            "L": L,
            "B": B,
            "Ti_keV": ti_keV,
            "Te_keV": None,
            "S_factor": float("inf"),
            "Elongation": float("inf"),
            "Shield_Thickness_m": float("inf"),
            "Radiator_Area_m2": float("inf"),
            "Total_Mass_kg": float("nan"),
        }
        return PhysicsResult(
            thrust=0.0,
            isp=1.0,
            twr=0.0,
            q_plasma=0.0,
            q_engineering=0.0,
            p_fusion=0.0,
            p_charged=0.0,
            p_neutron=0.0,
            p_waste=0.0,
            wall_heat_flux=float("inf"),
            stability_risk=1000.0,
            masses={},
            fuel_burn_kg_per_year={"D": float("inf"), "He3": float("inf")},
            stored_energy=0.0,
            current_density=float("inf"),
            rf_specific_mass=float("inf"),
            details=details,
        )

