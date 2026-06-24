from typing import Any

from langchain.agents import create_agent
import pydash
import os

from dotenv import load_dotenv

from agentrun.integration.langchain import model, sandbox_toolset, AgentRunConverter
from agentrun.sandbox import TemplateType
from agentrun.server import AgentRequest, AgentRunServer
from agentrun.utils.log import logger

load_dotenv()
# 请替换为您已经创建的 模型 和 沙箱 名称
MODEL_NAME = os.getenv("MODEL_NAME")
MODEL_SERVICE_NAME = os.getenv("MODEL_SERVICE_NAME")
SANDBOX_NAME = os.getenv("SANDBOX_NAME")

if not MODEL_SERVICE_NAME:
    raise ValueError("请将 MODEL_SERVICE_NAME 替换为您已经创建的模型名称")

code_interpreter_tools = []
if SANDBOX_NAME and not SANDBOX_NAME.startswith("<"):
    code_interpreter_tools = sandbox_toolset(
        template_name=SANDBOX_NAME,
        template_type=TemplateType.CODE_INTERPRETER,
        sandbox_idle_timeout_seconds=300,
    )
else:
    logger.warning("SANDBOX_NAME 未设置或未替换，跳过加载沙箱工具。")

agent = create_agent(
    model=model(MODEL_SERVICE_NAME, model=MODEL_NAME),
    tools=[*code_interpreter_tools],
    system_prompt="你是一个 AgentRun 的 AI 专家，可以通过沙箱运行代码来回答用户的问题。",
)


def invoke_agent(request: AgentRequest):
    input: Any = {"messages": [{"content": message.content, "role": message.role} for message in request.messages]}
    converter = AgentRunConverter()

    try:
        if request.stream:

            async def stream_generator():
                result = agent.astream_events(input)
                async for chunk in result:
                    print(chunk)
                    for item in converter.convert(chunk):
                        yield item

            return stream_generator()
        else:
            result = agent.invoke(input)
            return pydash.get(result, "messages.-1.content")
    except Exception as e:
        import traceback

        traceback.print_exc()
        logger.error("调用出错: %s", e)
        raise e


AgentRunServer(invoke_agent=invoke_agent).start()
"""
curl 127.0.0.1:9000/openai/v1/chat/completions -XPOST \
    -H "content-type: application/json" \
    -d '{
        "messages": [{"role": "user", "content": "写一段代码,查询现在是几点?"}], 
        "stream":true
    }'

curl 127.0.0.1:9000/ag-ui/agent -XPOST \
    -H "content-type: application/json" \
    -d '{
        "messages": [{"role": "user", "content": "写一段代码,查询现在是几点?"}]
    }'
"""
