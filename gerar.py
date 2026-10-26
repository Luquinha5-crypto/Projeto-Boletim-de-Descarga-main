"""Gera o Boletim de Descarga (PDF) a partir de NF-e em XML.

Uso:
  python gerar.py nota.xml                       -> saida/boletim_NF<numero>.pdf
  python gerar.py nota.xml --extra extra.json    -> completa o que a NF não traz (temp. amostra, pH, motorista...)
  python gerar.py pasta_com_xmls\\                -> um PDF por XML (e sugere junções, se achar NFs da mesma carga)
  python gerar.py nf1.xml nf2.xml --juntar       -> UM boletim para a mesma carga fracionada em 2+ NFs
  python gerar.py nota.xml --cavalos cavalos.txt -> usa a lista de placas de cavalos (padrão: ./cavalos.txt, se existir)
  python gerar.py nota.xml -o outra_pasta
  python gerar.py nota.xml --sem-xlsx            -> só o PDF (por padrão sai também o .xlsx editável)

Junto do PDF sai um .xlsx igual ao formulário: complete o que faltar direto nele (a via da direita
se atualiza sozinha) e imprima pelo Excel. Não precisa de JSON/--extra para isso.

O que não vier da NF nem do --extra sai EM BRANCO no PDF (para preencher à mão). Nada é inventado.
"""
import argparse
import dataclasses
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from calculos import Autorizacao, conferir
from diagnostico import verificar
from gerar_pdf import gerar_pdf
from gerar_xlsx import gerar_xlsx
from juntar import juntar, sugerir_grupos
from leitor_nfe import carregar_cavalos, ler_nfe
from volume import volume_20_exibido

CAMPOS_VALIDOS = {f.name for f in dataclasses.fields(Autorizacao)} - {"emitido_em"}
NS_INFCPL = (".//{http://www.portalfiscal.inf.br/nfe}infAdic/"
             "{http://www.portalfiscal.inf.br/nfe}infCpl")


def aplicar_extra(aut: Autorizacao, caminho: Path) -> None:
    """Valores do --extra têm prioridade sobre o que foi lido da NF."""
    extra = json.loads(caminho.read_text(encoding="utf-8"))
    desconhecidos = set(extra) - CAMPOS_VALIDOS
    if desconhecidos:  # erro de digitação no nome do campo não pode passar em silêncio
        raise SystemExit(f"Campos desconhecidos em {caminho.name}: {sorted(desconhecidos)}\n"
                         f"Campos válidos: {sorted(CAMPOS_VALIDOS)}")
    for chave, valor in extra.items():
        setattr(aut, chave, valor)


def _ler(xml: Path, cavalos):
    """(Autorizacao, avisos, texto infCpl). Levanta exceção se o arquivo não for uma NF-e válida."""
    aut, avisos = ler_nfe(str(xml), cavalos)
    infcpl = ET.parse(str(xml)).getroot().findtext(NS_INFCPL, "")
    return aut, avisos, infcpl


def _emitir(aut: Autorizacao, avisos: list[str], suspeitas: list[str], pasta_saida: Path,
            nome_arquivo: str, com_xlsx: bool = True) -> int:
    """Imprime conferência/avisos, grava o PDF e devolve o código de saída (0 ok, 2 divergência)."""
    print(f"  NF {aut.nota_fiscal} | {aut.usina} | {aut.produto}")
    divergencias = 0
    print("  Conferência (NF x recalculado):")
    for v in conferir(aut):
        marca = {True: "OK  ", False: "ERRO", None: " -- "}[v["ok"]]
        divergencias += v["ok"] is False
        print(f"    [{marca}] {v['item']}: NF={v['nf']}  calculado={v['calculado']}")

    valor, origem = volume_20_exibido(aut)
    if origem == "calculado":
        print(f"  Volume a 20 ºC no boletim: {valor} (calculado: volume ambiente x fator)")
    elif origem == "nf":
        print(f"  Volume a 20 ºC no boletim: {valor} (valor/soma das NFs: faltam o volume ambiente e/ou o fator "
              f"para calcular; informe em --extra ou digite o volume ambiente na célula A38 do .xlsx)")

    # avisos do leitor, menos os "Não encontrado" (substituídos pela lista atualizada, já com o --extra)
    for a in (x for x in dict.fromkeys(avisos) if not x.startswith("Não encontrado")):
        print(f"  AVISO: {a}")
    for suspeita in dict.fromkeys(suspeitas):
        print(f"  SUSPEITA: {suspeita}")
    vazios = aut.faltando()
    if vazios:
        print(f"  Em branco no PDF (preencher à mão ou usar --extra): {', '.join(vazios)}")

    pasta_saida.mkdir(parents=True, exist_ok=True)
    pdf = pasta_saida / nome_arquivo
    gerar_pdf(aut, str(pdf))
    print(f"  PDF: {pdf}")
    if com_xlsx:
        xlsx = pdf.with_suffix(".xlsx")
        gerar_xlsx(aut, str(xlsx))
        print(f"  XLSX (editável): {xlsx}")
    if divergencias:
        print("  ATENÇÃO: há divergências. Confira a NF antes de imprimir.")
        return 2
    return 0


def processar(xml: Path, pasta_saida: Path, extra: Path | None, cavalos=None, com_xlsx: bool = True) -> int:
    """Uma NF -> um boletim."""
    print(f"\n=== {xml.name}")
    try:
        aut, avisos, infcpl = _ler(xml, cavalos)
    except Exception as e:  # XML inválido, não é NF-e, etc.
        print(f"  ERRO ao ler o arquivo: {e}")
        return 3
    if extra:
        aplicar_extra(aut, extra)
    return _emitir(aut, avisos, verificar(aut, infcpl), pasta_saida,
                   f"boletim_NF{aut.nota_fiscal or xml.stem}.pdf", com_xlsx)


def processar_junto(xmls: list[Path], pasta_saida: Path, extra: Path | None, cavalos=None,
                    com_xlsx: bool = True) -> int:
    """2+ NFs da mesma carga -> UM boletim (NF1 / NF2, volume somado)."""
    print(f"\n=== Juntando {len(xmls)} NFs: {', '.join(x.name for x in xmls)}")
    lidas = []
    for xml in xmls:
        try:
            lidas.append(_ler(xml, cavalos))
        except Exception as e:
            print(f"  ERRO ao ler {xml.name}: {e}")
            return 3
    for aut, _, _ in lidas:
        print(f"  NF {aut.nota_fiscal}: volume a 20 ºC = {aut.volume_20_nf}")
    avisos_junta: list[str] = []
    try:
        unida = juntar([aut for aut, _, _ in lidas], avisos_junta)
    except ValueError as e:
        print(f"  NÃO JUNTEI: {e}")
        return 4
    if extra:
        aplicar_extra(unida, extra)
    avisos = avisos_junta + [a for _, av, _ in lidas for a in av]
    suspeitas = [s for aut, _, txt in lidas for s in verificar(aut, txt)]
    numeros = "_".join(a.nota_fiscal or "x" for a, _, _ in lidas)
    return _emitir(unida, avisos, suspeitas, pasta_saida, f"boletim_NF{numeros}.pdf", com_xlsx)


def main() -> int:
    p = argparse.ArgumentParser(description="NF-e (XML) -> Boletim de Descarga (PDF)")
    p.add_argument("entrada", type=Path, nargs="+", help="arquivo(s) .xml ou pasta com .xml")
    p.add_argument("--extra", type=Path, help="JSON com campos que a NF não traz")
    p.add_argument("--juntar", action="store_true", help="todas as NFs dadas são da MESMA carga: gera um boletim só")
    p.add_argument("--cavalos", type=Path, help="txt com as placas dos cavalos, uma por linha (padrão: ./cavalos.txt)")
    p.add_argument("--sem-xlsx", action="store_true", help="não gerar o .xlsx editável (só o PDF)")
    p.add_argument("-o", "--saida", type=Path, default=Path("saida"), help="pasta dos PDFs (padrão: saida)")
    args = p.parse_args()

    xmls: list[Path] = []
    for e in args.entrada:
        xmls += sorted(e.glob("*.xml")) if e.is_dir() else [e]
    if not xmls:
        print("Nenhum XML encontrado.")
        return 1

    caminho_cavalos = args.cavalos or (Path("cavalos.txt") if Path("cavalos.txt").exists() else None)
    cavalos = carregar_cavalos(caminho_cavalos) if caminho_cavalos else None
    if cavalos:
        print(f"Lista de cavalos: {len(cavalos)} placa(s) em {caminho_cavalos}")

    if args.juntar:
        return processar_junto(xmls, args.saida, args.extra, cavalos, not args.sem_xlsx)

    codigos = [processar(x, args.saida, args.extra, cavalos, not args.sem_xlsx) for x in xmls]

    if len(xmls) > 1:  # sugestão: NFs com os mesmos lacres/placas/motorista parecem a mesma carga
        lidas = {}
        for x in xmls:
            try:
                lidas[x] = ler_nfe(str(x), cavalos)[0]
            except Exception:
                pass
        for grupo in sugerir_grupos(list(lidas.values())):
            nomes = [x.name for x, a in lidas.items() if a in grupo]
            print(f"\nDICA: {', '.join(nomes)} têm o mesmo cavalo e a mesma data, sem lacres diferentes (mesma viagem?). "
                  f"Se forem, rode: python gerar.py {' '.join(nomes)} --juntar")
    return max(codigos)


if __name__ == "__main__":
    sys.exit(main())
