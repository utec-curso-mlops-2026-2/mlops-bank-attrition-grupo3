import numpy as np
import pandas as pd

from bank_attrition.monitoring import psi_categorical, psi_numeric, semaforo


def test_psi_misma_distribucion_es_cero():
    x = np.random.default_rng(0).normal(size=5000)
    assert psi_numeric(x, x) < 1e-6


def test_psi_detecta_desplazamiento():
    rng = np.random.default_rng(0)
    assert psi_numeric(rng.normal(0, 1, 5000), rng.normal(1.5, 1, 5000)) > 0.25


def test_psi_categorica_con_categoria_nueva():
    ref = pd.Series(["A"] * 50 + ["B"] * 50)
    cur = pd.Series(["A"] * 50 + ["C"] * 50)
    assert psi_categorical(ref, cur) > 0.25


def test_semaforo():
    assert semaforo(0.05) == "critico"
    assert semaforo(0.15) == "alerta"
    assert semaforo(0.30) == "critico"
