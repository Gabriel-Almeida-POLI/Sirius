"""Minimal ASGI application placeholder for the Sirius web UI."""
from __future__ import annotations

import json
from typing import Any, Dict


HTML_RESPONSE = """
<!DOCTYPE html>
<html lang=\"pt-BR\">
<head>
    <meta charset=\"utf-8\" />
    <title>Sirius UI</title>
    <style>
        body { font-family: sans-serif; margin: 2rem; }
        main { max-width: 640px; margin: auto; text-align: center; }
        .dropzone {
            border: 2px dashed #3b82f6;
            border-radius: 12px;
            padding: 3rem;
            color: #1f2937;
            background: #f8fafc;
        }
    </style>
</head>
<body>
    <main>
        <h1>Sirius</h1>
        <p>Interface web de demonstração. Arraste e solte um PDF consolidado.</p>
        <div class=\"dropzone\">Drag and drop não está implementado neste protótipo.</div>
    </main>
</body>
</html>
""".strip()


async def app(scope: Dict[str, Any], receive, send) -> None:  # type: ignore[override]
    if scope["type"] != "http":
        raise RuntimeError("A aplicação ASGI suporta apenas eventos HTTP.")

    if scope["method"] != "GET":
        await send(
            {
                "type": "http.response.start",
                "status": 405,
                "headers": [(b"content-type", b"application/json; charset=utf-8")],
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": json.dumps({"detail": "Método não permitido."}).encode("utf-8"),
            }
        )
        return

    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [(b"content-type", b"text/html; charset=utf-8")],
        }
    )
    await send({"type": "http.response.body", "body": HTML_RESPONSE.encode("utf-8")})
