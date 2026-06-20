import logging

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from app.agents.analyst_agent import AnalystAgent
from app.agents.chart_agent import ChartAgent
from app.agents.data_agent import DataAgent
from app.agents.rag_agent import RagAgent

logger = logging.getLogger("Tools")

class AgentQuestionInput(BaseModel):
    question: str = Field(..., description="The query to process")

@tool("data_tool", args_schema=AgentQuestionInput)
def data_tool(question: str) -> str:
    """Fetches raw data from the ClickHouse database using SQL based on the natural language question. Returns data as JSON string."""
    logger.info(f"[DataTool] Processing: {question}")
    agent = DataAgent()
    res = agent.run(question)
    if not res.success:
        return f"Error: {res.error}"
    # Return full data as JSON so the agent can see it or pass it
    import json
    return json.dumps(res.data, default=str, ensure_ascii=False)

@tool("chart_tool", args_schema=AgentQuestionInput)
def chart_tool(question: str) -> str:
    """Generates a chart specification based on a specific question and the available data. Requires data to be fetched first."""
    logger.info(f"[ChartTool] Processing: {question}")
    data_agent = DataAgent()
    data_res = data_agent.run(question)
    if not data_res.success:
        return f"Error: {data_res.error}"
        
    chart_agent = ChartAgent()
    chart_res = chart_agent.run(question, data=data_res.data)
    
    if not chart_res.success:
        return f"Error: {chart_res.error}"
        
    import json
    result = {
        "chart_type": chart_res.chart.type,
        "title": chart_res.chart.title,
        "data": data_res.data
    }
    return json.dumps(result, default=str, ensure_ascii=False)

@tool("analyst_tool", args_schema=AgentQuestionInput)
def analyst_tool(question: str) -> str:
    """Generates textual insights and narrative based on the data. Use this after fetching data to provide human-readable analysis."""
    logger.info(f"[AnalystTool] Processing: {question}")
    agent = AnalystAgent()
    res = agent.run(question, depends_on_results={})
    if not res.success:
        return f"Error: {res.error}"
    return res.insights

@tool("rag_tool", args_schema=AgentQuestionInput)
def rag_tool(question: str) -> str:
    """Searches the regulatory knowledge base (tax code, laws) using semantic search in Qdrant."""
    logger.info(f"[RagTool] Processing: {question}")
    agent = RagAgent()
    res = agent.run(question)
    if not res.success:
        return f"Error: {res.error}"
    return res.context

def get_all_tools():
    return [data_tool, chart_tool, analyst_tool, rag_tool]
