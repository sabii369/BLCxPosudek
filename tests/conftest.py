"""Společné nastavení testů: balíček blc z kořene repozitáře, grafy bez okna."""
import os
import sys

import matplotlib

matplotlib.use("Agg")

KOREN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if KOREN not in sys.path:
    sys.path.insert(0, KOREN)
