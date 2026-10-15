"""Testes do leitor de NF-e com XMLs FICTÍCIOS (tests/fixtures/). Rodam em qualquer máquina e podem ir ao GitHub.

Rode na pasta do projeto:   python -m unittest discover -s tests -v
Os fixtures imitam o formato de 3 usinas reais (biodiesel, hidratado, anidro) com dados inventados.
Um teste FALHA de propósito (placas do hidratado): ele aponta um bug real do leitor.
"""
import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).parent.parent
sys.path.insert(0, str(RAIZ))
from gerar import processar  # noqa: E402
from leitor_nfe import ler_nfe  # noqa: E402

FIX = Path(__file__).parent / "fixtures"


def ler(nome):
    return ler_nfe(str(FIX / f"ficticia_{nome}.xml"))


class LeitorNFe(unittest.TestCase):
    def test_fixtures_existem(self):  # evita o "passou sem rodar nada"
        self.assertEqual(len(list(FIX.glob("*.xml"))), 3)

    def test_campos_fixos(self):
        casos = [("biodiesel", "100001", "10/10/2026", "USINA BIO EXEMPLO S.A.", 50000),
                 ("hidratado", "100002", "13/10/2026", "USINA ALCOOL EXEMPLO S.A.", 40000),
                 ("anidro", "100003", "13/10/2026", "USINA ANIDRO EXEMPLO S.A.", 49900)]
        for nome, nf, data, usina, vol in casos:
            with self.subTest(nome):
                a, _ = ler(nome)
                self.assertEqual((a.nota_fiscal, a.data_nf, a.usina, a.volume_20_nf), (nf, data, usina, vol))

    def test_anidro_texto_livre(self):
        a, _ = ler("anidro")
        self.assertEqual((a.temp_tanque, a.fator_nf, a.teor_alcoolico), (21.9, 0.998, 99.6))
        self.assertEqual((a.volume_ambiente, a.volume_20_nf), (50000, 49900))
        self.assertEqual(a.lacres, ["0001001", "0001002", "0001003", "0001004"])
        self.assertEqual((a.placa_cavalo, a.placas_carreta), ("ABC1D23", ["ABC4E56"]))

    def test_lacre_de_amostra_nunca_entra(self):
        self.assertNotIn("200001", ler("biodiesel")[0].lacres)
        self.assertNotIn("E0009999", ler("hidratado")[0].lacres)
        self.assertNotIn("3000001", ler("anidro")[0].lacres)

    def test_campo_ausente_vira_aviso_e_nao_valor_chutado(self):
        a, avisos = ler("hidratado")     # esta NF não traz temperatura nem densidade
        self.assertIsNone(a.temp_tanque)
        self.assertTrue(any("temp_tanque" in v for v in avisos))

    def test_placas_do_hidratado(self):
        """BUG REAL: o texto traz 'CPF12345678909 CNH1234567890'. Veja o que o leitor devolve."""
        a, _ = ler("hidratado")
        self.assertEqual(a.placa_cavalo, "ABC1D23")
        self.assertEqual(a.placas_carreta, ["ABC4E56"])


class DoXmlAoPdf(unittest.TestCase):
    def test_gera_pdf_para_cada_xml(self):
        with tempfile.TemporaryDirectory() as tmp:
            for xml in sorted(FIX.glob("*.xml")):
                with self.subTest(xml.name):
                    processar(xml, Path(tmp), None)
            pdfs = list(Path(tmp).glob("*.pdf"))
            self.assertEqual(len(pdfs), 3)
            self.assertTrue(all(p.stat().st_size > 5000 for p in pdfs))


if __name__ == "__main__":
    unittest.main()
