import pytest

from core.llm import GroqLLM, LLMError


def test_missing_model_access_returns_actionable_error_without_retry():
    class ModelNotFound(Exception):
        status_code = 404

    class Completions:
        calls = 0

        def create(self, **kwargs):
            self.calls += 1
            raise ModelNotFound("The model llama-3.3-70b-versatile does not exist or you do not have access to it.")

    class Client:
        def __init__(self):
            self.chat = type("Chat", (), {"completions": Completions()})()

    llm = GroqLLM(api_key="test-key", model="llama-3.3-70b-versatile")
    client = Client()
    llm._client = client

    with pytest.raises(LLMError, match="openai/gpt-oss-120b"):
        llm.json("system", "user")

    assert client.chat.completions.calls == 1
