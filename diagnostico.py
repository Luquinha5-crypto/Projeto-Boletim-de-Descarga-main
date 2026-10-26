"""Alerta de leitura: o texto da NF fala de um dado, mas o leitor NÃO o extraiu.

Por que existe: o <infCpl> é texto livre e cada usina escreve de um jeito. Quando uma usina nova usa
palavras que o leitor não conhece, o campo fica em branco SEM erro. Este módulo procura as palavras-chave
de cada dado no texto e, se achar a palavra mas o campo está vazio, avisa mostrando o trecho para você
ensinar o padrão novo (tabela PADROES de leitor_nfe.py).

Uso (gerar.py já chama): suspeitas = verificar(aut, texto_infcpl)
"""
import re

from calculos import Autorizacao

# campo da Autorizacao -> (nome legível, palavras-chave que indicam que o texto cita esse dado)
PALAVRAS = {
    "temp_tanque": ("temperatura do tanque/veículo", r"\btemp(?:eratura)?\b"),
    "temp_amostra": ("temperatura da amostra/análise", r"temperatura\s*(?:da|de|do)?\s*(?:amostra|analise|análise)"),
    "dens_ambiente": ("densidade/massa específica ambiente",
                      r"(?:densidade|massa\s*esp\w*)\s*(?:a\s*)?(?:ambiente|observada)"),
    "dens_20": ("densidade/massa específica", r"\bdens(?:idade)?\b|massa\s*esp"),
    "fator_nf": ("fator de correção/redução", r"\bfat(?:or)?\b"),
    "teor_alcoolico": ("teor alcoólico (INPM)", r"inpm|teor\s*alco"),
    "volume_ambiente": ("volume ambiente/capacidade", r"capacidade|volume\s*amb"),
    "volume_20_nf": ("volume a 20 ºC", r"volume\s*(?:a\s*)?20"),
    "lacres": ("lacres", r"lacre"),
    "motorista": ("motorista", r"motorista|condutor"),
    "cpf": ("CPF do motorista", r"cpf"),
    "placa_cavalo": ("placas", r"placa"),
}
TRECHO = 70   # caracteres de contexto mostrados em volta da palavra encontrada


def _vazio(valor) -> bool:
    return valor in (None, "", [])


def verificar(a: Autorizacao, texto: str) -> list[str]:
    """Para cada campo vazio cujo assunto aparece no texto, devolve um aviso com o trecho."""
    avisos, vistos = [], set()
    for campo, (nome, palavra) in PALAVRAS.items():
        if not _vazio(getattr(a, campo)):
            continue
        for m in re.finditer(palavra, texto, re.IGNORECASE):
            ini, fim = max(0, m.start() - 15), min(len(texto), m.end() + TRECHO)
            trecho = re.sub(r"\s+", " ", texto[ini:fim]).strip()
            if (nome, trecho) in vistos:
                continue
            vistos.add((nome, trecho))
            avisos.append(f"'{nome}' aparece no texto da NF mas não foi lido (campo {campo}): «...{trecho}...»")
            break   # um trecho por campo basta para você achar o padrão
    return avisos
