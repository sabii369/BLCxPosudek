"""Zápis čísel do textů pro uživatele (popisy, protokol, grafy) s desetinnou čárkou."""

from __future__ import annotations


def cz(v, d: int | None = None, g: bool = False) -> str:
    """Číslo s desetinnou čárkou: cz(x) = formát g, cz(x, 2) = 2 desetinná místa,
    cz(x, 3, g=True) = 3 platné číslice (formát .3g)."""
    spec = "g" if d is None else f".{d}{'g' if g else 'f'}"
    return format(float(v), spec).replace(".", ",")
