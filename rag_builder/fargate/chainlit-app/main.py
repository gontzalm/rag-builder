import chainlit as cl
from chainlit.types import ThreadDict
from langchain_core.messages import AIMessage, HumanMessage

from app.actions import ACTIONS
from app.agent import setup_agent
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

    in_thinking_step = False

    async for content, metadata in agent.astream(  # pyright: ignore[reportUnknownMemberType, reportOptionalMemberAccess, reportUnknownVariableType]
        {"messages": [HumanMessage(message.content)]},
        config={"configurable": {"thread_id": message.thread_id}},
        stream_mode="messages",
    ):
        try:
            token = content.content_blocks[0]["text"]  # pyright: ignore[reportUnknownVariableType, reportUnknownMemberType]
        except (IndexError, KeyError):
            continue

        match metadata["langgraph_node"]:  # pyright: ignore[reportMatchNotExhaustive]
            case "tools":
                async with cl.Step(name="retrieve_context", type="tool") as step:
                    step.output = f"{token[:500]}\n...\n Output truncated"

            case "model":
                if token == "<thinking":
                    # Entered thinking step
                    in_thinking_step = True
                    about_to_end_thinking = False

                    async with cl.Step(name="thinking", type="llm") as thinking_step:
                        continue

                if not in_thinking_step:
                    await answer.stream_token(token)  # pyright: ignore[reportUnknownArgumentType]
                    continue

                match token.rstrip("\n"):  # pyright: ignore[reportUnknownMemberType]
                    case " </" | "thinking":
                        about_to_end_thinking = True
                        continue

                    case ">":
                        if about_to_end_thinking:  # pyright: ignore[reportPossiblyUnboundVariable]
                            in_thinking_step = False
                        continue

                    case thinking_token:  # pyright: ignore[reportUnknownVariableType]
                        _ = await thinking_step.stream_token(thinking_token)  # pyright: ignore[reportPossiblyUnboundVariable, reportUnknownArgumentType]

    _ = await answer.send()


@cl.on_chat_resume  # pyright: ignore[reportUnknownMemberType]
async def resume(thread: ThreadDict):
    messages = [
        HumanMessage(step["output"])  # pyright: ignore[reportTypedDictNotRequiredAccess]
        if step["type"] == "user_message"  # pyright: ignore[reportTypedDictNotRequiredAccess]
        else AIMessage(step["output"])  # pyright: ignore[reportTypedDictNotRequiredAccess]
        for step in thread["steps"]
        if step["type"] in ("user_message", "assistant_message")  # pyright: ignore[reportTypedDictNotRequiredAccess]
    ]
    setup_agent({"messages": messages, "thread_id": thread["id"]})
