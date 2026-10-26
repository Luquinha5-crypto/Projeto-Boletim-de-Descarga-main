"""Lê uma NF-e (XML) e devolve (Autorizacao, avisos).

Duas fontes de informação dentro da NF-e:
  1. TAGS FIXAS  -> mesmo lugar em qualquer usina (número, data, emitente, transportador...).
  2. TEXTO LIVRE -> <infCpl> (informações complementares). Cada usina escreve de um jeito,
     então usamos uma TABELA DE PADRÕES (regex): para cada campo, uma lista de formas
     conhecidas. Formato novo de usina = acrescentar um padrão na lista, sem mexer no resto.

Regra de ouro: se não achou, devolve None e registra um aviso. Nunca chutar valor.
"""
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

from calculos import Autorizacao, eh_alcool

NS = {"n": "http://www.portalfiscal.inf.br/nfe"}

TRANSPORTADOR_FIXO = "NICHELE"   # sempre este nome no boletim; deixe "" (vazio) para ler o transportador da NF

# ---- padrões do texto livre (infCpl). Primeiro que casar vence. Sem acento: as NFs vêm sem. ----
NUM = r"([\d.,]+)"
PADROES = {
    "temp_tanque": [r"TEMPERATURA MEDIA DO\(S\) COMPARTIMENTO\(S\)\s*:\s*" + NUM,
                    r"Temperatura do veiculo\s*=\s*" + NUM,
                    r"TEMP\.\s*VEIC\.?\s*=\s*" + NUM],
    "temp_amostra": [r"Temperatura de analise\s*=\s*" + NUM,
                     r"TEMP\.\s*ENS\.?\s*=\s*" + NUM],
    "dens_ambiente": [r"Massa Especifica\s*=\s*" + NUM,
                      r"\bM\.\s*ESP\s*=\s*" + NUM],
    "dens_20": [r"DENSIDADE MEDIA A 20\s*o?C\s*:\s*" + NUM,
                r"Massa Esp\.?\s*20\s*C\s*=\s*" + NUM,
                r"M\.\s*ESP\.\s*T\.\s*E\.?\s*=\s*" + NUM],
    "fator_nf": [r"FATOR DE CORRECAO A 20\s*o?C\s*:\s*" + NUM,
                 r"Fator Reducao\s*=\s*" + NUM,
                 r"\bFATOR\s*=\s*" + NUM],
    "teor_alcoolico": [r"Grau INPM\s*=\s*" + NUM,
                       r"GRAU\s*ALC\.?\s*=\s*" + NUM],
    "volume_ambiente": [r"Capacidade Seta\s*=\s*" + NUM,
                        r"SETAVEIC\s*=\s*" + NUM],
    "volume_20_nf": [r"Volume 20C Seta\s*=\s*" + NUM,
                     r"V\.\s*FAT\.?\s*=\s*" + NUM],
    "acidez": [r"\bACIDEZ\s*=\s*" + NUM],
    "ph": [r"\bPH\s*=\s*" + NUM],
    "condutividade": [r"\bCONDUTIV\w*\.?\s*=\s*" + NUM],
}

# antiga (ABC1234) e Mercosul (ABC1D23), com ou sem hífen (ABC-1234).
# "(?<![A-Z])": não pode vir letra antes (evita pegar "FOP-5652" dentro de "CFOP-5652").
# "(?!\d)": não pode vir dígito depois (evita pegar os 7 primeiros de um código maior).
# Letras/dígitos COLADOS nos lados são aceitos de propósito: algumas NFs escrevem "PLACA2ABC4E56PR"
# (número da placa e UF grudados). O teste test_placas_do_hidratado protege esse formato.
PLACA = re.compile(r"(?<![A-Z])[A-Z]{3}-?\d[A-Z0-9]\d{2}(?!\d)")


def _achar_placas(texto: str) -> list[str]:
    """Placas do texto, sempre SEM hífen (ABC-1234 -> ABC1234)."""
    return [p.replace("-", "") for p in PLACA.findall(texto.upper())]
LACRE_TOKEN = r"[A-Z]?\d{5,9}"
SEP = r"[\s,;/\-]*"


def carregar_cavalos(caminho) -> set[str]:
    """Lê cavalos.txt: uma placa por linha; '#' começa comentário; maiúsculas, sem hífen/espaço."""
    cavalos: set[str] = set()
    for linha in Path(caminho).read_text(encoding="utf-8").splitlines():
        placa = re.sub(r"[\s\-]", "", linha.split("#")[0]).upper()
        if placa:
            cavalos.add(placa)
    return cavalos


def _num(texto: str) -> Optional[float]:
    """'21,9' -> 21.9 ; '0.9871.' -> 0.9871"""
    t = texto.strip().rstrip(".,").replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return None


def _num_volume(texto: str) -> Optional[float]:
    """Volume em pt-BR: o ponto é MILHAR. '41.915' -> 41915 ; '42.003,000' -> 42003"""
    return _num(texto.strip().rstrip(".,").replace(".", ""))


def _procurar(texto: str, chave: str) -> Optional[float]:
    conversor = _num_volume if chave.startswith("volume") else _num
    for padrao in PADROES[chave]:
        m = re.search(padrao, texto, re.IGNORECASE)
        if m:
            return conversor(m.group(1))
    return None


def _lacres(texto: str) -> list[str]:
    """Lacres da carga, SEM os lacres de amostra (que são de outro controle)."""
    # 1) apaga os trechos de amostra para não entrarem na lista
    t = re.sub(rf"(?i)lacres?\s+(?:da|das|de)?\s*amostras?(?:-testemunha)?\s*(?:n[º°o]?)?\s*[:.]?{SEP}(?:{LACRE_TOKEN}{SEP})+", " ", texto)
    t = re.sub(rf"(?i)lacre\s+amostra\s+{LACRE_TOKEN}", " ", t)
    # 2) "Lacre(s): n-n-n". Os "LA: n-n" são lacres LATERAIS (confirmado pelo usuário): não vão no boletim.
    achados: list[str] = []
    for m in re.finditer(rf"(?i)\blacres?\b\s*[:.]?{SEP}((?:{LACRE_TOKEN}{SEP})+)", t):
        achados += re.findall(LACRE_TOKEN, m.group(1))
    return list(dict.fromkeys(achados))  # tira repetidos mantendo a ordem


def _formatar_cpf(d: str) -> str:
    return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"


def _produto(descricao: str) -> str:
    d = descricao.upper()
    if "HIDRATADO" in d:
        return "HIDRATADO"
    if "ANIDRO" in d:
        return "ANIDRO"
    return descricao.strip()


def ler_nfe(caminho: str, cavalos: Optional[set] = None) -> tuple[Autorizacao, list[str]]:
    """`cavalos`: conjunto de placas de cavalos conhecidos (ver carregar_cavalos). Opcional."""
    avisos: list[str] = []
    raiz = ET.parse(caminho).getroot()
    inf = raiz.find(".//n:infNFe", NS)
    if inf is None:
        raise ValueError("Arquivo não parece uma NF-e (tag infNFe não encontrada).")

    def tag(caminho_tag: str) -> Optional[str]:
        el = inf.find(caminho_tag, NS)
        return el.text.strip() if el is not None and el.text else None

    a = Autorizacao()

    # ---- 1. tags fixas ----
    a.nota_fiscal = tag("n:ide/n:nNF")
    dh = tag("n:ide/n:dhEmi")  # '2026-10-13T12:22:44-03:00' -> pega só a data, sem converter fuso
    if dh:
        a.data_nf = f"{dh[8:10]}/{dh[5:7]}/{dh[0:4]}"
    # nome fantasia (xFant, ex.: "EMPRESA CIDADE") traz usina + cidade; xNome é a razão social, igual em todas
    a.usina = tag("n:emit/n:xFant") or tag("n:emit/n:xNome")
    a.transportador = TRANSPORTADOR_FIXO or tag("n:transp/n:transporta/n:xNome")
    desc = tag("n:det/n:prod/n:descANP") or tag("n:det/n:prod/n:xProd") or ""
    a.produto = _produto(desc)
    q = tag("n:det/n:prod/n:qTrib")
    if q and (tag("n:det/n:prod/n:uTrib") or "").upper() in ("L", "LT"):
        a.volume_20_nf = round(float(q))  # faturamento de combustível é a 20 ºC

    # ---- 2. texto livre ----
    texto = tag("n:infAdic/n:infCpl") or ""
    for campo in PADROES:
        valor = _procurar(texto, campo)
        if valor is None:
            continue
        if campo == "volume_20_nf" and a.volume_20_nf is not None:
            continue    # qTrib (quantidade DESTA NF) vence: o texto pode repetir o total da carga em cada NF fracionada
        setattr(a, campo, round(valor) if campo.startswith("volume") else valor)

    a.lacres = _lacres(texto)

    # ---- placas: tags fixas + campo extra + texto livre ----
    placas = [el.text.strip() for el in inf.findall(".//n:veicTransp/n:placa", NS) if el.text]
    placas += [el.text.strip() for el in inf.findall(".//n:reboque/n:placa", NS) if el.text]
    for el in inf.findall("n:infAdic/n:obsCont", NS):
        if el.get("xCampo") == "TRANSP_PLACAS":
            placas += _achar_placas(el.findtext("n:xTexto", "", NS))
    m_cavalo = re.search(r"(?i)cavalo\s*(" + PLACA.pattern.replace("(?<![A-Z])", "") + ")", texto)
    explicito = m_cavalo.group(1).upper().replace("-", "") if m_cavalo else None
    texto_sem_docs = re.sub(r"(CPF|CNH|RG|CNPJ|RENAVAM)[\s:]*[\d.\-]+", " ", texto, flags=re.IGNORECASE)
    placas += _achar_placas(texto_sem_docs)
    placas = list(dict.fromkeys(placas))
    if explicito:
        a.placa_cavalo = explicito
        a.placas_carreta = [p for p in placas if p != explicito]
    elif placas:
        conhecidos = [p for p in placas if cavalos and p in cavalos]
        if len(conhecidos) == 1:     # a lista de cavalos resolve: sem chute, sem aviso
            a.placa_cavalo = conhecidos[0]
            a.placas_carreta = [p for p in placas if p != conhecidos[0]]
        else:
            a.placa_cavalo, a.placas_carreta = placas[0], placas[1:]
            if cavalos and not conhecidos:
                motivo = "nenhuma das placas está na lista de cavalos"
            elif cavalos:
                motivo = "mais de uma placa está na lista de cavalos"
            else:
                motivo = "a NF não diz qual é o cavalo"
            avisos.append(f"Placas: {motivo}; assumi que a 1ª é o cavalo. Confira.")

    # ---- motorista (quando a usina informa) ----
    for padrao in (r"VEICULO\s*([A-ZÀ-Ú][A-ZÀ-Ú ]+?)\s*CPF\s*(\d{11})",
                   r"MOTORISTA\s*:\s*([A-ZÀ-Ú][A-ZÀ-Ú ]+?)\s*CPF\s*:?\s*(\d{11})"):
        m = re.search(padrao, texto)
        if m:
            a.motorista, a.cpf = m.group(1).strip(), _formatar_cpf(m.group(2))
            break

    # ---- avisos de campos que a NF não trouxe ----
    for nome in a.faltando():
        avisos.append(f"Não encontrado na NF: {nome}")
    if eh_alcool(a.produto) and a.volume_ambiente is None:
        avisos.append("Volume ambiente (manifestado) não consta na NF: informe em --extra.")
    return a, avisos
