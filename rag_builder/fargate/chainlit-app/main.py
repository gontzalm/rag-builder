import chainlit as cl
from langchain_core.messages import HumanMessage

from app.actions import ACTIONS
from app.agent import rag_agent  # pyright: ignore[reportUnknownVariableType]
from app.auth import setup_oauth

setup_oauth()


@cl.on_chat_start  # pyright: ignore[reportUnknownMemberType]
async def start():
    user = cl.user_session.get("user")  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]

    _ = await cl.Message(
        f"Hello, {user.identifier}! Ask me anything regarding the existing knowledge base. You can also perform the following actions:",  # pyright: ignore[reportUnknownMemberType, reportOptionalMemberAccess]
        actions=ACTIONS,
    ).send()


@cl.on_message  # pyright: ignore[reportUnknownMemberType]
async def main(message: cl.Message):
    answer = cl.Message("")

    async for token, metadata in rag_agent.astream(  # pyright: ignore[reportUnknownMemberType]
        {"messages": [HumanMessage(message.content)]},
        stream_mode="messages",
    ):
        if not token.content_blocks:  # pyright: ignore[reportUnknownMemberType, reportAttributeAccessIssue]
            continue

        match metadata["langgraph_node"]:  # pyright: ignore[reportArgumentType]
            case "tools":
                with cl.Step(name="retrieve_context", type="tool") as step:
                    step.output = f"{token.content_blocks[0]['text'][:500]}\n...\n Output truncated"  # pyright: ignore[reportUnknownMemberType, reportAttributeAccessIssue]
            case "model":
                content_block = token.content_blocks[0]  # pyright: ignore[reportUnknownVariableType, reportUnknownMemberType, reportAttributeAccessIssue]
                if content_block["type"] == "text":
                    await answer.stream_token(content_block["text"])  # pyright: ignore[reportUnknownArgumentType]

            case _:
                pass

    _ = await answer.send()
