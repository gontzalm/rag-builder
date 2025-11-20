import os

import chainlit as cl
import httpx
import pandas as pd

_BACKEND_API_URL = os.environ["BACKEND_API_URL"]

ACTIONS = [
    cl.Action("load_document", {}, label="📄 Load new document"),
    cl.Action("show_load_history", {}, label="⏳ Show load history"),
    cl.Action("show_knowledge_base", {}, label="📚 Show knowledge base"),
    cl.Action("delete_document", {}, label="🗑️ Delete document in knowledge base"),
]
FOLLOWUP_MESSAGE = (
    "Ask me anything regarding the knowledge base, or perform another action:"
)


@cl.action_callback("load_document")  # pyright: ignore[reportUntypedFunctionDecorator, reportUnknownMemberType]
async def on_load_document(action: cl.Action) -> None:
    """Loads a new document with the given user input spec."""
    r = await cl.AskActionMessage(
        "Which is the document source?",
        actions=[
            cl.Action("select_source", payload={"source": "pdf"}, label="📕 PDF"),
            cl.Action("select_source", payload={"source": "web"}, label="🌐 Website"),
        ],
    ).send()

    if r is None:
        _ = await cl.Message("TIMEOUT: Please provide a document source").send()
        _ = await cl.Message(FOLLOWUP_MESSAGE, actions=ACTIONS).send()
        # see https://github.com/Chainlit/chainlit/issues/2209
        await cl.context.emitter.task_end()
        return

    source = r["payload"]["source"]  # pyright: ignore[reportUnknownVariableType]

    r = await cl.AskUserMessage("Which is the document URL?").send()

    if r is None:
        _ = await cl.Message("TIMEOUT: Please provide a document URL").send()
        _ = await cl.Message(FOLLOWUP_MESSAGE, actions=ACTIONS).send()
        await cl.context.emitter.task_end()
        return

    url = r["output"]  # pyright: ignore[reportTypedDictNotRequiredAccess]

    msg = cl.Message(f"Starting document load for URL '{url}'")
    _ = await msg.send()

    user_token = cl.user_session.get("user").metadata["access_token"]  # pyright: ignore[reportUnknownMemberType, reportOptionalMemberAccess, reportUnknownVariableType]

    async with httpx.AsyncClient(
        base_url=_BACKEND_API_URL,
        headers={"Authorization": f"Bearer {user_token}"},
    ) as http:
        r = await http.post("/documents/load", json={"source": source, "url": url})  # pyright: ignore[reportUnknownArgumentType]

    try:
        _ = r.raise_for_status()
    except httpx.HTTPStatusError:
        msg.content = "❌ An error ocurred, please try again"
    else:
        msg.content = f"📤 Successfully started document load for URL '{url}'"

    _ = await msg.update()
    _ = await cl.Message(FOLLOWUP_MESSAGE, actions=ACTIONS).send()
    await cl.context.emitter.task_end()


@cl.action_callback("show_load_history")  # pyright: ignore[reportUnknownMemberType, reportUntypedFunctionDecorator]
async def on_get_load_history(action: cl.Action) -> None:
    """Shows the load history."""
    msg = cl.Message("Fetching load history...")
    _ = await msg.send()

    user_token = cl.user_session.get("user").metadata["access_token"]  # pyright: ignore[reportUnknownMemberType, reportOptionalMemberAccess, reportUnknownVariableType]

    load_history = []

    async with httpx.AsyncClient(
        base_url=_BACKEND_API_URL,
        headers={"Authorization": f"Bearer {user_token}"},
    ) as http:
        r = await http.get("/documents/load_history")
        _ = r.raise_for_status()

        payload = r.json()  # pyright: ignore[reportAny]
        load_history.extend(payload["load_history"])  # pyright: ignore[reportUnknownMemberType, reportAny]

        while payload["next_token"] is not None:
            r = await http.get(
                "/documents/load_history", params={"next_token": payload["next_token"]}
            )
            _ = r.raise_for_status()

            payload = r.json()  # pyright: ignore[reportAny]
            load_history.extend(payload["load_history"])  # pyright: ignore[reportUnknownMemberType, reportAny]

    df = pd.DataFrame.from_records(load_history)  # pyright: ignore[reportUnknownMemberType]
    msg.content = "⏳ Load History"
    msg.elements = [cl.Dataframe(data=df)]  # pyright: ignore[reportAttributeAccessIssue]

    _ = await msg.update()
    _ = await cl.Message(FOLLOWUP_MESSAGE, actions=ACTIONS).send()


@cl.action_callback("show_knowledge_base")  # pyright: ignore[reportUnknownMemberType, reportUntypedFunctionDecorator]
async def on_get_knowledge_base(action: cl.Action) -> None:
    """Shows the documents in the knowledge base."""
    msg = cl.Message("Fetching documents in knowledge base...")
    _ = await msg.send()

    user_token = cl.user_session.get("user").metadata["access_token"]  # pyright: ignore[reportUnknownMemberType, reportOptionalMemberAccess, reportUnknownVariableType]

    documents = []

    async with httpx.AsyncClient(
        base_url=_BACKEND_API_URL,
        headers={"Authorization": f"Bearer {user_token}"},
    ) as http:
        r = await http.get("/documents")
        _ = r.raise_for_status()

        payload = r.json()  # pyright: ignore[reportAny]
        documents.extend(payload["documents"])  # pyright: ignore[reportUnknownMemberType, reportAny]

        while payload["next_token"] is not None:
            r = await http.get(
                "/documents", params={"next_token": payload["next_token"]}
            )
            _ = r.raise_for_status()

            payload = r.json()  # pyright: ignore[reportAny]
            documents.extend(payload["documents"])  # pyright: ignore[reportUnknownMemberType, reportAny]

    df = pd.DataFrame.from_records(documents)  # pyright: ignore[reportUnknownMemberType]
    msg.content = "📚 Knowledge Base"
    msg.elements = [cl.Dataframe(data=df)]  # pyright: ignore[reportAttributeAccessIssue]

    _ = await msg.update()
    _ = await cl.Message(FOLLOWUP_MESSAGE, actions=ACTIONS).send()


@cl.action_callback("delete_document")  # pyright: ignore[reportUnknownMemberType, reportUntypedFunctionDecorator]
async def on_delete_document(action: cl.Action) -> None:
    """Deletes a document from the knowledge base."""
    r = await cl.AskUserMessage("Which is the ID of the document?").send()

    if r is None:
        _ = await cl.Message("TIMEOUT: Please provide a document ID").send()
        _ = await cl.Message(FOLLOWUP_MESSAGE, actions=ACTIONS).send()
        await cl.context.emitter.task_end()
        return

    document_id = r["output"]  # pyright: ignore[reportTypedDictNotRequiredAccess]

    msg = cl.Message(f"Deleting document with ID '{document_id}'")
    _ = await msg.send()

    user_token = cl.user_session.get("user").metadata["access_token"]  # pyright: ignore[reportUnknownMemberType, reportOptionalMemberAccess, reportUnknownVariableType]

    async with httpx.AsyncClient(
        base_url=_BACKEND_API_URL,
        headers={"Authorization": f"Bearer {user_token}"},
    ) as http:
        r = await http.delete(f"/documents/{document_id}")

    try:
        _ = r.raise_for_status()
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            msg.content = f"🤷‍♂️ Document with ID '{document_id}' was not found"
        else:
            msg.content = f"❌ An error ocurred (status code: {e.response.status_code}), please try again"
    else:
        msg.content = f"🗑️ Successfully deleted document with ID '{document_id}'"

    _ = await msg.update()
    _ = await cl.Message(FOLLOWUP_MESSAGE, actions=ACTIONS).send()
    await cl.context.emitter.task_end()
