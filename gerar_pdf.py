"""Desenha a Autorização de Descarga em PDF (A4 paisagem, 2 vias lado a lado), IGUAL ao formulário original.

Como funciona
  - layout_original.json guarda, célula por célula, o que o formulário do Excel tem: largura/altura,
    células mescladas, bordas, fonte, alinhamento, rótulos e posição do logotipo
    (gerado por tools/extrair_layout.py a partir do arquivo original).
  - Aqui só ligamos os DADOS (Autorizacao) aos endereços de célula e desenhamos.
  - A via da direita espelha a da esquerda, como as fórmulas (=B13) do original.
"""
import json
import re
from pathlib import Path

from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.utils import simpleSplit
from reportlab.pdfgen import canvas

from calculos import Autorizacao
from volume import volume_20_exibido

AQUI = Path(__file__).parent
LAYOUT = json.loads((AQUI / "layout_original.json").read_text(encoding="utf-8"))
LOGO = AQUI / "assets" / "logo.jpeg"          # opcional: sem o arquivo, o PDF sai sem logotipo
DECIMAL = ","                                  # vírgula = padrão brasileiro (o Excel em pt-BR imprime assim)

COL_VIA2 = 10                                  # a via da direita começa na coluna K (índice 10)
LARGURA_LINHA = {"hair": 0.3, "thin": 0.75, "medium": 1.5, "thick": 2.25}
FONTES = {  # (família, negrito, itálico) -> fonte PDF padrão
    "Times New Roman": ("Times-Roman", "Times-Bold", "Times-Italic", "Times-BoldItalic"),
    "Arial": ("Helvetica", "Helvetica-Bold", "Helvetica-Oblique", "Helvetica-BoldOblique"),
}
# lacres: B22..H22, depois A23, depois B23..H23 (15 encaixes, como no formulário)
LACRE_ENDERECOS = [f"{c}22" for c in "BCDEFGH"] + ["A23"] + [f"{c}23" for c in "BCDEFGH"]


# ------------------------------------------------------------------------------------------
# dados -> endereços de célula da via esquerda
# ------------------------------------------------------------------------------------------
def _num(valor, casas=None):
    """Número no padrão brasileiro. None -> '' (campo em branco para preencher à mão)."""
    if valor is None:
        return ""
    texto = f"{valor:.{casas}f}" if casas is not None else f"{valor:g}"
    return texto.replace(".", DECIMAL)


def _milhar(valor):
    return "" if valor is None else f"{int(valor):,}".replace(",", ".")


def valores_por_celula(a: Autorizacao, data_hora: str) -> dict:
    carretas = (list(a.placas_carreta or []) + ["", ""])[:2]
    v = {
        "B12": data_hora, "B13": a.usina, "B14": a.produto, "A17": a.nota_fiscal, "C17": a.data_nf,
        "C18": a.transportador, "C20": a.placa_cavalo, "C21": carretas[0], "D21": carretas[1],
        "B25": _num(a.temp_tanque, 1), "D25": _num(a.temp_amostra, 1),
        "B27": _num(a.dens_ambiente, 4), "D27": _num(a.dens_20, 4),
        "B29": _num(a.teor_alcoolico, 2), "D29": _num(a.acidez, 2),
        "B31": _num(a.ph, 2), "D31": _num(a.condutividade),
        "B33": _num(a.fator_nf, 4),
        "A38": _milhar(a.volume_ambiente), "C38": _milhar(volume_20_exibido(a)[0]),
        "B45": a.motorista, "B47": a.cpf,
    }
    for i, endereco in enumerate(LACRE_ENDERECOS):
        v[endereco] = str(a.lacres[i]) if i < len(a.lacres or []) else ""
    return {k: ("" if x is None else str(x)) for k, x in v.items()}


def _texto_da_celula(endereco: str, cel: dict, valores: dict, data_hora: str) -> str:
    """Rótulo fixo, dado preenchido ou (via direita) espelho do dado da via esquerda."""
    bruto = cel.get("v")
    if endereco in valores:
        return valores[endereco]
    if isinstance(bruto, str) and bruto.startswith("="):
        if bruto.upper() == "=NOW()":
            return data_hora
        m = re.fullmatch(r"=\+?([A-Z]+\d+)", bruto)
        if m:
            ref = m.group(1)
            if ref in valores:
                return valores[ref]
            rotulo = LAYOUT["celulas"].get(ref, {}).get("v")   # ex.: =A45 -> "MOTORISTA:"
            return rotulo if isinstance(rotulo, str) and not rotulo.startswith("=") else ""
        return ""
    return bruto or ""


# ------------------------------------------------------------------------------------------
# desenho
# ------------------------------------------------------------------------------------------
def _letras(indice: int) -> str:
    return chr(65 + indice)                      # colunas A..R (18 colunas)


def _texto_na_posicao(lin: int, col1: int, valores: dict, data_hora: str, mesclada_de: dict) -> str:
    """Texto que aparece na célula (lin, col1 base 1), olhando a âncora se for mesclada."""
    faixa = mesclada_de.get((lin, col1))
    if faixa:
        lin, col1 = faixa[0], faixa[1]
    endereco = f"{_letras(col1 - 1)}{lin}"
    cel = LAYOUT["celulas"].get(endereco)
    return _texto_da_celula(endereco, cel, valores, data_hora).strip() if cel else ""



def _letra_para_indice(letras: str) -> int:
    n = 0
    for ch in letras:
        n = n * 26 + ord(ch) - 64
    return n - 1


def _fonte_pdf(nome: str, negrito: bool, italico: bool) -> str:
    regular, bold, ital, bolditalic = FONTES.get(nome, FONTES["Arial"])
    return bolditalic if negrito and italico else bold if negrito else ital if italico else regular


def gerar_pdf(a: Autorizacao, caminho: str, vias: int = 2) -> None:
    larg, alt = LAYOUT["larguras"], LAYOUT["alturas"]
    colunas_usadas = len(larg) if vias == 2 else 8
    pag_w, pag_h = landscape(A4)
    ml, mv = LAYOUT["pagina"]["margem_lateral"], LAYOUT["pagina"]["margem_vertical"]

    X = [0.0]
    for w in larg[:colunas_usadas]:
        X.append(X[-1] + w)
    Y = [0.0]
    for h in alt:
        Y.append(Y[-1] + h)
    esc = min((pag_w - 2 * ml) / X[-1], (pag_h - 2 * mv) / Y[-1])      # cabe na folha, sem distorcer
    x0 = (pag_w - X[-1] * esc) / 2                                      # centralizado, como no original
    y0 = pag_h - (pag_h - Y[-1] * esc) / 2

    def px(x): return x0 + x * esc
    def py(y): return y0 - y * esc

    data_hora = a.emitido_em.strftime("%d/%m/%y %H:%M")
    valores = valores_por_celula(a, data_hora)

    mesclada_de = {}                                                    # (lin, col) -> intervalo
    for r1, c1, r2, c2 in LAYOUT["mescladas"]:
        if c2 > colunas_usadas:
            continue
        for r in range(r1, r2 + 1):
            for c in range(c1, c2 + 1):
                mesclada_de[(r, c)] = (r1, c1, r2, c2)

    pdf = canvas.Canvas(caminho, pagesize=landscape(A4))
    pdf.setTitle(f"Boletim de Descarga - NF {a.nota_fiscal or ''}")
    pdf.setLineCap(2)

    # ---- 1) textos
    for endereco, cel in LAYOUT["celulas"].items():
        m = re.fullmatch(r"([A-Z]+)(\d+)", endereco)
        c, r = _letra_para_indice(m.group(1)), int(m.group(2))
        if c >= colunas_usadas:
            continue
        faixa = mesclada_de.get((r, c + 1))
        if faixa and (faixa[0], faixa[1]) != (r, c + 1):
            continue                                                    # só a célula-âncora escreve
        r1, c1, r2, c2 = faixa if faixa else (r, c + 1, r, c + 1)
        texto = _texto_da_celula(endereco, cel, valores, data_hora)
        if not texto.strip():
            continue
        xa, xb = px(X[c1 - 1]), px(X[c2])
        yt, yb = py(Y[r1 - 1]), py(Y[r2])
        nome, tam, neg, ita = cel["fonte"]
        fonte = _fonte_pdf(nome, neg, ita)
        tam = tam * esc
        folga = 2 * esc
        h_al, v_al, quebra = cel["alin"]
        numerico = endereco in valores and bool(re.fullmatch(r"[\d.,]+", texto))
        h_al = "right" if (h_al in (None, "general") and numerico) else \
            "center" if h_al in ("center", "justify", "distributed") else \
            "right" if h_al == "right" else "left"
        quebra = quebra or "\n" in texto
        if h_al == "left" and not quebra:
            # como no Excel, texto à esquerda "transborda" sobre as células vazias à direita
            prox = c2 + 1
            while prox <= colunas_usadas and not _texto_na_posicao(r1, prox, valores, data_hora, mesclada_de):
                xb = px(X[prox])
                prox += 1
        largura_util = xb - xa - 2 * folga
        palavras = [w for w in texto.replace("\n", " ").split() if w]
        while tam > 4 and ((not quebra and pdf.stringWidth(texto, fonte, tam) > largura_util) or
                           (quebra and palavras and max(pdf.stringWidth(w, fonte, tam) for w in palavras) > largura_util)):
            tam -= 0.25                                                 # reduz só o necessário p/ caber
        if quebra:
            linhas = [ln for parte in texto.split("\n") for ln in simpleSplit(parte, fonte, tam, largura_util)]
        else:
            linhas = [texto]
        pdf.setFont(fonte, tam)
        passo = tam * 1.15
        bloco = passo * len(linhas)
        if v_al == "top":
            y = yt - folga - tam * 0.85
        elif v_al in ("center", "distributed", "justify"):
            y = (yt + yb) / 2 + bloco / 2 - tam * 0.85
        else:                                                           # bottom (padrão do Excel)
            y = yb + folga + bloco - tam * 0.95
        for ln in linhas:
            if h_al == "center":
                pdf.drawCentredString((xa + xb) / 2, y, ln)
            elif h_al == "right":
                pdf.drawRightString(xb - folga, y, ln)
            else:
                pdf.drawString(xa + folga, y, ln)
            y -= passo

    # ---- 2) bordas (por cima dos textos; arestas internas de células mescladas não são desenhadas)
    for endereco, cel in LAYOUT["celulas"].items():
        if not cel["borda"]:
            continue
        m = re.fullmatch(r"([A-Z]+)(\d+)", endereco)
        c, r = _letra_para_indice(m.group(1)), int(m.group(2))
        if c >= colunas_usadas:
            continue
        faixa = mesclada_de.get((r, c + 1))
        xa, xb, yt, yb = px(X[c]), px(X[c + 1]), py(Y[r - 1]), py(Y[r])
        for lado, estilo in cel["borda"].items():
            if faixa:
                r1, c1, r2, c2 = faixa
                interna = ((lado == "l" and c + 1 > c1) or (lado == "r" and c + 1 < c2) or
                           (lado == "t" and r > r1) or (lado == "b" and r < r2))
                if interna:
                    continue
            pdf.setLineWidth(max(0.25, LARGURA_LINHA.get(estilo, 0.75) * esc))
            if lado == "l":
                pdf.line(xa, yb, xa, yt)
            elif lado == "r":
                pdf.line(xb, yb, xb, yt)
            elif lado == "t":
                pdf.line(xa, yt, xb, yt)
            else:
                pdf.line(xa, yb, xb, yb)

    # ---- 3) logotipo (uma por via, na posição do original)
    if LOGO.exists():
        for img in LAYOUT["imagens"]:
            if img["x"] >= X[-1]:
                continue
            pdf.drawImage(str(LOGO), px(img["x"]), py(img["y"] + img["h"]), width=img["w"] * esc,
                          height=img["h"] * esc, preserveAspectRatio=False, mask="auto")   # esticado como no original

    # ---- 3b) caixinhas DENTRO / FORA
    pdf.setLineWidth(max(0.25, 0.75 * esc))
    for ret in LAYOUT.get("retangulos", []):
        if ret["x"] < X[-1]:
            pdf.rect(px(ret["x"]), py(ret["y"] + ret["h"]), ret["w"] * esc, ret["h"] * esc, stroke=1, fill=0)

    # ---- 4) linha pontilhada de corte entre as duas vias
    if vias == 2:
        xm = px((X[8] + X[COL_VIA2]) / 2)
        pdf.setDash(2, 3)
        pdf.setLineWidth(0.4)
        pdf.line(xm, mv, xm, pag_h - mv)
    pdf.showPage()
    pdf.save()
