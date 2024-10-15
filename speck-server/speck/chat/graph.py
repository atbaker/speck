from typing import Annotated, Literal
from typing_extensions import TypedDict

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, RemoveMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition

from emails.tools import ListThreadsTool, SearchThreadsTool, GetThreadTool
from config import settings


class State(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    summary: str

list_threads_tool = ListThreadsTool()
search_threads_tool = SearchThreadsTool()
get_thread_tool = GetThreadTool()
tools = [list_threads_tool, search_threads_tool, get_thread_tool]

provider_settings = settings.cloud_inference_providers['cerebras']
llm = ChatOpenAI(
    base_url=provider_settings['endpoint'],
    openai_api_key=provider_settings['api_key'],
    model=provider_settings['model'],
    temperature=0,
)
llm_with_tools = llm.bind_tools(tools)

def chatbot(state: State):
    return {"messages": [llm_with_tools.invoke(state["messages"])]}

def should_continue(state: State):
    """In respones to a new user message, check if we need to invoke tools. If not, check if we need to summarize the conversation."""
    messages = state["messages"]
    last_message = messages[-1]

    # If there's a function call in the last message, we need to invoke tools
    if isinstance(last_message, AIMessage) and last_message.tool_calls:
        return 'tools'

    # Otherwise, check if we need to summarize the conversation
    if len(messages) > 4:
        return 'summarize'
    else:
        return END

def invoke_llm_with_summary(state: State):
    # If a summary exists, add it as a system message
    summary = state.get("summary", "")
    if summary:
        summary_message = f'Summary of conversation so far: {summary}'
        messages = [SystemMessage(content=summary_message)] + state["messages"]
    else:
        messages = state["messages"]

    # Always prepend a system message before invoking the LLM
    messages = [
        SystemMessage("You are Speck, an AI assistant that can help answer questions related to a user's Gmail mailbox. You have tools available to list threads, search threads, get the details of a thread."),
        *messages,
    ]

    response = llm_with_tools.invoke(messages)
    return {"messages": [response]}

def summarize_conversation(state: State):
    """Summarize the conversation."""
    summary = state.get('summary', '')
    if summary:
        # If a summary already exists, we use a different system prompt
        # to summarize it than if one didn't
        summary_message = (
            f"This is summary of the conversation to date: {summary}\n\n"
            "Update the summary by taking into account the new messages above:"
        )
    else:
        summary_message = 'Create a summary of the conversation so far.'

    messages = state['messages'] + [HumanMessage(content=summary_message)]
    response = llm.invoke(messages)

    # Now, delete all but the last two messages
    delete_messages = [RemoveMessage(id=message.id) for message in state['messages'][:-2]]
    return {"messages": delete_messages, "summary": response.content}

def get_graph_builder():
    """Initialize the graph builder."""
    graph_builder = StateGraph(State)

    graph_builder.add_node("conversation", invoke_llm_with_summary)
    graph_builder.set_entry_point("conversation")

    graph_builder.add_node('summarize', summarize_conversation)

    tool_node = ToolNode(tools=tools)
    graph_builder.add_node("tools", tool_node)

    graph_builder.add_conditional_edges(
        "conversation",
        should_continue,
    )
    graph_builder.add_edge("tools", "conversation")

    return graph_builder
