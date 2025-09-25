# Sirius PDF Extractor

Interface web local para arrastar PDFs de demonstrações financeiras, extrair tabelas e baixar os resultados já limpos.

## Requisitos

1. Python 3.10+.
2. Ambiente virtual recomendado (`python -m venv .venv && source .venv/bin/activate`).
3. Dependências: `pip install -r requirements.txt`.

> Opcional: para habilitar o motor Camelot no painel de "Opções avançadas", instale `camelot-py[cv]` (requer dependências do sistema como Ghostscript).

## Como iniciar

```bash
./iniciar.sh
```

O script executa o servidor FastAPI com Uvicorn em `http://127.0.0.1:8000`.

Se preferir, rode manualmente:

```bash
uvicorn webapp:app --host 0.0.0.0 --port 8000
```

## Como usar

1. Abra `http://127.0.0.1:8000` no navegador.
2. Arraste um ou mais PDFs para a área central ou clique para selecionar arquivos.
3. Acompanhe o progresso individual de cada PDF; cartões exibem seções detectadas, páginas e previews das primeiras linhas.
4. Use os botões de download para obter um ZIP com todas as tabelas ou CSV/Parquet por seção.
5. O painel de "Opções avançadas" permite escolher motor, unir tabelas multi-página, normalizar schema, formato e relatório JSON.

Todos os arquivos são processados em memória ou em diretórios temporários controlados pela aplicação — nenhum caminho fixo é utilizado.
