from typing import Annotated, Literal
from typing_extensions import TypedDict

from langchain_community.tools.tavily_search import TavilySearchResults
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, RemoveMessage, SystemMessage, trim_messages
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition

from emails.tools import CustomCalculatorTool, RecentEmailsTool


class State(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    summary: str

graph_builder = StateGraph(State)

search_tool = TavilySearchResults(max_results=5)
calculator_tool = CustomCalculatorTool()
recent_emails_tool = RecentEmailsTool()
tools = [search_tool, calculator_tool, recent_emails_tool]
# llm = ChatOpenAI(
#     base_url='https://api.cerebras.ai/v1',
#     openai_api_key=os.environ['CEREBRAS_API_KEY'],
#     model='llama3.1-70b',
#     temperature=0,
# )
import os
llm = ChatOpenAI(
    base_url='https://api.fireworks.ai/inference/v1',
    openai_api_key=os.environ['FIREWORKS_API_KEY'],
    model='accounts/fireworks/models/llama-v3p1-70b-instruct',
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
    # TODO: Check this based on token count / message length instead
    # If there are more than 5 messages, summarize the conversation
    if len(messages) > 5:
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

memory = MemorySaver() # TODO: Change to SQLite checkpointer
graph = graph_builder.compile(checkpointer=memory)

config = {"configurable": {"thread_id": "1"}} # TODO: Track thread_id in the frontend

def process_user_message(user_message: str):
    response = graph.invoke({"messages": [("user", user_message)]}, config)
    import pdb; pdb.set_trace()
