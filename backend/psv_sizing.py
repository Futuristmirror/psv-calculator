"""
PSV Sizing Calculations per API 520/521

Implements relief valve sizing for:
- Fire case (wetted and unwetted)
- Blocked outlet (vapor and liquid)
- Control valve failure

Author: Franc Engineering
"""

import math
from dataclasses import dataclass
from typing import Dict, Optional, Tuple
from enum import Enum


# Constants
R = 8.314462  # J/(mol·K)
R_US = 1545.35  # ft·lbf/(lbmol·R)


class Scenario(Enum):
    FIRE_WETTED = "fire_wetted"
    FIRE_UNWETTED = "fire_unwetted"
    BLOCKED_VAPOR = "blocked_vapor"
    BLOCKED_LIQUID = "blocked_liquid"
    CV_FAILURE = "cv_failure"


@dataclass
class Orifice:
    """API 526 Standard Orifice"""
    letter: str
    area_in2: float
    area_mm2: float


# API 526 Standard Orifice Sizes
API_526_ORIFICES = [
    Orifice("D", 0.110, 71.0),
    Orifice("E", 0.196, 126.5),
    Orifice("F", 0.307, 198.1),
    Orifice("G", 0.503, 324.5),
    Orifice("H", 0.785, 506.5),
    Orifice("J", 1.287, 830.3),
    Orifice("K", 1.838, 1185.8),
    Orifice("L", 2.853, 1841.0),
    Orifice("M", 3.600, 2322.6),
    Orifice("N", 4.340, 2800.0),
    Orifice("P", 6.380, 4116.1),
    Orifice("Q", 11.05, 7129.0),
    Orifice("R", 16.00, 10322.6),
    Orifice("T", 26.00, 16774.2),
]


def select_orifice(required_area_in2: float) -> Tuple[Orifice, float]:
    """
    Select API 526 standard orifice based on required area

    Returns:
        Tuple of (selected orifice, percent utilization)
    """
    for orifice in API_526_ORIFICES:
        if orifice.area_in2 >= required_area_in2:
            utilization = (required_area_in2 / orifice.area_in2) * 100
            return orifice, utilization

    # If larger than T orifice, return T with >100% utilization
    largest = API_526_ORIFICES[-1]
    return largest, (required_area_in2 / largest.area_in2) * 100


def fire_heat_input_wetted(wetted_area_ft2: float,
                           insulated: bool = False,
                           F_env: float = 1.0,
                           adequate_drainage: bool = True) -> float:
    """
    Calculate fire heat input per API 521 for wetted surface

    Q = C1 * F * A^0.82  (for adequate drainage)
    Q = C2 * F * A       (for inadequate drainage)

    Args:
        wetted_area_ft2: Wetted surface area in ft²
        insulated: Whether vessel is insulated
        F_env: Environmental factor (1.0 for bare, 0.3 for water spray, etc.)
        adequate_drainage: Whether adequate drainage/firefighting exists

    Returns:
        Heat input in BTU/hr
    """
    if insulated:
        # Insulation credit per API 521
        F_env = min(F_env, 0.3)

    if adequate_drainage and wetted_area_ft2 <= 2800:
        # Q = 21,000 * F * A^0.82 for A ≤ 2800 ft²
        Q = 21000 * F_env * (wetted_area_ft2 ** 0.82)
    elif adequate_drainage:
        # Q = 34,500 * F * A^0.82 for A > 2800 ft²
        Q = 34500 * F_env * (wetted_area_ft2 ** 0.82)
    else:
        # Inadequate drainage: Q = 20,000 * F * A
        Q = 20000 * F_env * wetted_area_ft2

    return Q


def fire_heat_input_unwetted(surface_area_ft2: float,
                             T_vessel_R: float = 1160,
                             emissivity: float = 0.9) -> float:
    """
    Calculate fire heat input for unwetted (vapor space) surface

    Uses Stefan-Boltzmann radiation heat transfer
    Q = σ * ε * A * (T_fire^4 - T_vessel^4)

    Args:
        surface_area_ft2: Unwetted surface area
        T_vessel_R: Vessel wall temperature in Rankine (default 1160R = 700°F)
        emissivity: Surface emissivity (default 0.9 for oxidized steel)

    Returns:
        Heat input in BTU/hr
    """
    # Stefan-Boltzmann constant: 0.1714e-8 BTU/(hr·ft²·R⁴)
    sigma = 0.1714e-8

    # Fire temperature typically 1460°F = 1920R per API 521
    T_fire_R = 1920

    Q = sigma * emissivity * surface_area_ft2 * (T_fire_R**4 - T_vessel_R**4)
    return Q


def wetted_area_horizontal_vessel(diameter_ft: float,
                                  length_ft: float,
                                  liquid_level_fraction: float = 0.5) -> float:
    """
    Calculate wetted area for horizontal cylindrical vessel

    Args:
        diameter_ft: Vessel diameter in feet
        length_ft: Vessel tan-tan length in feet
        liquid_level_fraction: Fraction of diameter filled (0 to 1)

    Returns:
        Wetted area in ft²
    """
    R = diameter_ft / 2
    h = liquid_level_fraction * diameter_ft

    # Angle subtended by liquid surface
    theta = 2 * math.acos((R - h) / R) if h <= diameter_ft else 2 * math.pi

    # Wetted perimeter of circular cross-section
    arc_length = R * theta

    # Wetted shell area
    shell_area = arc_length * length_ft

    # Wetted head area (2 heads, assume 2:1 elliptical)
    # Simplified: treat as flat circles
    # Wetted head area = 2 * (segment area)
    segment_area = (R**2 / 2) * (theta - math.sin(theta))
    head_area = 2 * segment_area

    return shell_area + head_area


def wetted_area_vertical_vessel(diameter_ft: float,
                                height_ft: float,
                                liquid_height_ft: float) -> float:
    """
    Calculate wetted area for vertical cylindrical vessel

    Args:
        diameter_ft: Vessel diameter in feet
        height_ft: Total vessel height in feet
        liquid_height_ft: Height of liquid in feet

    Returns:
        Wetted area in ft²
    """
    R = diameter_ft / 2

    # Wetted shell area
    shell_area = math.pi * diameter_ft * min(liquid_height_ft, height_ft)

    # Bottom head area (2:1 elliptical approximation)
    bottom_head = math.pi * R**2

    return shell_area + bottom_head


def vapor_relief_rate_fire(Q_btu_hr: float,
                           latent_heat_btu_lb: float) -> float:
    """
    Calculate vapor relief rate for fire case

    W = Q / λ

    Args:
        Q_btu_hr: Heat input in BTU/hr
        latent_heat_btu_lb: Latent heat of vaporization in BTU/lb

    Returns:
        Relief rate in lb/hr
    """
    return Q_btu_hr / latent_heat_btu_lb


def critical_pressure_ratio(gamma: float) -> float:
    """Calculate critical pressure ratio for choked flow"""
    return (2 / (gamma + 1)) ** (gamma / (gamma - 1))


def is_critical_flow(P1_psia: float, P2_psia: float, gamma: float) -> bool:
    """Determine if flow is critical (choked)"""
    P_ratio = P2_psia / P1_psia
    P_crit = critical_pressure_ratio(gamma)
    return P_ratio <= P_crit


def vapor_orifice_area_api520(W_lb_hr: float,
                              T_R: float,
                              MW: float,
                              Z: float,
                              gamma: float,
                              P1_psia: float,
                              P2_psia: float = 14.7,
                              Kd: float = 0.975,
                              Kb: float = 1.0,
                              Kc: float = 1.0) -> float:
    """
    Calculate required orifice area for vapor/gas relief per API 520

    For critical flow:
    A = W / (C * Kd * P1 * Kb * Kc) * sqrt(T * Z / M)

    Args:
        W_lb_hr: Required relief rate in lb/hr
        T_R: Relieving temperature in Rankine
        MW: Molecular weight
        Z: Compressibility factor
        gamma: Cp/Cv ratio
        P1_psia: Relieving pressure in psia (set pressure * 1.1 + atm)
        P2_psia: Back pressure in psia
        Kd: Discharge coefficient (0.975 for vapor)
        Kb: Back pressure correction factor
        Kc: Combination correction factor (1.0 for no rupture disk)

    Returns:
        Required orifice area in in²
    """
    # Calculate C coefficient
    C = 520 * math.sqrt(gamma * (2 / (gamma + 1)) ** ((gamma + 1) / (gamma - 1)))

    if is_critical_flow(P1_psia, P2_psia, gamma):
        # Critical (choked) flow equation
        A = (W_lb_hr / (C * Kd * P1_psia * Kb * Kc)) * math.sqrt(T_R * Z / MW)
    else:
        # Subcritical flow - more complex equation
        r = P2_psia / P1_psia
        F2 = math.sqrt((gamma / (gamma - 1)) * r**(2/gamma) *
                       ((1 - r**((gamma-1)/gamma)) / (1 - r)))

        A = (W_lb_hr / (735 * F2 * Kd * Kc)) * math.sqrt(T_R * Z / (MW * P1_psia * P2_psia))

    return A


def liquid_orifice_area_api520(Q_gpm: float,
                               G: float,
                               P1_psig: float,
                               P2_psig: float = 0,
                               Kd: float = 0.65,
                               Kw: float = 1.0,
                               Kc: float = 1.0,
                               Kv: float = 1.0) -> float:
    """
    Calculate required orifice area for liquid relief per API 520

    A = Q / (38 * Kd * Kw * Kc * Kv) * sqrt(G / (P1 - P2))

    Args:
        Q_gpm: Required relief rate in US gpm
        G: Specific gravity (water = 1.0)
        P1_psig: Relieving pressure in psig
        P2_psig: Back pressure in psig
        Kd: Discharge coefficient (0.65 for liquid)
        Kw: Back pressure correction (1.0 for conventional)
        Kc: Combination correction factor
        Kv: Viscosity correction factor

    Returns:
        Required orifice area in in²
    """
    delta_P = P1_psig - P2_psig
    if delta_P <= 0:
        raise ValueError("Relieving pressure must be greater than back pressure")

    A = (Q_gpm / (38 * Kd * Kw * Kc * Kv)) * math.sqrt(G / delta_P)
    return A


def blocked_outlet_relief_rate(upstream_flow_lb_hr: float,
                               normal_flow_lb_hr: float = 0) -> float:
    """
    Calculate relief rate for blocked outlet scenario

    Relief rate = upstream supply rate - normal outlet rate
    For fully blocked: normal_flow = 0
    """
    return upstream_flow_lb_hr - normal_flow_lb_hr


def cv_failure_flow(Cv: float,
                    P1_psia: float,
                    P2_psia: float,
                    G: float = 1.0,
                    T_R: float = 520) -> float:
    """
    Calculate flow through failed-open control valve

    For liquid: Q = Cv * sqrt(ΔP / G)
    For gas: W = 63.3 * Cv * P1 * sqrt(X / (G * T))

    This returns liquid flow in gpm. For gas, convert separately.

    Args:
        Cv: Valve flow coefficient
        P1_psia: Upstream pressure
        P2_psia: Downstream pressure
        G: Specific gravity
        T_R: Temperature in Rankine (for gas)

    Returns:
        Flow rate in gpm (liquid)
    """
    delta_P = P1_psia - P2_psia
    if delta_P <= 0:
        return 0

    Q = Cv * math.sqrt(delta_P / G)
    return Q


class PSVSizer:
    """Main PSV sizing calculator"""

    def __init__(self,
                 scenario: Scenario,
                 set_pressure_psig: float,
                 back_pressure_psig: float = 0,
                 accumulation: float = 0.10):
        """
        Initialize PSV sizer

        Args:
            scenario: Relief scenario type
            set_pressure_psig: PSV set pressure in psig
            back_pressure_psig: Total back pressure in psig
            accumulation: Allowed accumulation (0.10 for fire, 0.21 for other)
        """
        self.scenario = scenario
        self.set_pressure_psig = set_pressure_psig
        self.back_pressure_psig = back_pressure_psig

        # Fire cases get 21% accumulation per API 521
        if scenario in [Scenario.FIRE_WETTED, Scenario.FIRE_UNWETTED]:
            self.accumulation = 0.21
        else:
            self.accumulation = accumulation

        # Calculate relieving pressure
        self.relieving_pressure_psia = (set_pressure_psig * (1 + self.accumulation)) + 14.7
        self.back_pressure_psia = back_pressure_psig + 14.7

    def size_vapor(self,
                   W_lb_hr: float,
                   T_F: float,
                   MW: float,
                   Z: float,
                   gamma: float,
                   Kd: float = 0.975,
                   Kb: float = 1.0,
                   Kc: float = 1.0) -> Dict:
        """
        Size PSV for vapor/gas service

        Returns dictionary with sizing results
        """
        T_R = T_F + 459.67

        A_required = vapor_orifice_area_api520(
            W_lb_hr=W_lb_hr,
            T_R=T_R,
            MW=MW,
            Z=Z,
            gamma=gamma,
            P1_psia=self.relieving_pressure_psia,
            P2_psia=self.back_pressure_psia,
            Kd=Kd,
            Kb=Kb,
            Kc=Kc
        )

        orifice, utilization = select_orifice(A_required)
        flow_type = "Critical" if is_critical_flow(
            self.relieving_pressure_psia,
            self.back_pressure_psia,
            gamma
        ) else "Subcritical"

        return {
            "scenario": self.scenario.value,
            "relief_rate_lb_hr": W_lb_hr,
            "relieving_temperature_F": T_F,
            "relieving_pressure_psia": round(self.relieving_pressure_psia, 1),
            "back_pressure_psia": round(self.back_pressure_psia, 1),
            "molecular_weight": MW,
            "compressibility_Z": Z,
            "gamma": gamma,
            "flow_type": flow_type,
            "required_area_in2": round(A_required, 4),
            "selected_orifice": orifice.letter,
            "orifice_area_in2": orifice.area_in2,
            "percent_utilization": round(utilization, 1),
            "Kd": Kd,
            "Kb": Kb,
            "Kc": Kc
        }

    def size_liquid(self,
                    Q_gpm: float,
                    G: float,
                    Kd: float = 0.65,
                    Kw: float = 1.0,
                    Kc: float = 1.0,
                    Kv: float = 1.0) -> Dict:
        """
        Size PSV for liquid service

        Returns dictionary with sizing results
        """
        # For liquid, use psig values in the equation
        A_required = liquid_orifice_area_api520(
            Q_gpm=Q_gpm,
            G=G,
            P1_psig=self.set_pressure_psig * (1 + self.accumulation),
            P2_psig=self.back_pressure_psig,
            Kd=Kd,
            Kw=Kw,
            Kc=Kc,
            Kv=Kv
        )

        orifice, utilization = select_orifice(A_required)

        return {
            "scenario": self.scenario.value,
            "relief_rate_gpm": Q_gpm,
            "specific_gravity": G,
            "relieving_pressure_psig": round(self.set_pressure_psig * (1 + self.accumulation), 1),
            "back_pressure_psig": self.back_pressure_psig,
            "required_area_in2": round(A_required, 4),
            "selected_orifice": orifice.letter,
            "orifice_area_in2": orifice.area_in2,
            "percent_utilization": round(utilization, 1),
            "Kd": Kd,
            "Kw": Kw,
            "Kc": Kc,
            "Kv": Kv
        }

    def size_fire_wetted(self,
                         wetted_area_ft2: float,
                         latent_heat_btu_lb: float,
                         T_F: float,
                         MW: float,
                         Z: float,
                         gamma: float,
                         insulated: bool = False,
                         F_env: float = 1.0) -> Dict:
        """
        Size PSV for fire case with wetted surface
        """
        Q_fire = fire_heat_input_wetted(wetted_area_ft2, insulated, F_env)
        W = vapor_relief_rate_fire(Q_fire, latent_heat_btu_lb)

        result = self.size_vapor(W, T_F, MW, Z, gamma)
        result.update({
            "wetted_area_ft2": wetted_area_ft2,
            "heat_input_btu_hr": round(Q_fire, 0),
            "heat_input_mmbtu_hr": round(Q_fire / 1e6, 3),
            "latent_heat_btu_lb": latent_heat_btu_lb,
            "insulated": insulated,
            "environmental_factor": F_env
        })
        return result

    def size_fire_unwetted(self,
                           surface_area_ft2: float,
                           T_F: float,
                           MW: float,
                           Z: float,
                           gamma: float,
                           Cp_btu_lb_F: float = 0.5) -> Dict:
        """
        Size PSV for fire case with unwetted (vapor) surface

        Vapor expansion relief rate based on heat input
        """
        Q_fire = fire_heat_input_unwetted(surface_area_ft2)

        # For vapor, relief is due to thermal expansion
        # W = Q / (Cp * ΔT) approximately
        # Use simplified approach: assume vapor must be vented to prevent overpressure
        T_R = T_F + 459.67

        # Relief rate based on ideal gas expansion
        # Simplified: W ≈ Q / (Cp * T) * MW / (Z * R)
        W = Q_fire / (Cp_btu_lb_F * 100)  # Approximate, conservative

        result = self.size_vapor(W, T_F, MW, Z, gamma)
        result.update({
            "unwetted_area_ft2": surface_area_ft2,
            "heat_input_btu_hr": round(Q_fire, 0),
            "heat_input_mmbtu_hr": round(Q_fire / 1e6, 3),
            "Cp_btu_lb_F": Cp_btu_lb_F
        })
        return result


def calculate_psv_size(scenario: str,
                       set_pressure_psig: float,
                       fluid_properties: Dict,
                       vessel_properties: Optional[Dict] = None,
                       flow_rate: Optional[float] = None,
                       back_pressure_psig: float = 0) -> Dict:
    """
    Main entry point for PSV sizing calculations

    Args:
        scenario: One of "fire_wetted", "fire_unwetted", "blocked_vapor",
                  "blocked_liquid", "cv_failure"
        set_pressure_psig: PSV set pressure
        fluid_properties: Dict with MW, Z, gamma, T_F, latent_heat_btu_lb, etc.
        vessel_properties: Dict with dimensions for fire cases
        flow_rate: Relief rate for blocked outlet / CV failure cases
        back_pressure_psig: Back pressure

    Returns:
        Sizing results dictionary
    """
    scenario_enum = Scenario(scenario)
    sizer = PSVSizer(scenario_enum, set_pressure_psig, back_pressure_psig)

    if scenario == "fire_wetted":
        return sizer.size_fire_wetted(
            wetted_area_ft2=vessel_properties.get("wetted_area_ft2", 200),
            latent_heat_btu_lb=fluid_properties.get("latent_heat_btu_lb", 150),
            T_F=fluid_properties.get("T_F", 200),
            MW=fluid_properties.get("MW", 30),
            Z=fluid_properties.get("Z", 0.9),
            gamma=fluid_properties.get("gamma", 1.2),
            insulated=vessel_properties.get("insulated", False),
            F_env=vessel_properties.get("F_env", 1.0)
        )

    elif scenario == "fire_unwetted":
        return sizer.size_fire_unwetted(
            surface_area_ft2=vessel_properties.get("surface_area_ft2", 200),
            T_F=fluid_properties.get("T_F", 200),
            MW=fluid_properties.get("MW", 30),
            Z=fluid_properties.get("Z", 0.9),
            gamma=fluid_properties.get("gamma", 1.2)
        )

    elif scenario == "blocked_vapor":
        return sizer.size_vapor(
            W_lb_hr=flow_rate or 10000,
            T_F=fluid_properties.get("T_F", 200),
            MW=fluid_properties.get("MW", 30),
            Z=fluid_properties.get("Z", 0.9),
            gamma=fluid_properties.get("gamma", 1.2)
        )

    elif scenario == "blocked_liquid":
        return sizer.size_liquid(
            Q_gpm=flow_rate or 500,
            G=fluid_properties.get("specific_gravity", 0.8)
        )

    elif scenario == "cv_failure":
        return sizer.size_vapor(
            W_lb_hr=flow_rate or 10000,
            T_F=fluid_properties.get("T_F", 200),
            MW=fluid_properties.get("MW", 30),
            Z=fluid_properties.get("Z", 0.9),
            gamma=fluid_properties.get("gamma", 1.2)
        )

    else:
        raise ValueError(f"Unknown scenario: {scenario}")


if __name__ == "__main__":
    # Test fire wetted case
    print("Testing Fire Wetted Case")
    print("=" * 50)

    result = calculate_psv_size(
        scenario="fire_wetted",
        set_pressure_psig=150,
        fluid_properties={
            "MW": 44,
            "Z": 0.85,
            "gamma": 1.15,
            "T_F": 200,
            "latent_heat_btu_lb": 140
        },
        vessel_properties={
            "wetted_area_ft2": 500,
            "insulated": False,
            "F_env": 1.0
        }
    )

    for key, value in result.items():
        print(f"{key}: {value}")
