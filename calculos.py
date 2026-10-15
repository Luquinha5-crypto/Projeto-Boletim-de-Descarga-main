"""Regras de cálculo e conferência da Autorização de Descarga (sem nada de PDF aqui).

Fórmulas lidas da planilha original (aplicam-se ao ETANOL):
  fator de correção  ~ 1 - 0,00109 * (T_tanque - 20)      (célula F64)
  volume a 20 ºC     = volume ambiente * fator
  grau INPM          = -346,2 * dens_20 + 373,4 (máx 100) (célula F59)

ATENÇÃO: o coeficiente 0,00109 é uma aproximação. A planilha usava a função
`fator` (tabela oficial), que não sobreviveu ao .XLS. Por isso a diferença
tolerada no fator é pequena mas existe (ver TOLERANCIAS) e o volume é
conferido com o fator impresso na NF, não com o recalculado.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

COEF_DILATACAO_ALCOOL = 0.00109  # por ºC, vem da célula F64
LIMITES = {  # linhas 67-68 da planilha
    "temperatura": (5, 45),
    "dens_ambiente": (0.696, 0.9969),
    "dens_20": (0.7893, 0.8139),
}
TOLERANCIAS = {"fator": 0.0001, "volume": 3}  # linha 62
MAX_LACRES = 15  # B22:H22 (7) + A23 (1) + B23:H23 (7)


@dataclass
class Autorizacao:
    """Dados do formulário. None = não veio da NF (sai em branco no PDF)."""
    usina: Optional[str] = None
    produto: Optional[str] = None
    nota_fiscal: Optional[str] = None
    data_nf: Optional[str] = None            # "09/10/2026"
    transportador: Optional[str] = None
    placa_cavalo: Optional[str] = None
    placas_carreta: list = field(default_factory=list)
    lacres: list = field(default_factory=list)
    temp_tanque: Optional[float] = None
    temp_amostra: Optional[float] = None
    dens_ambiente: Optional[float] = None
    dens_20: Optional[float] = None
    teor_alcoolico: Optional[float] = None
    acidez: Optional[float] = None
    ph: Optional[float] = None
    condutividade: Optional[float] = None
    fator_nf: Optional[float] = None         # fator impresso na NF
    volume_ambiente: Optional[int] = None    # volume manifestado
    volume_20_nf: Optional[int] = None       # volume a 20 ºC
    motorista: Optional[str] = None
    cpf: Optional[str] = None
    emitido_em: datetime = field(default_factory=datetime.now)

    def faltando(self) -> list[str]:
        """Nomes dos campos que ficaram vazios (para o operador completar)."""
        vazios = [k for k, v in self.__dict__.items()
                  if k != "emitido_em" and v in (None, "", [])]
        if self.placa_cavalo and not self.placas_carreta and "placas_carreta" not in vazios:
            vazios.append("placas_carreta")
        return vazios


def eh_alcool(produto: Optional[str]) -> bool:
    p = (produto or "").upper()
    return any(k in p for k in ("ETANOL", "ALCOOL", "HIDRATADO", "ANIDRO"))


def fator_correcao(temp_tanque: float) -> float:
    return round(1 - COEF_DILATACAO_ALCOOL * (temp_tanque - 20), 4)


def inpm(dens_20: float) -> float:
    return round(min(100.0, -346.2 * dens_20 + 373.4), 2)


def _ate(diferenca: float, tolerancia: float) -> bool:
    """|diferença| <= tolerância, sem o erro de ponto flutuante (0,998-0,9979 > 0,0001 em float!)."""
    return round(abs(diferenca), 6) <= tolerancia


def conferir(a: Autorizacao) -> list[dict]:
    """Compara o que veio na NF com o recalculado.

    ok = True (confere), False (diverge) ou None (não deu para verificar: dado ausente
    ou produto sem fórmula).
    """
    r = []

    def add(item, nf, calc, ok):
        r.append({"item": item, "nf": nf, "calculado": calc, "ok": ok})

    alcool = eh_alcool(a.produto)
    lo, hi = LIMITES["temperatura"]
    add("Temperatura do tanque na faixa", a.temp_tanque, f"{lo}–{hi}",
        None if a.temp_tanque is None else lo <= a.temp_tanque <= hi)

    if alcool:
        if a.temp_tanque is not None and a.fator_nf is not None:
            f = fator_correcao(a.temp_tanque)
            add("Fator de correção (aprox. linear)", a.fator_nf, f, _ate(a.fator_nf - f, TOLERANCIAS["fator"]))
        else:
            add("Fator de correção (aprox. linear)", a.fator_nf, None, None)
        if a.volume_ambiente is not None and a.fator_nf is not None and a.volume_20_nf is not None:
            v = round(a.volume_ambiente * a.fator_nf)
            add("Volume a 20 ºC = ambiente × fator da NF", a.volume_20_nf, v,
                _ate(a.volume_20_nf - v, TOLERANCIAS["volume"]))
        else:
            add("Volume a 20 ºC = ambiente × fator da NF", a.volume_20_nf, None, None)
        if a.dens_20 is not None and a.teor_alcoolico is not None:
            g = inpm(a.dens_20)
            add("Teor alcoólico (INPM)", a.teor_alcoolico, g, -0.2 <= a.teor_alcoolico - g <= 0.1)
        else:
            add("Teor alcoólico (INPM)", a.teor_alcoolico, None, None)
        for nome, val, chave in (("Densidade ambiente na faixa", a.dens_ambiente, "dens_ambiente"),
                                 ("Densidade a 20 ºC na faixa", a.dens_20, "dens_20")):
            lo_d, hi_d = LIMITES[chave]
            add(nome, val, f"{lo_d}–{hi_d}", None if val is None else lo_d <= val <= hi_d)
    else:
        add("Fator, volume, INPM e densidades", None, "sem fórmula para este produto", None)

    add("Lacres cabem no formulário", len(a.lacres), f"≤ {MAX_LACRES}", len(a.lacres) <= MAX_LACRES)
    return r
