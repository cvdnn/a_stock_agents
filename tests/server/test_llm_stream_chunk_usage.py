from server.llm.base import LLMStreamChunk


def test_usage_accepts_openai_nested_token_details() -> None:
    usage = {
        "completion_tokens": 46,
        "prompt_tokens": 65,
        "total_tokens": 111,
        "completion_tokens_details": {
            "reasoning_tokens": 21,
            "text_tokens": 25,
        },
        "prompt_tokens_details": {
            "cached_tokens": 0,
            "text_tokens": 65,
        },
    }

    chunk = LLMStreamChunk(usage=usage)

    assert chunk.usage == usage
    assert chunk.usage["total_tokens"] == 111
