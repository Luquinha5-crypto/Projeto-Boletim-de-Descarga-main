"""Desenha a Autorização de Descarga em PDF (A4 paisagem, 2 vias lado a lado).

A geometria (largura das colunas, altura das linhas) é a da planilha original,
só que escalada para caber na folha. Cada célula do formulário é uma linha da
lista CELULAS: (linha_ini, col_ini, linha_fim, col_fim, texto|campo, estilo).
Quando o texto é um campo (ex.: "{usina}"), ele é trocado pelo dado da Autorizacao.
"""
from pathlib import Path

from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.utils import simpleSplit
from reportlab.pdfgen import canvas

from calculos import MAX_LACRES, Autorizacao, fator_correcao

LOGO = Path(__file__).parent / "assets" / "logo.jpeg"

# Larguras A:H em "caracteres do Excel" (iguais nas duas vias) e alturas das linhas 1..51 em pontos.
def _pt(chars: float) -> float:
    """Largura de coluna do Excel (em caracteres) -> pontos."""
    return (chars * 7 + 5) * 0.75


LARGURAS = [_pt(w) for w in (13.41, 10.28, 12.99, 10.41, 12.99, 9.99, 12.99, 9.99)]
GAP = _pt(4.85) * 2  # colunas I:J
ALTURAS = [12.75, 12.75, 12.75, 3, 3, 15.75, 8.25, 15.75, 8.25, 15.75, 13.5, 19.5, 19.5, 19.5, 19.5,
           19.5, 19.5, 19.5, 19.5, 19.5, 19.5, 12.75, 13.5, 19.5, 16.5, 16.5, 16.5, 16.5, 16.5, 16.5,
           16.5, 16.5, 18.75, 18.75, 18.95, 19.5, 19.5, 19.5, 12.75, 12.75, 12.75, 18.0, 13.5, 12.75,
           13.5, 12.75, 12.75, 13.5, 12.75, 12.75, 13.5]
N_LINHAS = 51
LACRE_SLOTS = [(22, c) for c in range(1, 8)] + [(23, 0)] + [(23, c) for c in range(1, 8)]

LINHA = "__________:__________"
B, I, N = "bold", "italic", ""  # estilos de fonte


def _f(valor, formato: str = "{}") -> str:
    """Formata um campo; se não veio da NF (None) sai em branco para preencher à mão."""
    return "" if valor is None else formato.format(valor)


def _celulas(a: Autorizacao, data_hora: str) -> list:
    """(r1, c1, r2, c2, texto, estilo, alinhamento). Linhas 1-based, colunas 0-based (A=0 .. H=7)."""
    carretas = (a.placas_carreta + ["", ""])[:2]
    c = [
        (6, 0, 6, 7, "RAIZEN COMBUSTIVEIS S/A", B, "center", 0),
        (8, 0, 8, 7, "Autorização para Descarga de Auto Tanque no Pool de Londrina", B, "center", 0),
        # cabeçalhos
        (10, 0, 10, 3, "Preenchido pela Raizen", B, "center", 1),
        (11, 0, 11, 3, "Dados do carregamento", B, "center", 1),
        (10, 4, 10, 7, "Preenchido pelo Pool", B, "center", 1),
        (11, 4, 11, 7, "Dados do recebimento", B, "center", 1),
        # dados do carregamento (lado Raízen)
        (12, 0, 12, 0, "Data:", B, "left", 0), (12, 1, 12, 3, data_hora, B, "center", 0),
        (13, 0, 13, 0, "Usina:", B, "left", 0), (13, 1, 13, 3, a.usina or "", B, "center", 0),
        (14, 0, 15, 0, "Produto:", B, "left", 0), (14, 1, 15, 3, a.produto or "", B, "center", 0),
        (16, 0, 16, 1, "Nota fiscal (s)", B, "center", 0), (16, 2, 16, 3, "Data:", B, "center", 0),
        (17, 0, 17, 1, a.nota_fiscal or "", B, "center", 0), (17, 2, 17, 3, a.data_nf or "", B, "center", 0),
        (18, 0, 19, 1, "Transportador:", B, "left", 0), (18, 2, 19, 3, a.transportador or "", B, "center", 0),
        (20, 0, 21, 0, "Placas:", B, "left", 0),
        (20, 1, 20, 1, "Cavalo:", B, "center", 0), (20, 2, 20, 3, a.placa_cavalo or "", B, "center", 0),
        (21, 1, 21, 1, "Carreta:", B, "center", 0),
        (21, 2, 21, 2, carretas[0], B, "center", 0), (21, 3, 21, 3, carretas[1], B, "center", 0),
        (22, 0, 22, 0, "LACRES:", B, "left", 0),
        # lado Pool: campos para preencher à mão
        (12, 4, 23, 7, "", N, "center", 0),
        (13, 4, 13, 5, "Data da Descarga", B, "left", 0), (13, 6, 13, 7, LINHA, N, "center", 2),
        (15, 4, 15, 5, "Hora da Chegada:", B, "left", 0), (15, 6, 15, 7, LINHA, N, "center", 2),
        (17, 4, 17, 5, "Hora da entrada:", B, "left", 0), (17, 6, 17, 7, LINHA, N, "center", 2),
        (19, 4, 19, 5, "Hora da Saída", B, "left", 0), (19, 6, 19, 7, LINHA, N, "center", 2),
        # controle de qualidade
        (24, 0, 24, 3, "", N, "center", 0),
        (24, 4, 24, 7, "Controle de Qualidade Recebido", B, "center", 1),
    ]
    # lacres: células vazias para os 15 encaixes + valores
    for i, (r, col) in enumerate(LACRE_SLOTS):
        c.append((r, col, r, col, str(a.lacres[i]) if i < len(a.lacres) else "", B, "center", 0))
    # análises: (linha, rótulo1, valor1, rótulo2, valor2, rótulo Pool 1, rótulo Pool 2)
    analises = [
        (25, "Temperatura Tanque", _f(a.temp_tanque, "{:.1f}"), "Temperatura amostra", _f(a.temp_amostra, "{:.1f}"),
         "Temperatura amostra", "Fator de Correção"),
        (27, "Densidade Ambiente", _f(a.dens_ambiente, "{:.4f}"), "Densidade A 20", _f(a.dens_20, "{:.4f}"),
         "Densidade Ambiente", "Densidade 20"),
        (29, "Teor Alcoólico", _f(a.teor_alcoolico, "{:.2f}"), "Acidez", _f(a.acidez, "{:.2f}"),
         "Teor alcoólico", "Acidez"),
        (31, "PH", _f(a.ph, "{:.2f}"), "Condutividade", _f(a.condutividade, "{:g}"), "PH", "Condutividade"),
    ]
    for r, l1, v1, l2, v2, p1, p2 in analises:
        c += [(r, 0, r + 1, 0, l1, B, "center", 0), (r, 1, r + 1, 1, v1, B, "center", 0),
              (r, 2, r + 1, 2, l2, B, "center", 0), (r, 3, r + 1, 3, v2, B, "center", 0),
              (r, 4, r + 1, 4, p1, B, "center", 0), (r, 5, r + 1, 5, "", N, "center", 0),
              (r, 6, r + 1, 6, p2, B, "center", 0), (r, 7, r + 1, 7, "", N, "center", 0)]
    c += [
        (33, 0, 34, 0, "Fator de Correção", B, "center", 0), (33, 1, 34, 1, _f(a.fator_nf, "{:.4f}"), B, "center", 0),
        (33, 2, 34, 3, "", N, "center", 0),
        (33, 4, 33, 7, "Temperatura do Autotanque (compartimentos)", B, "center", 1),
        (34, 4, 34, 4, "", N, "center", 0), (34, 5, 34, 5, "", N, "center", 0),
        (34, 6, 34, 6, "", N, "center", 0), (34, 7, 34, 7, "", N, "center", 0),
        (35, 0, 35, 3, "", N, "center", 0),
        (35, 4, 35, 5, "", N, "center", 0), (35, 6, 35, 6, "Média", B, "right", 0), (35, 7, 35, 7, "", N, "center", 0),
        # volumes
        (36, 0, 36, 3, "Volume Manifestado", B, "center", 1),
        (37, 0, 37, 1, "Ambiente", B, "center", 0), (37, 2, 37, 3, "20º C", B, "center", 0),
        (38, 0, 38, 1, _f(a.volume_ambiente, "{:,}").replace(",", "."), B, "center", 3),
        (38, 2, 38, 3, _f(a.volume_20_nf, "{:,}").replace(",", "."), B, "center", 3),
        (36, 4, 36, 7, "Volume Recebido", B, "center", 1),
        (37, 4, 37, 4, "Ambiente", B, "center", 0), (37, 5, 37, 5, "S/F", B, "center", 0),
        (37, 6, 37, 6, "20º", B, "center", 0), (37, 7, 37, 7, "S/F", B, "center", 0),
        (38, 4, 38, 4, "", N, "center", 0), (38, 5, 38, 5, "", N, "center", 0),
        (38, 6, 38, 6, "", N, "center", 0), (38, 7, 38, 7, "", N, "center", 0),
        # rodapé
        (39, 0, 42, 0, "Emitido por:", B + I, "center", 4), (39, 1, 42, 3, "", N, "center", 0),
        (43, 0, 43, 3, "Observações =", B + I, "center", 4),
        (44, 0, 44, 3, "", N, "center", 0),
        (45, 0, 45, 0, "MOTORISTA:", B, "left", 0), (45, 1, 45, 3, a.motorista or "", B, "left", 0),
        (46, 0, 46, 3, "", N, "center", 0),
        (47, 0, 47, 0, "CPF:", B, "center", 0), (47, 1, 47, 3, a.cpf or "", B, "left", 0),
        (48, 0, 51, 3, "", N, "center", 0),
        (39, 4, 39, 7, "KIT METANOL", B, "center", 0),
        (40, 4, 40, 5, "DENTRO", B + I, "left", 5), (40, 6, 40, 7, "FORA", B + I, "right", 5),
        (41, 4, 44, 7, "Declaro que acompanhei a apuração dos volumes e estou de acôrdo com a variação "
                       "de _____________ litros a 20° C.", B + I, "center", 6),
        (45, 4, 45, 7, "Motorista", B + I, "center", 4),
        (46, 4, 47, 7, "", N, "center", 0),
        (48, 4, 48, 7, "Conferido / Analisado  por = Operador", B + I, "center", 4),
        (49, 4, 50, 7, "", N, "center", 0),
        (51, 4, 51, 7, "Liberado por = Supervisor de Operações", B + I, "center", 4),
    ]
    return c


# fator de tamanho de fonte por "tipo" (última coluna das tuplas): 0 normal, 1 cabeçalho, 2 linha, 3 destaque,
# 4 pequeno, 5 pequeno com caixinha, 6 texto corrido
TAM = {0: 8, 1: 8.5, 2: 8, 3: 9.5, 4: 6.2, 5: 7.5, 6: 7}


def gerar_pdf(a: Autorizacao, caminho: str, vias: int = 2) -> None:
    pag_w, pag_h = landscape(A4)
    margem = 14
    larg_forma = sum(LARGURAS)
    larg_total = larg_forma * vias + GAP * (vias - 1)
    sx = (pag_w - 2 * margem) / larg_total
    sy = (pag_h - 2 * margem) / sum(ALTURAS[:N_LINHAS])
    esc = min(sx, sy)

    xs = [0.0]
    for w in LARGURAS:
        xs.append(xs[-1] + w * esc)
    ys = [0.0]
    for h in ALTURAS[:N_LINHAS]:
        ys.append(ys[-1] + h * esc)
    largura_via = xs[-1]
    gap = GAP * esc
    x_inicio = (pag_w - (largura_via * vias + gap * (vias - 1))) / 2
    y_topo = pag_h - margem - 2

    c = canvas.Canvas(caminho, pagesize=landscape(A4))
    c.setTitle(f"Autorização de Descarga - NF {a.nota_fiscal}")
    data_hora = a.emitido_em.strftime("%d/%m/%y %H:%M")
    celulas = _celulas(a, data_hora)

    for v in range(vias):
        x0 = x_inicio + v * (largura_via + gap)
        for r1, c1, r2, c2, texto, estilo, alin, tipo in celulas:
            x, xf = x0 + xs[c1], x0 + xs[c2 + 1]
            yt, yb = y_topo - ys[r1 - 1], y_topo - ys[r2]
            c.setLineWidth(0.6)
            if not (r1 in (6, 8) and c1 == 0 and c2 == 7):  # títulos ficam sem moldura
                c.rect(x, yb, xf - x, yt - yb, stroke=1, fill=0)
            if not texto:
                continue
            fonte = "Helvetica" + ("-BoldOblique" if estilo == B + I else "-Bold" if estilo == B
                                   else "-Oblique" if estilo == I else "")
            tam = max(5.5, TAM[tipo] * esc / 0.78)
            # reduz a fonte se uma palavra sozinha não couber na largura da célula
            while tam > 5 and max(c.stringWidth(w, fonte, tam) for w in texto.split()) > xf - x - 4:
                tam -= 0.3
            c.setFont(fonte, tam)
            linhas = simpleSplit(texto, fonte, tam, xf - x - 4)
            alt_linha = tam * 1.15
            total = alt_linha * len(linhas)
            y = (yt + yb) / 2 + total / 2 - tam * 0.85
            for ln in linhas:
                if alin == "center":
                    c.drawCentredString((x + xf) / 2, y, ln)
                elif alin == "right":
                    c.drawRightString(xf - 3, y, ln)
                else:
                    c.drawString(x + 3, y, ln)
                y -= alt_linha
        # caixinhas DENTRO/FORA
        bx = 7.5 * esc / 0.78
        yc = y_topo - (ys[39] + ys[40]) / 2 - bx / 2
        c.rect(x0 + xs[4] + 38 * esc / 0.78, yc, bx * 1.8, bx, stroke=1, fill=0)
        c.rect(x0 + xs[8] - 38 * esc / 0.78 - bx * 1.8, yc, bx * 1.8, bx, stroke=1, fill=0)
        # logotipo centralizado no topo
        if LOGO.exists():
            lw = 88 * esc
            lh = lw * 112 / 248
            c.drawImage(str(LOGO), x0 + (largura_via - lw) / 2, y_topo - ys[5] + (ys[5] - lh) / 2 + 6 * esc,
                        width=lw, height=lh, preserveAspectRatio=True, mask="auto")
    # linha divisória pontilhada entre as vias (para recorte)
    if vias == 2:
        xm = x_inicio + largura_via + gap / 2
        c.setDash(2, 3)
        c.setLineWidth(0.4)
        c.line(xm, margem, xm, pag_h - margem)
    c.showPage()
    c.save()
