"""Minimal ASGI application for the Sirius web UI with PDF upload support."""
from __future__ import annotations

import json
from typing import Any, Dict

from sections import find_consolidated_spans_from_bytes


HTML_RESPONSE = """
<!DOCTYPE html>
<html lang=\"pt-BR\">
<head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
    <title>Sirius UI</title>
    <style>
        :root {
            color-scheme: light dark;
            --bg-gradient: radial-gradient(circle at top left, #e0f2fe, #f5f3ff 45%, #f8fafc 70%);
            --panel-color: rgba(255, 255, 255, 0.88);
            --border-color: rgba(148, 163, 184, 0.4);
            --shadow-elevated: 0 30px 60px rgba(15, 23, 42, 0.16);
            --accent: #2563eb;
            --accent-strong: #1d4ed8;
            --text-primary: #0f172a;
            --text-muted: #475569;
            --success: #16a34a;
            --error: #dc2626;
        }
        * {
            box-sizing: border-box;
        }
        body {
            min-height: 100vh;
            margin: 0;
            padding: clamp(1.5rem, 5vw, 3rem);
            font-family: 'Inter', system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: var(--bg-gradient);
            color: var(--text-primary);
            display: flex;
            align-items: center;
            justify-content: center;
        }
        main {
            width: min(960px, 100%);
            background: var(--panel-color);
            border: 1px solid var(--border-color);
            border-radius: 28px;
            padding: clamp(2rem, 6vw, 3.5rem);
            box-shadow: var(--shadow-elevated);
            backdrop-filter: blur(18px);
        }
        header {
            display: flex;
            flex-direction: column;
            gap: 0.75rem;
            margin-bottom: 2.5rem;
        }
        h1 {
            margin: 0;
            font-size: clamp(2.5rem, 6vw, 3.5rem);
            letter-spacing: -0.04em;
        }
        p.description {
            margin: 0;
            font-size: 1.05rem;
            color: var(--text-muted);
            max-width: 52ch;
            line-height: 1.6;
        }
        .card-grid {
            display: grid;
            gap: 1.75rem;
        }
        .drop-card {
            border-radius: 24px;
            padding: clamp(2.5rem, 4vw, 3rem);
            background: linear-gradient(140deg, rgba(37, 99, 235, 0.16), rgba(59, 130, 246, 0.05));
            border: 1px dashed rgba(37, 99, 235, 0.45);
            position: relative;
            overflow: hidden;
            transition: transform 160ms ease, box-shadow 160ms ease, border-color 160ms ease;
            cursor: pointer;
        }
        .drop-card::after {
            content: '';
            position: absolute;
            inset: -40%;
            background: radial-gradient(circle at top, rgba(96, 165, 250, 0.4), rgba(255, 255, 255, 0));
            opacity: 0;
            transition: opacity 200ms ease;
        }
        .dropzone {
            display: grid;
            justify-items: center;
            gap: 1.25rem;
            position: relative;
            z-index: 1;
        }
        .drop-card.dragover {
            transform: translateY(-6px) scale(1.01);
            border-color: rgba(29, 78, 216, 0.9);
            box-shadow: 0 24px 50px rgba(37, 99, 235, 0.22);
        }
        .drop-card.dragover::after {
            opacity: 1;
        }
        .dropzone strong {
            font-size: 1.3rem;
            letter-spacing: -0.01em;
        }
        .dropzone span {
            color: var(--text-muted);
            font-size: 0.95rem;
        }
        .dropzone span code {
            font-family: 'JetBrains Mono', 'Fira Code', monospace;
            padding: 0.1rem 0.35rem;
            border-radius: 0.5rem;
            background: rgba(148, 163, 184, 0.14);
        }
        #status {
            display: flex;
            align-items: center;
            gap: 0.75rem;
            font-weight: 600;
            margin-top: 1.5rem;
            min-height: 2.5rem;
            padding: 0.65rem 1rem;
            border-radius: 16px;
            background: rgba(148, 163, 184, 0.12);
            transition: background 180ms ease, color 180ms ease, box-shadow 180ms ease;
        }
        #status[data-state="success"] {
            background: rgba(22, 163, 74, 0.12);
            box-shadow: 0 12px 24px rgba(22, 163, 74, 0.22);
        }
        #status[data-state="error"] {
            background: rgba(220, 38, 38, 0.12);
            box-shadow: 0 12px 24px rgba(220, 38, 38, 0.2);
        }
        #status[data-state="loading"] {
            background: rgba(37, 99, 235, 0.12);
            box-shadow: 0 12px 24px rgba(37, 99, 235, 0.2);
        }
        #status-icon {
            width: 1.5rem;
            height: 1.5rem;
            display: inline-flex;
            align-items: center;
            justify-content: center;
        }
        #status-text {
            margin: 0;
        }
        .spinner {
            width: 1.25rem;
            height: 1.25rem;
            border-radius: 999px;
            border: 2px solid transparent;
            border-top-color: currentColor;
            animation: spin 900ms linear infinite;
        }
        @keyframes spin {
            to { transform: rotate(360deg); }
        }
        #results {
            border-radius: 22px;
            border: 1px solid rgba(148, 163, 184, 0.35);
            background: rgba(15, 23, 42, 0.03);
            backdrop-filter: blur(14px);
            padding: 1.5rem;
            box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.3);
        }
        #results h2 {
            margin-top: 0;
            margin-bottom: 1rem;
            font-size: 1.2rem;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            overflow: hidden;
            border-radius: 16px;
            box-shadow: 0 15px 35px rgba(15, 23, 42, 0.08);
        }
        th, td {
            padding: 0.75rem 1rem;
            text-align: left;
        }
        thead th {
            background: linear-gradient(120deg, rgba(37, 99, 235, 0.12), rgba(59, 130, 246, 0.08));
            font-weight: 700;
            letter-spacing: 0.02em;
        }
        tbody tr:nth-child(even) td {
            background: rgba(148, 163, 184, 0.12);
        }
        .empty-state {
            margin: 0;
            font-size: 1rem;
            color: var(--text-muted);
            text-align: center;
        }
        .hidden {
            display: none !important;
        }
        footer {
            margin-top: 2rem;
            font-size: 0.85rem;
            color: rgba(15, 23, 42, 0.56);
            display: flex;
            justify-content: space-between;
            flex-wrap: wrap;
            gap: 0.75rem;
        }
        footer a {
            color: var(--accent-strong);
            text-decoration: none;
            font-weight: 600;
        }
        footer a:hover {
            text-decoration: underline;
        }
        @media (max-width: 720px) {
            body {
                padding: 1.25rem;
            }
            main {
                padding: 2rem;
            }
            .dropzone strong {
                text-align: center;
            }
        }
        @media (prefers-color-scheme: dark) {
            :root {
                --bg-gradient: radial-gradient(circle at top left, #0f172a, #111827 40%, #020617 80%);
                --panel-color: rgba(15, 23, 42, 0.85);
                --border-color: rgba(51, 65, 85, 0.7);
                --shadow-elevated: 0 28px 60px rgba(2, 6, 23, 0.72);
                --text-primary: #f8fafc;
                --text-muted: rgba(226, 232, 240, 0.72);
            }
            .drop-card {
                background: linear-gradient(140deg, rgba(37, 99, 235, 0.3), rgba(59, 130, 246, 0.1));
                border: 1px dashed rgba(191, 219, 254, 0.45);
            }
            .drop-card.dragover {
                box-shadow: 0 20px 44px rgba(37, 99, 235, 0.45);
            }
            #results {
                background: rgba(30, 41, 59, 0.7);
                box-shadow: inset 0 1px 0 rgba(148, 163, 184, 0.2);
            }
            tbody tr:nth-child(even) td {
                background: rgba(148, 163, 184, 0.18);
            }
            footer {
                color: rgba(226, 232, 240, 0.7);
            }
        }
    </style>
</head>
<body>
    <main>
        <header>
            <h1>Interface Sirius</h1>
            <p class=\"description\">Uma experiência refinada para detectar seções consolidadas em arquivos PDF. Arraste e solte o documento, ou clique na área elegante abaixo para fazer o upload manualmente.</p>
        </header>
        <div class=\"card-grid\">
            <div id=\"drop-card\" class=\"drop-card\">
                <div id=\"dropzone\" class=\"dropzone\">
                    <svg width=\"64\" height=\"64\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.5\" stroke-linecap=\"round\" stroke-linejoin=\"round\" aria-hidden=\"true\">
                        <path d=\"M12 21h6a2 2 0 0 0 2-2v-6\" />
                        <path d=\"M16 16l-4-4-4 4\" />
                        <path d=\"M12 12V3\" />
                        <path d=\"M8 8H5a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h3\" />
                    </svg>
                    <strong>Solte seu PDF consolidado aqui</strong>
                    <span>ou selecione manualmente um arquivo <code>.pdf</code> para analisarmos instantaneamente.</span>
                    <input id=\"file-input\" type=\"file\" accept=\"application/pdf\" class=\"hidden\" />
                </div>
            </div>
            <div id=\"status\">
                <span id=\"status-icon\" aria-hidden=\"true\"></span>
                <p id=\"status-text\"></p>
            </div>
            <section id=\"results\" class=\"hidden\">
                <h2>Resultado da análise</h2>
                <div id=\"results-content\"></div>
            </section>
        </div>
        <footer>
            <span>Pronto para transformar seus documentos.</span>
            <a href=\"#dropzone\">Enviar outro PDF</a>
        </footer>
    </main>
    <script>
        const dropCard = document.getElementById('drop-card');
        const dropzone = document.getElementById('dropzone');
        const fileInput = document.getElementById('file-input');
        const statusEl = document.getElementById('status');
        const statusIcon = document.getElementById('status-icon');
        const statusText = document.getElementById('status-text');
        const resultsEl = document.getElementById('results');
        const resultsContent = document.getElementById('results-content');

        const statusIcons = {
            idle: '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 12h.01"></path><circle cx="12" cy="12" r="9"></circle></svg>',
            loading: '<span class="spinner" aria-hidden="true"></span>',
            success: '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="m5 13 4 4L19 7"></path></svg>',
            error: '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"></circle><path d="m15 9-6 6"></path><path d="m9 9 6 6"></path></svg>'
        };

        const setStatus = (message, state = 'idle') => {
            statusEl.dataset.state = state;
            statusIcon.innerHTML = statusIcons[state] || '';
            statusText.textContent = message;
            if (state === 'error') {
                statusEl.style.color = 'var(--error)';
            } else if (state === 'success') {
                statusEl.style.color = 'var(--success)';
            } else if (state === 'loading') {
                statusEl.style.color = 'var(--accent-strong)';
            } else {
                statusEl.style.color = 'var(--text-muted)';
            }
        };

        const resetResults = () => {
            resultsContent.innerHTML = '';
            resultsEl.classList.add('hidden');
        };

        const renderResults = (spans) => {
            const entries = Object.entries(spans);
            if (entries.length === 0) {
                resultsContent.innerHTML = '<p class="empty-state">Nenhuma seção consolidada foi detectada para este documento.</p>';
            } else {
                const rows = entries.map(([key, value], index) => {
                    const start = value.start_page ?? '?';
                    const end = value.end_page ?? start;
                    return `<tr><td>${index + 1}</td><td>${key}</td><td>${start}</td><td>${end}</td></tr>`;
                }).join('');
                resultsContent.innerHTML = `
                    <table>
                        <thead><tr><th>#</th><th>Seção</th><th>Página inicial</th><th>Página final</th></tr></thead>
                        <tbody>${rows}</tbody>
                    </table>
                `;
            }
            resultsEl.classList.remove('hidden');
        };

        const uploadFile = async (file) => {
            resetResults();
            if (!file) {
                setStatus('Nenhum arquivo selecionado.', 'error');
                return;
            }
            if (file.type && file.type !== 'application/pdf') {
                setStatus('Por favor selecione um arquivo PDF.', 'error');
                return;
            }
            setStatus(`Enviando ${file.name}...`, 'loading');
            try {
                const response = await fetch('/api/analyze', {
                    method: 'POST',
                    headers: {
                        'content-type': file.type || 'application/pdf'
                    },
                    body: file
                });

                if (!response.ok) {
                    const errorPayload = await response.json().catch(() => ({}));
                    const detail = errorPayload.detail || 'Não foi possível processar o PDF.';
                    throw new Error(detail);
                }

                const payload = await response.json();
                setStatus('Processamento concluído com sucesso.', 'success');
                renderResults(payload.spans || {});
            } catch (error) {
                console.error(error);
                setStatus(error.message || 'Erro desconhecido.', 'error');
            }
        };

        const handleFiles = (files) => {
            if (!files || files.length === 0) {
                setStatus('Nenhum arquivo selecionado.', 'error');
                return;
            }
            uploadFile(files[0]);
            fileInput.value = '';
        };

        dropzone.addEventListener('click', () => fileInput.click());
        dropzone.addEventListener('dragenter', (event) => {
            event.preventDefault();
            dropCard.classList.add('dragover');
        });
        dropzone.addEventListener('dragover', (event) => {
            event.preventDefault();
        });
        dropzone.addEventListener('dragleave', (event) => {
            if (event.target === dropzone || !dropzone.contains(event.relatedTarget)) {
                dropCard.classList.remove('dragover');
            }
        });
        dropzone.addEventListener('drop', (event) => {
            event.preventDefault();
            dropCard.classList.remove('dragover');
            const files = event.dataTransfer?.files;
            if (files && files.length > 0) {
                handleFiles(files);
            }
        });
        fileInput.addEventListener('change', (event) => {
            handleFiles(event.target.files);
        });

        setStatus('Pronto para receber seu PDF.', 'idle');
    </script>
</body>
</html>
""".strip()


async def _read_body(receive) -> bytes:
    body = bytearray()
    while True:
        message = await receive()
        body.extend(message.get("body", b""))
        if not message.get("more_body", False):
            break
    return bytes(body)


async def _send_json(send, status: int, payload: Dict[str, Any]) -> None:
    body = json.dumps(payload).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [(b"content-type", b"application/json; charset=utf-8")],
        }
    )
    await send({"type": "http.response.body", "body": body})


async def _send_html(send, html: str) -> None:
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [(b"content-type", b"text/html; charset=utf-8")],
        }
    )
    await send({"type": "http.response.body", "body": html.encode("utf-8")})


async def app(scope: Dict[str, Any], receive, send) -> None:  # type: ignore[override]
    if scope["type"] != "http":
        raise RuntimeError("A aplicação ASGI suporta apenas eventos HTTP.")

    method = scope["method"].upper()
    path = scope.get("path", "/")

    if method == "GET" and path == "/":
        await _send_html(send, HTML_RESPONSE)
        return

    if method == "POST" and path == "/api/analyze":
        pdf_bytes = await _read_body(receive)
        if not pdf_bytes:
            await _send_json(send, 400, {"detail": "O corpo da requisição está vazio."})
            return
        try:
            spans = find_consolidated_spans_from_bytes(pdf_bytes)
        except Exception as exc:  # pragma: no cover - defensive programming
            await _send_json(send, 500, {"detail": "Erro ao analisar o PDF.", "error": str(exc)})
            return

        await _send_json(send, 200, {"spans": spans})
        return

    if method == "OPTIONS":
        await send(
            {
                "type": "http.response.start",
                "status": 204,
                "headers": [(b"allow", b"GET, POST, OPTIONS")],
            }
        )
        await send({"type": "http.response.body", "body": b""})
        return

    await _send_json(send, 404, {"detail": "Rota não encontrada."})
