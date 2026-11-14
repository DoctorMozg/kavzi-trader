from pydantic_ai.exceptions import ModelRequestTimeout, ModelTimeoutError

# pydantic-ai wraps transport timeouts as ModelTimeoutError, which is not a
# builtin TimeoutError; asyncio.wait_for still raises the builtin one.
LLM_TIMEOUT_ERRORS = (TimeoutError, ModelTimeoutError, ModelRequestTimeout)
