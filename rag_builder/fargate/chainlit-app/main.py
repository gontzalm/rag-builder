import chainlit as cl
from chainlit.types import ThreadDict
from langchain_core.messages import AIMessage, HumanMessage

from app.actions import ACTIONS
from app.agent import MAX_MEMORY_WINDOW, setup_agent
from app.auth import setup_oauth
from app.data_persistence import setup_data_persistence

setup_oauth()
setup_data_persistence()


@cl.on_chat_start  # pyright: ignore[reportUnknownMemberType]
async def start():
    setup_agent()

    user = cl.user_session.get("user")  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]

    _ = await cl.Message(
        f"Hello, {user.identifier}! Ask me anything regarding the existing knowledge base. You can also perform the following actions:",  # pyright: ignore[reportUnknownMemberType, reportOptionalMemberAccess]
        actions=ACTIONS,
    ).send()


@cl.on_message  # pyright: ignore[reportUnknownMemberType]
async def main(message: cl.Message):
    answer = cl.Message("")

    agent = cl.user_session.get("agent")  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]

    async for token, metadata in agent.astream(  # pyright: ignore[reportUnknownMemberType, reportOptionalMemberAccess, reportUnknownVariableType]
        {"messages": [HumanMessage(message.content)]},
        config={"configurable": {"thread_id": message.thread_id}},
        stream_mode="messages",
    ):
        if not token.content_blocks:  # pyright: ignore[reportUnknownMemberType]
            continue

        match metadata["langgraph_node"]:
            case "tools":
                with cl.Step(name="retrieve_context", type="tool") as step:
                    step.output = f"{token.content_blocks[0]['text'][:500]}\n...\n Output truncated"  # pyright: ignore[reportUnknownMemberType]
            case "model":
                content_block = token.content_blocks[0]  # pyright: ignore[reportUnknownVariableType, reportUnknownMemberType]
                if content_block["type"] == "text":
                    await answer.stream_token(content_block["text"])  # pyright: ignore[reportUnknownArgumentType]

            case _:  # pyright: ignore[reportUnknownVariableType]
                pass

    _ = await answer.send()


@cl.on_chat_resume  # pyright: ignore[reportUnknownMemberType]
async def resume(thread: ThreadDict):
    messages = [
        HumanMessage(step["output"])  # pyright: ignore[reportTypedDictNotRequiredAccess]
        if step["type"] == "user_message"  # pyright: ignore[reportTypedDictNotRequiredAccess]
        else AIMessage(step["output"])  # pyright: ignore[reportTypedDictNotRequiredAccess]
        for step in thread["steps"]
        if step["type"] in ("user_message", "assistant_message")  # pyright: ignore[reportTypedDictNotRequiredAccess]
    ][-MAX_MEMORY_WINDOW:]

    # The first message must be a HumanMessage in order to avoid a Bedrock validation exception
    if not isinstance(messages[0], HumanMessage):
        _ = messages.pop(0)

    setup_agent({"messages": messages, "thread_id": thread["id"]})
