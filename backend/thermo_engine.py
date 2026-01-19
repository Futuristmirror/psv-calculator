"""
Thermodynamic Engine for PSV Calculator
Implements Peng-Robinson EOS for hydrocarbon mixtures

Author: Franc Engineering
"""

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

# Universal gas constant
R = 8.314462  # J/(mol·K)
R_BTU = 1.9858775  # BTU/(lbmol·R)


@dataclass
class Component:
    """Pure component properties"""
    name: str
    formula: str
    mw: float  # g/mol
    tc: float  # K (critical temperature)
    pc: float  # Pa (critical pressure)
    omega: float  # acentric factor
    lfl: Optional[float] = None  # vol% Lower Flammability Limit
    ufl: Optional[float] = None  # vol% Upper Flammability Limit


# Component Database - Critical properties from DIPPR/experiment
COMPONENTS = {
    "methane": Component("Methane", "CH4", 16.043, 190.56, 4599000, 0.0115, 5.0, 15.0),
    "ethane": Component("Ethane", "C2H6", 30.070, 305.32, 4872000, 0.0995, 3.0, 12.4),
    "propane": Component("Propane", "C3H8", 44.096, 369.83, 4248000, 0.1523, 2.1, 9.5),
    "isobutane": Component("Isobutane", "iC4H10", 58.122, 407.85, 3640000, 0.1835, 1.8, 8.4),
    "n-butane": Component("n-Butane", "nC4H10", 58.122, 425.12, 3796000, 0.2002, 1.8, 8.4),
    "isopentane": Component("Isopentane", "iC5H12", 72.149, 460.35, 3381000, 0.2275, 1.4, 7.6),
    "n-pentane": Component("n-Pentane", "nC5H12", 72.149, 469.70, 3370000, 0.2515, 1.4, 7.8),
    "n-hexane": Component("n-Hexane", "C6H14", 86.175, 507.60, 3025000, 0.3013, 1.2, 7.4),
    "n-heptane": Component("n-Heptane", "C7H16", 100.202, 540.20, 2740000, 0.3495, 1.05, 6.7),
    "n-octane": Component("n-Octane", "C8H18", 114.229, 568.70, 2490000, 0.3996, 1.0, 6.5),
    "n-nonane": Component("n-Nonane", "C9H20", 128.255, 594.60, 2290000, 0.4435, 0.8, 5.9),
    "n-decane": Component("n-Decane", "C10H22", 142.282, 617.70, 2110000, 0.4923, 0.8, 5.4),
    "nitrogen": Component("Nitrogen", "N2", 28.014, 126.20, 3398000, 0.0377, None, None),
    "oxygen": Component("Oxygen", "O2", 31.999, 154.58, 5043000, 0.0222, None, None),
    "co2": Component("Carbon Dioxide", "CO2", 44.010, 304.21, 7383000, 0.2236, None, None),
    "h2s": Component("Hydrogen Sulfide", "H2S", 34.081, 373.53, 8963000, 0.0942, 4.0, 44.0),
    "water": Component("Water", "H2O", 18.015, 647.10, 22064000, 0.3449, None, None),
}

# Binary Interaction Parameters (kij) for Peng-Robinson
# Symmetric matrix: kij = kji
BINARY_PARAMS = {
    ("methane", "ethane"): 0.0,
    ("methane", "propane"): 0.0,
    ("methane", "n-butane"): 0.0,
    ("methane", "co2"): 0.1,
    ("methane", "h2s"): 0.08,
    ("methane", "nitrogen"): 0.036,
    ("methane", "water"): 0.5,
    ("ethane", "propane"): 0.0,
    ("ethane", "co2"): 0.13,
    ("ethane", "h2s"): 0.085,
    ("propane", "co2"): 0.13,
    ("propane", "h2s"): 0.09,
    ("co2", "h2s"): 0.1,
    ("nitrogen", "co2"): -0.02,
    ("nitrogen", "oxygen"): -0.012,
}


def get_kij(comp1: str, comp2: str) -> float:
    """Get binary interaction parameter for component pair"""
    if comp1 == comp2:
        return 0.0
    key1 = (comp1.lower(), comp2.lower())
    key2 = (comp2.lower(), comp1.lower())
    return BINARY_PARAMS.get(key1, BINARY_PARAMS.get(key2, 0.0))


class PengRobinson:
    """Peng-Robinson Equation of State for mixture calculations"""

    def __init__(self, components: List[str], mole_fractions: List[float]):
        """
        Initialize PR-EOS for a mixture

        Args:
            components: List of component names (must be in COMPONENTS dict)
            mole_fractions: List of mole fractions (must sum to 1.0)
        """
        if abs(sum(mole_fractions) - 1.0) > 0.001:
            raise ValueError(f"Mole fractions must sum to 1.0, got {sum(mole_fractions)}")

        self.comp_names = [c.lower() for c in components]
        self.z = mole_fractions
        self.n = len(components)

        # Get component objects
        self.comps = []
        for name in self.comp_names:
            if name not in COMPONENTS:
                raise ValueError(f"Unknown component: {name}")
            self.comps.append(COMPONENTS[name])

        # Calculate mixture molecular weight
        self.mw = sum(z * c.mw for z, c in zip(self.z, self.comps))

    def _alpha(self, comp: Component, T: float) -> float:
        """Calculate alpha function for component at temperature T"""
        Tr = T / comp.tc
        kappa = 0.37464 + 1.54226 * comp.omega - 0.26992 * comp.omega**2
        return (1 + kappa * (1 - math.sqrt(Tr)))**2

    def _a_comp(self, comp: Component, T: float) -> float:
        """Calculate 'a' parameter for pure component"""
        alpha = self._alpha(comp, T)
        return 0.45724 * (R**2) * (comp.tc**2) / comp.pc * alpha

    def _b_comp(self, comp: Component) -> float:
        """Calculate 'b' parameter for pure component"""
        return 0.07780 * R * comp.tc / comp.pc

    def mixture_params(self, T: float) -> Tuple[float, float]:
        """
        Calculate mixture a and b parameters using van der Waals mixing rules

        Returns:
            Tuple of (a_mix, b_mix)
        """
        # Pure component parameters
        a = [self._a_comp(c, T) for c in self.comps]
        b = [self._b_comp(c) for c in self.comps]

        # Mixing rules with binary interaction parameters
        a_mix = 0.0
        for i in range(self.n):
            for j in range(self.n):
                kij = get_kij(self.comp_names[i], self.comp_names[j])
                a_mix += self.z[i] * self.z[j] * math.sqrt(a[i] * a[j]) * (1 - kij)

        b_mix = sum(self.z[i] * b[i] for i in range(self.n))

        return a_mix, b_mix

    def compressibility(self, T: float, P: float, phase: str = "vapor") -> float:
        """
        Calculate compressibility factor Z by solving cubic EOS

        Args:
            T: Temperature in Kelvin
            P: Pressure in Pa
            phase: "vapor" or "liquid"

        Returns:
            Compressibility factor Z
        """
        a_mix, b_mix = self.mixture_params(T)

        # Dimensionless parameters
        A = a_mix * P / (R**2 * T**2)
        B = b_mix * P / (R * T)

        # Cubic equation: Z^3 + p*Z^2 + q*Z + r = 0
        # where: Z^3 - (1-B)*Z^2 + (A-3B^2-2B)*Z - (AB-B^2-B^3) = 0
        p = -(1 - B)
        q = A - 3*B**2 - 2*B
        r = -(A*B - B**2 - B**3)

        # Solve cubic using Cardano's formula
        roots = self._solve_cubic(p, q, r)

        # Filter valid roots (Z > B, Z > 0)
        valid_roots = [z for z in roots if z > B and z > 0]

        if not valid_roots:
            # Fallback to ideal gas
            return 1.0

        if phase.lower() == "vapor":
            return max(valid_roots)
        else:
            return min(valid_roots)

    def _solve_cubic(self, p: float, q: float, r: float) -> List[float]:
        """Solve cubic equation x^3 + px^2 + qx + r = 0"""
        # Convert to depressed cubic t^3 + at + b = 0
        a = q - p**2 / 3
        b = r - p*q/3 + 2*p**3/27

        discriminant = (b/2)**2 + (a/3)**3

        roots = []

        if discriminant > 0:
            # One real root
            sqrt_disc = math.sqrt(discriminant)
            u = (-b/2 + sqrt_disc)**(1/3) if (-b/2 + sqrt_disc) >= 0 else -(-(-b/2 + sqrt_disc))**(1/3)
            v = (-b/2 - sqrt_disc)**(1/3) if (-b/2 - sqrt_disc) >= 0 else -(-(-b/2 - sqrt_disc))**(1/3)
            t1 = u + v
            roots.append(t1 - p/3)
        else:
            # Three real roots
            r_val = math.sqrt(-(a/3)**3)
            theta = math.acos(-b / (2 * r_val)) if r_val != 0 else 0

            for k in range(3):
                t = 2 * (-(a/3))**0.5 * math.cos((theta + 2*math.pi*k) / 3)
                roots.append(t - p/3)

        return [r for r in roots if isinstance(r, (int, float)) and not math.isnan(r)]

    def density(self, T: float, P: float, phase: str = "vapor") -> float:
        """
        Calculate density in kg/m³

        Args:
            T: Temperature in Kelvin
            P: Pressure in Pa
            phase: "vapor" or "liquid"
        """
        Z = self.compressibility(T, P, phase)
        # rho = PM / ZRT
        return P * (self.mw / 1000) / (Z * R * T)

    def cp_ideal(self, T: float) -> float:
        """
        Estimate ideal gas Cp using correlation (J/mol·K)
        Simplified correlation - for rigorous work, use component-specific polynomials
        """
        # Simple estimate based on MW (rough but reasonable for hydrocarbons)
        # More accurate would use DIPPR polynomials per component
        cp_contributions = []
        for z, comp in zip(self.z, self.comps):
            # Rough correlation: Cp/R ≈ 3.5 + 0.05*MW for hydrocarbons at moderate T
            cp_i = R * (3.5 + 0.05 * comp.mw) * (1 + 0.001 * (T - 298))
            cp_contributions.append(z * cp_i)
        return sum(cp_contributions)

    def gamma(self, T: float, P: float) -> float:
        """
        Calculate heat capacity ratio Cp/Cv for vapor phase

        Uses: Cv = Cp - R for ideal gas approximation
        """
        cp = self.cp_ideal(T)
        cv = cp - R
        return cp / cv if cv > 0 else 1.3  # Fallback

    def lfl_mixture(self) -> Optional[float]:
        """Calculate mixture LFL using Le Chatelier's rule"""
        weighted_inv = 0.0
        total_flammable = 0.0

        for z, comp in zip(self.z, self.comps):
            if comp.lfl is not None and comp.lfl > 0:
                weighted_inv += z / comp.lfl
                total_flammable += z

        if weighted_inv > 0 and total_flammable > 0:
            return total_flammable / weighted_inv
        return None

    def ufl_mixture(self) -> Optional[float]:
        """Calculate mixture UFL using Le Chatelier's rule"""
        weighted_inv = 0.0
        total_flammable = 0.0

        for z, comp in zip(self.z, self.comps):
            if comp.ufl is not None and comp.ufl > 0:
                weighted_inv += z / comp.ufl
                total_flammable += z

        if weighted_inv > 0 and total_flammable > 0:
            return total_flammable / weighted_inv
        return None

    def flash_estimate(self, T: float, P: float) -> Dict:
        """
        Simple flash calculation estimate
        Returns vapor fraction and phase properties

        Note: For rigorous VLE, use iterative Rachford-Rice with K-values
        This is a simplified estimate using Wilson K-values
        """
        # Wilson correlation for K-values
        K = []
        for comp in self.comps:
            Tr = T / comp.tc
            Pr = P / comp.pc
            K_i = (comp.pc / P) * math.exp(5.373 * (1 + comp.omega) * (1 - comp.tc / T))
            K.append(K_i)

        # Check if all vapor or all liquid
        sum_Kz = sum(K[i] * self.z[i] for i in range(self.n))
        sum_z_K = sum(self.z[i] / K[i] for i in range(self.n))

        if sum_Kz <= 1.0:
            # All liquid
            return {
                "vapor_fraction": 0.0,
                "liquid_fraction": 1.0,
                "phase": "liquid",
                "K_values": K
            }
        elif sum_z_K <= 1.0:
            # All vapor
            return {
                "vapor_fraction": 1.0,
                "liquid_fraction": 0.0,
                "phase": "vapor",
                "K_values": K
            }
        else:
            # Two-phase - solve Rachford-Rice
            # Simplified: estimate VF
            VF = (sum_Kz - 1) / (sum_Kz - sum_z_K) if (sum_Kz - sum_z_K) != 0 else 0.5
            VF = max(0, min(1, VF))

            return {
                "vapor_fraction": VF,
                "liquid_fraction": 1 - VF,
                "phase": "two-phase",
                "K_values": K
            }


def get_properties(components: List[str], mole_fractions: List[float],
                   T_K: float, P_Pa: float) -> Dict:
    """
    Main function to get all thermodynamic properties for a mixture

    Args:
        components: List of component names
        mole_fractions: List of mole fractions
        T_K: Temperature in Kelvin
        P_Pa: Pressure in Pascals

    Returns:
        Dictionary of calculated properties
    """
    pr = PengRobinson(components, mole_fractions)
    flash = pr.flash_estimate(T_K, P_Pa)

    # Determine primary phase for property calculations
    phase = "vapor" if flash["vapor_fraction"] > 0.5 else "liquid"

    return {
        "mw": pr.mw,
        "mw_units": "g/mol",
        "Z": pr.compressibility(T_K, P_Pa, phase),
        "density": pr.density(T_K, P_Pa, phase),
        "density_units": "kg/m³",
        "gamma": pr.gamma(T_K, P_Pa),
        "cp_ideal": pr.cp_ideal(T_K),
        "cp_units": "J/(mol·K)",
        "lfl": pr.lfl_mixture(),
        "ufl": pr.ufl_mixture(),
        "flash": flash,
        "T_K": T_K,
        "P_Pa": P_Pa
    }


# Preset compositions for common fluids
PRESETS = {
    "natural_gas": {
        "components": ["methane", "ethane", "propane", "n-butane", "co2", "nitrogen"],
        "mole_fractions": [0.85, 0.07, 0.03, 0.02, 0.02, 0.01]
    },
    "rich_gas": {
        "components": ["methane", "ethane", "propane", "isobutane", "n-butane", "isopentane", "n-pentane", "co2"],
        "mole_fractions": [0.70, 0.12, 0.08, 0.03, 0.03, 0.01, 0.01, 0.02]
    },
    "propane": {
        "components": ["propane"],
        "mole_fractions": [1.0]
    },
    "butane_mix": {
        "components": ["isobutane", "n-butane"],
        "mole_fractions": [0.5, 0.5]
    },
    "crude_oil_vapor": {
        "components": ["methane", "ethane", "propane", "n-butane", "n-pentane", "n-hexane", "n-heptane"],
        "mole_fractions": [0.30, 0.15, 0.15, 0.12, 0.10, 0.10, 0.08]
    }
}


if __name__ == "__main__":
    # Test with natural gas composition
    print("Testing Peng-Robinson EOS with Natural Gas")
    print("=" * 50)

    props = get_properties(
        components=["methane", "ethane", "propane", "n-butane", "co2", "nitrogen"],
        mole_fractions=[0.85, 0.07, 0.03, 0.02, 0.02, 0.01],
        T_K=300,  # ~80°F
        P_Pa=1e6  # ~145 psia
    )

    print(f"Molecular Weight: {props['mw']:.2f} g/mol")
    print(f"Compressibility Z: {props['Z']:.4f}")
    print(f"Density: {props['density']:.2f} kg/m³")
    print(f"Cp/Cv (gamma): {props['gamma']:.3f}")
    print(f"LFL: {props['lfl']:.2f}%" if props['lfl'] else "LFL: N/A")
    print(f"UFL: {props['ufl']:.2f}%" if props['ufl'] else "UFL: N/A")
    print(f"Phase: {props['flash']['phase']}")
