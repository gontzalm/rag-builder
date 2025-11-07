from pathlib import Path
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.utils.auth import get_current_user_token
from app.utils.env import BACKEND_API_URL

templates = Jinja2Templates(Path(__file__).parent.parent / "templates")
router = APIRouter(prefix="/frontend", tags=["frontend"])


@router.get("")
async def get_home_page(
    request: Request,
    _: str = Depends(get_current_user_token),  # pyright: ignore[reportCallInDefaultInitializer]
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "index.html",
        context={"user": request.session["email"]},
    )


@router.get("/logged-out")
async def get_logged_out_page(request: Request) -> HTMLResponse:
    """Page to show after logging out."""
    return templates.TemplateResponse(request, "logged_out.html", context={})


@router.get("/knowledge-base/available-documents")
async def get_available_documents(
    request: Request,
    _: str = Depends(get_current_user_token),  # pyright: ignore[reportCallInDefaultInitializer]
) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "knowledge_base/available_documents.html"
    )


@router.get("/knowledge-base/available-documents/data")
async def get_available_documents_data(
    request: Request,
    token: str = Depends(get_current_user_token),  # pyright: ignore[reportCallInDefaultInitializer]
) -> HTMLResponse:
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{BACKEND_API_URL}/document",
            headers={"Authorization": f"Bearer {token}"},
        )
        _ = r.raise_for_status()
        documents = r.json()["documents"]  # pyright: ignore[reportAny]
    return templates.TemplateResponse(
        request,
        "knowledge_base/available_documents_table.html",
        context={"documents": documents},
    )


@router.delete("/knowledge-base/available-documents/{document_id}")
async def delete_document(
    document_id: str,
    request: Request,
    token: str = Depends(get_current_user_token),  # pyright: ignore[reportCallInDefaultInitializer]
) -> HTMLResponse:
    async with httpx.AsyncClient() as client:
        r = await client.delete(
            f"{BACKEND_API_URL}/document/{document_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        _ = r.raise_for_status()

    return await get_available_documents(request, token)


@router.get("/knowledge-base/query")
async def get_query(
    request: Request,
    _: str = Depends(get_current_user_token),  # pyright: ignore[reportCallInDefaultInitializer]
) -> HTMLResponse:
    return templates.TemplateResponse(request, "knowledge_base/query.html")


@router.get("/knowledge-base/query/search")
async def search_query(
    query: str,
    request: Request,
    token: str = Depends(get_current_user_token),  # pyright: ignore[reportCallInDefaultInitializer]
) -> HTMLResponse:
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.get(
            f"{BACKEND_API_URL}/query",
            params={"query": query},
            headers={"Authorization": f"Bearer {token}"},
        )
        _ = r.raise_for_status()
        agent_response = r.json()["agent_response"]  # pyright: ignore[reportAny]

    return templates.TemplateResponse(
        request,
        "knowledge_base/query_response.html",
        context={"agent_response": agent_response},
    )


@router.get("/load-document/new-document")
async def get_new_document(
    request: Request,
    _: str = Depends(get_current_user_token),  # pyright: ignore[reportCallInDefaultInitializer]
) -> HTMLResponse:
    return templates.TemplateResponse(request, "load_document/new_document.html")


@router.post("/load-document/new-document")
async def post_new_document(
    request: Request,
    source: Annotated[str, Form()],
    url: Annotated[str, Form()],
    token: str = Depends(get_current_user_token),  # pyright: ignore[reportCallInDefaultInitializer]
) -> HTMLResponse:
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{BACKEND_API_URL}/document/load",
            json={"source": source, "url": url},
            headers={"Authorization": f"Bearer {token}"},
        )
        _ = r.raise_for_status()

    return templates.TemplateResponse(
        request, "load_document/new_document_success.html"
    )


@router.get("/load-document/load-history")
async def get_load_history(
    request: Request,
    _: str = Depends(get_current_user_token),  # pyright: ignore[reportCallInDefaultInitializer]
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "load_document/load_history.html",
    )


@router.get("/load-document/load-history/data")
async def get_load_history_data(
    request: Request,
    token: str = Depends(get_current_user_token),  # pyright: ignore[reportCallInDefaultInitializer]
) -> HTMLResponse:
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{BACKEND_API_URL}/document/load_history",
            headers={"Authorization": f"Bearer {token}"},
        )
        _ = r.raise_for_status()
        load_history = r.json()["load_history"]  # pyright: ignore[reportAny]
        load_history.sort(key=lambda x: x["started_at"] or "", reverse=True)  # pyright: ignore[reportAny, reportUnknownLambdaType]

    return templates.TemplateResponse(
        request,
        "load_document/load_history_table.html",
        context={"load_history": load_history},
    )
