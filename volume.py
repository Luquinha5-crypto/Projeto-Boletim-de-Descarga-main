"""Qual volume a 20 ºC vai no boletim?

Regra (como no formulário original): volume a 20 ºC = volume ambiente x fator de correção.
Só quando faltar o volume ambiente ou o fator usamos o volume impresso na NF (ou a soma das NFs
juntadas), e o programa avisa. O volume da NF continua guardado para CONFERIR o calculado.
"""
import math
from typing import Optional

from calculos import Autorizacao


def volume_20_exibido(a: Autorizacao) -> tuple[Optional[int], Optional[str]]:
    """(valor, origem). origem: 'calculado' (ambiente x fator), 'nf' (volume/soma das NFs) ou None."""
    if a.volume_ambiente is not None and a.fator_nf is not None:
        # floor(x + 0,5) = arredondamento do Excel (0,5 sobe); o round() do Python arredonda 0,5 para o par
        return math.floor(a.volume_ambiente * a.fator_nf + 0.5), "calculado"
    if a.volume_20_nf is not None:
        return a.volume_20_nf, "nf"
    return None, None
