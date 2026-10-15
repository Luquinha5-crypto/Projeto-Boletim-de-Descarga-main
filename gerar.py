"""Gera o Boletim de Descarga (PDF) a partir de NF-e em XML.

Uso:
  python gerar.py nota.xml                       -> saida/boletim_NF<numero>.pdf
  python gerar.py nota.xml --extra extra.json    -> completa o que a NF não traz (temp. amostra, pH, motorista...)
  python gerar.py pasta_com_xmls\\                -> um PDF por XML
  python gerar.py nota.xml -o outra_pasta

O que não vier da NF nem do --extra sai EM BRANCO no PDF (para preencher à mão). Nada é inventado.
"""
import argparse
import dataclasses
import json
import sys
from pathlib import Path

from calculos import Autorizacao, conferir
from gerar_pdf import gerar_pdf
from leitor_nfe import ler_nfe

CAMPOS_VALIDOS = {f.name for f in dataclasses.fields(Autorizacao)} - {"emitido_em"}


def aplicar_extra(aut: Autorizacao, caminho: Path) -> None:
    """Valores do --extra têm prioridade sobre o que foi lido da NF."""
    extra = json.loads(caminho.read_text(encoding="utf-8"))
    desconhecidos = set(extra) - CAMPOS_VALIDOS
    if desconhecidos:  # erro de digitação no nome do campo não pode passar em silêncio
        raise SystemExit(f"Campos desconhecidos em {caminho.name}: {sorted(desconhecidos)}\n"
                         f"Campos válidos: {sorted(CAMPOS_VALIDOS)}")
    for chave, valor in extra.items():
        setattr(aut, chave, valor)


def processar(xml: Path, pasta_saida: Path, extra: Path | None) -> int:
    print(f"\n=== {xml.name}")
    try:
        aut, avisos = ler_nfe(str(xml))
    except Exception as e:  # XML inválido, não é NF-e, etc.
        print(f"  ERRO ao ler o arquivo: {e}")
        return 3
    if extra:
        aplicar_extra(aut, extra)

    print(f"  NF {aut.nota_fiscal} | {aut.usina} | {aut.produto}")
    divergencias = 0
    print("  Conferência (NF x recalculado):")
    for v in conferir(aut):
        marca = {True: "OK  ", False: "ERRO", None: " -- "}[v["ok"]]
        divergencias += v["ok"] is False
        print(f"    [{marca}] {v['item']}: NF={v['nf']}  calculado={v['calculado']}")

    # avisos do leitor, menos os "Não encontrado" (substituídos pela lista atualizada, já com o --extra)
    for a in (x for x in avisos if not x.startswith("Não encontrado")):
        print(f"  AVISO: {a}")
    vazios = aut.faltando()
    if vazios:
        print(f"  Em branco no PDF (preencher à mão ou usar --extra): {', '.join(vazios)}")

    pasta_saida.mkdir(parents=True, exist_ok=True)
    pdf = pasta_saida / f"boletim_NF{aut.nota_fiscal or xml.stem}.pdf"
    gerar_pdf(aut, str(pdf))
    print(f"  PDF: {pdf}")
    if divergencias:
        print("  ATENÇÃO: há divergências. Confira a NF antes de imprimir.")
        return 2
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="NF-e (XML) -> Boletim de Descarga (PDF)")
    p.add_argument("entrada", type=Path, nargs="+", help="arquivo .xml ou pasta com .xml")
    p.add_argument("--extra", type=Path, help="JSON com campos que a NF não traz")
    p.add_argument("-o", "--saida", type=Path, default=Path("saida"), help="pasta dos PDFs (padrão: saida)")
    args = p.parse_args()

    xmls: list[Path] = []
    for e in args.entrada:
        xmls += sorted(e.glob("*.xml")) if e.is_dir() else [e]
    if not xmls:
        print("Nenhum XML encontrado.")
        return 1
    codigos = [processar(x, args.saida, args.extra) for x in xmls]
    return max(codigos)


if __name__ == "__main__":
    sys.exit(main())
