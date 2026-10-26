"""Junta 2 ou mais NFs da MESMA viagem em um único boletim.

Contexto: a mesma carga sai em várias NFs (volume fracionado) e as NFs nem sempre vêm completas: uma traz
temperatura, densidade e lacres; a outra traz só a placa e o volume (falta de padronização da usina).

Regras (combinadas com o usuário):
  - nota_fiscal  -> "NF1 / NF2 / ..."        volume_20_nf -> SOMA dos volumes
  - campo VAZIO numa NF e preenchido em outra  -> COMPLETA com o valor que existe (e avisa de onde veio)
  - dois valores PREENCHIDOS e diferentes      -> CONFLITO: não junta e diz qual campo (não escolhemos em silêncio)
  - diferenças só de escrita (caixa, espaço, hífen, ordem dos lacres) NÃO são conflito
  - só completa se as NFs tiverem um IDENTIFICADOR FORTE em comum (mesmo cavalo ou mesmos lacres):
    sem isso, completar poderia misturar dados de caminhões diferentes
"""
import dataclasses
import re
from typing import Optional

from calculos import Autorizacao

# campos que descrevem a CARGA e, portanto, não podem mudar entre as NFs da mesma viagem
CAMPOS_CARGA = [
    "usina", "produto", "transportador", "placa_cavalo", "placas_carreta", "lacres",
    "temp_tanque", "temp_amostra", "dens_ambiente", "dens_20", "teor_alcoolico",
    "acidez", "ph", "condutividade", "fator_nf", "volume_ambiente", "motorista", "cpf",
]


def _vazio(valor) -> bool:
    return valor in (None, "", [])


def _norm(valor):
    """Forma de COMPARAR (nunca a que vai para o boletim): sem espaço/hífen/ponto, maiúsculas, listas sem ordem."""
    if isinstance(valor, str):
        return re.sub(r"[\s\-.]", "", valor).upper()
    if isinstance(valor, list):
        return sorted(_norm(v) for v in valor)
    return valor


def _listas_compativeis(listas) -> bool:
    """Lacres/carretas: compatíveis se, duas a duas, UMA CONTÉM A OUTRA (iguais, ou uma é parte da outra).
    Números repetidos aparecem uma vez só (união); números diferentes dos dois lados = conflito."""
    conjuntos = [set(_norm(lista)) for lista in listas if not _vazio(lista)]
    return all(x <= y or y <= x for x in conjuntos for y in conjuntos)


def divergencias(auts: list[Autorizacao]) -> dict[str, list]:
    """{campo: [valor de cada NF]} só para CONFLITOS REAIS (2+ valores preenchidos e diferentes).
    Campo vazio numa NF não é conflito: é lacuna a completar. Em listas (lacres), parte de outra lista não é conflito."""
    achados = {}
    for campo in CAMPOS_CARGA:
        valores = [getattr(a, campo) for a in auts]
        if any(isinstance(v, list) for v in valores):
            conflito = not _listas_compativeis(valores)
        else:
            conflito = len({repr(_norm(v)) for v in valores if not _vazio(v)}) > 1
        if conflito:
            achados[campo] = valores
    return achados


conflitos = divergencias        # mesmo conceito, nome usado nos testes de "dado faltando"


def _identificador_forte(auts: list[Autorizacao]) -> bool:
    """Mesmo cavalo em TODAS as NFs, ou lacres em TODAS com pelo menos um número em comum a todas."""
    if all(a.placa_cavalo for a in auts) and len({_norm(a.placa_cavalo) for a in auts}) == 1:
        return True
    return all(a.lacres for a in auts) and bool(set.intersection(*[set(_norm(a.lacres)) for a in auts]))


def juntar_com_relatorio(auts: list[Autorizacao]) -> tuple[Autorizacao, dict[str, tuple]]:
    """(boleto unido, completados). completados = {campo: (NF de onde veio, [NFs onde faltava ou estava incompleto])}.
    ValueError se não puderem ser unidas."""
    if len(auts) < 2:
        raise ValueError("Preciso de pelo menos 2 NFs para juntar.")
    numeros = [a.nota_fiscal for a in auts]
    if len(set(numeros)) != len(numeros):
        raise ValueError(f"NF repetida na lista: {numeros}")
    conflitos = divergencias(auts)
    if conflitos:
        detalhe = "; ".join(f"{campo}: {valores}" for campo, valores in conflitos.items())
        raise ValueError(f"As NFs têm valores diferentes no mesmo campo (conflito) -> {detalhe}")
    if not _identificador_forte(auts):
        raise ValueError("Sem identificador forte em comum (cavalo ou lacres) entre as NFs: não dá para afirmar "
                         "que são da mesma viagem. Confira e, se forem, informe o dado que falta (--extra).")

    unido, completados = {}, {}
    for campo in CAMPOS_CARGA:
        com_valor = [(a.nota_fiscal, getattr(a, campo)) for a in auts if not _vazio(getattr(a, campo))]
        if com_valor and isinstance(com_valor[0][1], list):
            # lista (lacres, carretas): como todas são parte da maior, a maior É a união, sem repetidos
            origem, maior = max(com_valor, key=lambda par: len(par[1]))
            unido[campo] = list(maior)
            faltando_em = [a.nota_fiscal for a in auts
                           if set(_norm(getattr(a, campo))) != set(_norm(maior))]
        elif com_valor:
            origem, unido[campo] = com_valor[0]
            faltando_em = [a.nota_fiscal for a in auts if _vazio(getattr(a, campo))]
        else:
            unido[campo], origem, faltando_em = getattr(auts[0], campo), None, []
        if faltando_em:
            completados[campo] = (origem, faltando_em)

    datas = list(dict.fromkeys(a.data_nf for a in auts if a.data_nf))
    volumes = [a.volume_20_nf for a in auts]
    soma: Optional[int] = None if any(v is None for v in volumes) else sum(volumes)
    boletim = dataclasses.replace(auts[0], **unido, nota_fiscal=" / ".join(n for n in numeros if n),
                                  data_nf=" / ".join(datas) or None, volume_20_nf=soma)
    return boletim, completados


def juntar(auts: list[Autorizacao], avisos: Optional[list[str]] = None) -> Autorizacao:
    """O boletim unido. Se `avisos` for dada, recebe uma linha para cada campo COMPLETADO
    (ex.: 'COMPLETADO temp_tanque veio só da NF 1 (faltava ou incompleto na NF 2). Confira.')."""
    boletim, completados = juntar_com_relatorio(auts)
    if avisos is not None:
        for campo, (origem, faltava_em) in completados.items():
            avisos.append(f"COMPLETADO {campo} veio só da NF {origem} (faltava ou incompleto na NF {', '.join(faltava_em)}). Confira.")
    return boletim


def _mesma_viagem(a: Autorizacao, b: Autorizacao) -> bool:
    """Sugestão (o usuário confirma): mesmo cavalo e mesma data; lacres, se as duas tiverem, compatíveis."""
    if not (a.placa_cavalo and b.placa_cavalo) or _norm(a.placa_cavalo) != _norm(b.placa_cavalo):
        return False
    if a.data_nf != b.data_nf:
        return False
    if not _listas_compativeis([a.lacres, b.lacres]):
        return False       # lacres diferentes = cargas diferentes, mesmo caminhão no mesmo dia
    return True


def sugerir_grupos(auts: list[Autorizacao]) -> list[list[Autorizacao]]:
    """Grupos de 2+ NFs que PARECEM a mesma viagem (todas compatíveis entre si, duas a duas)."""
    grupos: list[list[Autorizacao]] = []
    for a in auts:
        for g in grupos:
            if all(_mesma_viagem(a, outra) for outra in g):
                g.append(a)
                break
        else:
            grupos.append([a])
    return [g for g in grupos if len(g) > 1]
