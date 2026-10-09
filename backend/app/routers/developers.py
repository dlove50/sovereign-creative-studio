"""Developer API reference: every endpoint of the local API, read from the app's own OpenAPI description."""
from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter(prefix="/api/developers", tags=["developers"])

_METHODS = ("get", "post", "put", "patch", "delete")


@router.get("/endpoints")
def endpoints(request: Request):
    spec = request.app.openapi()
    items = []
    for path, operations in spec.get("paths", {}).items():
        if path.startswith("/api/developers"):
            continue
        for method in _METHODS:
            operation = operations.get(method)
            if not operation:
                continue
            body = (operation.get("requestBody") or {}).get("content", {})
            items.append({
                "method": method.upper(), "path": path, "group": (operation.get("tags") or ["other"])[0],
                "summary": operation.get("summary") or "", "description": (operation.get("description") or "").strip().split("\n")[0][:300],
                "path_params": [p["name"] for p in operation.get("parameters", []) if p.get("in") == "path"],
                "query_params": [p["name"] for p in operation.get("parameters", []) if p.get("in") == "query"],
                "body": "multipart" if "multipart/form-data" in body else "json" if "application/json" in body else None,
            })
    items.sort(key=lambda i: (i["group"], i["path"], i["method"]))
    return {"count": len(items), "interactive_docs": "/docs", "openapi": "/openapi.json", "endpoints": items}
