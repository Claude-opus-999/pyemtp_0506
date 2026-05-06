"""Pipe-type cable Z/Y generation.

Calls into :mod:`LCP.cable_model` for the physics (Ametani 1980).
"""

from __future__ import annotations

from typing import Any, Optional, Tuple

import numpy as np


def _potential_to_admittance(
    freq: np.ndarray,
    P_matrix: np.ndarray,
    n_conductors: int,
) -> np.ndarray:
    """Convert potential coefficient matrix to shunt admittance.

    Handles both 2D P (n, n) — frequency-independent — and
    3D P (K, n, n) — frequency-dependent.
    """
    omega = 2.0 * np.pi * np.asarray(freq, dtype=float)
    K = len(omega)
    Y = np.zeros((K, n_conductors, n_conductors), dtype=complex)

    P = np.asarray(P_matrix, dtype=complex)

    if P.ndim == 2:
        if P.shape != (n_conductors, n_conductors):
            raise ValueError(
                f"P_matrix 2D shape mismatch: expected "
                f"{(n_conductors, n_conductors)}, got {P.shape}"
            )
        cond = np.linalg.cond(P)
        P_inv = np.linalg.pinv(P) if cond >= 1e12 else np.linalg.inv(P)
        for k, w in enumerate(omega):
            Y[k] = 1j * w * P_inv
        return Y

    if P.ndim == 3:
        if P.shape != (K, n_conductors, n_conductors):
            raise ValueError(
                f"P_matrix 3D shape mismatch: expected "
                f"{(K, n_conductors, n_conductors)}, got {P.shape}"
            )
        for k, w in enumerate(omega):
            Pk = P[k]
            cond = np.linalg.cond(Pk)
            Pk_inv = np.linalg.pinv(Pk) if cond >= 1e12 else np.linalg.inv(Pk)
            Y[k] = 1j * w * Pk_inv
        return Y

    raise ValueError(
        f"Unexpected P_matrix ndim={P.ndim}, shape={P.shape}"
    )


def compute_pipe_type_cable_zy(
    freq: np.ndarray,
    geometry_config: Any,
    *,
    soil_config: Optional[Any] = None,
    verbose: bool = False,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, dict]:
    """Compute pipe-type cable series impedance and shunt admittance matrices.

    Parameters
    ----------
    freq:
        Frequency vector in Hz (1-D, all > 0).
    geometry_config:
        A :class:`PipeTypeCableGeometry` instance from
        :mod:`LCP.cable_model`, or any object with compatible attributes.
    soil_config:
        Soil parameters.  When None, uses rho=100 Ω·m, εr=10, μr=1.

    Returns
    -------
    freq, Z_matrix (K, n, n), Y_matrix (K, n, n), metadata
    """
    from LCP.cable_model import (
        compute_pipe_type_cable_impedance as _compute_Z,
        compute_pipe_type_cable_potential as _compute_P,
    )

    cable = geometry_config

    rho = getattr(soil_config, "resistivity", 100.0) if soil_config else 100.0
    mu_r_soil = getattr(soil_config, "permeability", 1.0) if soil_config else 1.0
    eps_r = getattr(soil_config, "permittivity", 10.0) if soil_config else 10.0

    omega = 2.0 * np.pi * freq
    mu_0 = 4.0 * np.pi * 1e-7
    sigma = 1.0 / rho
    gamma_soil = np.sqrt(1j * omega * mu_0 * mu_r_soil * sigma - omega**2 * mu_0 * mu_r_soil * eps_r * 8.854e-12)

    Z_matrix = _compute_Z(freq, cable, gamma_soil)
    P_matrix = _compute_P(freq, cable)
    n = Z_matrix.shape[1]

    Y_matrix = _potential_to_admittance(freq, P_matrix, n)

    metadata = {
        "conductor_order": [
            "Core1", "Sheath1",
            "Core2", "Sheath2",
            "Core3", "Sheath3",
            "Pipe",
        ],
        "n_conductors": n,
        "P_matrix_ndim": int(P_matrix.ndim),
        "P_matrix_shape": list(P_matrix.shape),
    }

    return freq, Z_matrix, Y_matrix, metadata
