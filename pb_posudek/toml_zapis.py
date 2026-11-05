"""Jednoduchý zápis vstupních dat do TOML (tomllib umí pouze čtení)."""
from __future__ import annotations

import json
import math


def _hodnota(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        if math.isnan(v) or math.isinf(v):
            raise ValueError("TOML nepodporuje NaN/inf")
        return repr(v)
    if isinstance(v, str):
        return json.dumps(v, ensure_ascii=False)
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(_hodnota(i) for i in v) + "]"
    if isinstance(v, dict):
        return "{ " + ", ".join(f"{_klic(k)} = {_hodnota(i)}" for k, i in v.items() if i is not None) + " }"
    raise TypeError(f"Nepodporovaný typ pro TOML: {type(v)}")


def _klic(k: str) -> str:
    return k if k.replace("_", "").replace("-", "").isalnum() and k.isascii() else json.dumps(k, ensure_ascii=False)


def _je_pole_tabulek(v) -> bool:
    return isinstance(v, list) and len(v) > 0 and all(isinstance(i, dict) for i in v)


def _tabulka(radky: list[str], d: dict):
    for k, v in d.items():
        if v is None or _je_pole_tabulek(v):
            continue
        radky.append(f"{_klic(k)} = {_hodnota(v)}")


def dumps(data: dict) -> str:
    radky: list[str] = []
    for sekce, obsah in data.items():
        if isinstance(obsah, dict):
            pod = {k: v for k, v in obsah.items() if _je_pole_tabulek(v)}
            ostatni = {k: v for k, v in obsah.items() if k not in pod}
            if ostatni or not pod:
                radky.append(f"[{_klic(sekce)}]")
                _tabulka(radky, ostatni)
                radky.append("")
            for k, pole in pod.items():
                for prvek in pole:
                    radky.append(f"[[{_klic(sekce)}.{_klic(k)}]]")
                    _tabulka(radky, prvek)
                    radky.append("")
        elif _je_pole_tabulek(obsah):
            for prvek in obsah:
                radky.append(f"[[{_klic(sekce)}]]")
                _tabulka(radky, prvek)
                radky.append("")
        elif obsah is not None and not (isinstance(obsah, list) and not obsah):
            radky.insert(0, f"{_klic(sekce)} = {_hodnota(obsah)}")
    return "\n".join(radky).rstrip() + "\n"
