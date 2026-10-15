# Boletim de Descarga

Gera uma **Autorização para Descarga de Auto Tanque** em PDF a partir de arquivos XML de NF-e. O programa lê os dados disponíveis na nota, confere alguns valores e deixa em branco no formulário o que não foi informado — não inventa dados.

O PDF é gerado em A4 paisagem, com duas vias lado a lado. O processamento é local; os arquivos não são enviados para serviços externos.

## Requisitos

- Python 3.10 ou superior
- Dependência: [ReportLab](https://pypi.org/project/reportlab/)

Instale a dependência:

```bash
python -m pip install reportlab
```

## Como usar

Execute os comandos na pasta do projeto:

```bash
# Gerar um PDF para uma NF-e
python gerar.py caminho/para/nota.xml

# Informar dados que não estão na NF-e
python gerar.py caminho/para/nota.xml --extra extra.json

# Processar todos os arquivos XML de uma pasta
python gerar.py caminho/para/xmls/

# Definir a pasta de saída (o padrão é saida/)
python gerar.py caminho/para/nota.xml -o outra_pasta
```

Os PDFs são salvos com o nome `boletim_NF<numero>.pdf`. Se não for possível obter o número da nota, o nome do arquivo XML é usado.

Para cada NF-e, o programa mostra os valores encontrados, o resultado das conferências e os campos que ficaram em branco. Se houver uma divergência, confira a nota antes de imprimir.

## Dados complementares

Use `--extra` para fornecer, em um arquivo JSON, os dados que não constam na NF-e. Esses valores **substituem** os correspondentes lidos da nota. Exemplo:

```json
{
  "temp_amostra": 20,
  "acidez": 8.6,
  "ph": 7,
  "condutividade": 237,
  "motorista": "MOTORISTA EXEMPLO",
  "cpf": "000.000.000-00"
}
```

Campos aceitos:

`usina`, `produto`, `nota_fiscal`, `data_nf`, `transportador`, `placa_cavalo`, `placas_carreta`, `lacres`, `temp_tanque`, `temp_amostra`, `dens_ambiente`, `dens_20`, `teor_alcoolico`, `acidez`, `ph`, `condutividade`, `fator_nf`, `volume_ambiente`, `volume_20_nf`, `motorista` e `cpf`.

Use números JSON para valores numéricos e listas JSON para `placas_carreta` e `lacres`. O programa informa erro se o arquivo contiver nomes de campos desconhecidos.

## Conferências e limitações

- As informações são extraídas de tags fixas da NF-e e de padrões conhecidos no texto complementar (`infCpl`). O texto varia entre emissores; campos não reconhecidos ficam em branco.
- Para produtos alcoólicos, o fator de correção é estimado por uma fórmula linear aproximada. O volume a 20 °C é conferido usando o fator informado na própria NF-e.
- As conferências são auxiliares e não substituem a validação operacional da documentação e dos valores.
- O logotipo é opcional. Se `assets/logo.jpeg` estiver disponível, ele será incluído no PDF.

## Testes

Os testes usam XMLs fictícios incluídos em `tests/fixtures/`:

```bash
python -m unittest discover -s tests -v
```

## Estrutura do projeto

```text
.
├── calculos.py             # Regras e conferências
├── gerar.py                # Linha de comando e processamento dos XMLs
├── gerar_pdf.py            # Geração do formulário em PDF
├── leitor_nfe.py           # Leitura dos dados da NF-e
├── extra_exemplo.json      # Exemplo de dados complementares
└── tests/
    ├── fixtures/           # NF-e fictícias para os testes
    └── test_leitor_nfe.py
```
