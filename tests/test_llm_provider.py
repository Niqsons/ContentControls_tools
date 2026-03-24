"""Тесты LLM провайдера (без реальных вызовов LLM)"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from llm_provider import (
    parse_llm_json,
    get_provider,
    OllamaProvider,
    OpenRouterProvider,
)


class TestParseLlmJson:
    """Тесты парсинга и валидации ответа LLM"""

    def test_valid_response(self):
        response = '[{"id": 0, "entity": "lender", "field_name": "name", "field_type": "text"}]'
        result = parse_llm_json(response)
        assert result is not None
        assert len(result) == 1
        assert result[0]['entity'] == 'lender'

    def test_response_with_markdown(self):
        response = '```json\n[{"id": 0, "entity": "lender", "field_name": "name", "field_type": "text"}]\n```'
        result = parse_llm_json(response)
        assert result is not None
        assert len(result) == 1

    def test_response_with_think_tags(self):
        """qwen3 оборачивает ответ в <think> теги"""
        response = '<think>some reasoning</think>[{"id": 0, "entity": "loan", "field_name": "amount", "field_type": "amount"}]'
        result = parse_llm_json(response)
        assert result is not None
        assert result[0]['field_type'] == 'amount'

    def test_empty_response(self):
        assert parse_llm_json('') is None
        assert parse_llm_json(None) is None

    def test_garbage_response(self):
        assert parse_llm_json('это не JSON вообще') is None

    def test_missing_required_field_id(self):
        response = '[{"entity": "lender", "field_name": "name", "field_type": "text"}]'
        result = parse_llm_json(response)
        # Элемент без id отфильтровывается
        assert result is None

    def test_partial_fields_filled_with_defaults(self):
        response = '[{"id": 0, "entity": "lender"}]'
        result = parse_llm_json(response)
        assert result is not None
        assert result[0]['field_name'] == ''
        assert result[0]['field_type'] == 'text'

    def test_multiple_items(self):
        response = """[
            {"id": 0, "entity": "lender", "field_name": "name", "field_type": "name"},
            {"id": 1, "entity": "borrower", "field_name": "name", "field_type": "name"},
            {"id": 2, "entity": "loan", "field_name": "amount", "field_type": "amount"}
        ]"""
        result = parse_llm_json(response)
        assert result is not None
        assert len(result) == 3

    def test_non_array_response(self):
        response = '{"id": 0, "entity": "lender"}'
        assert parse_llm_json(response) is None


class TestGetProvider:
    def test_default_is_ollama(self, monkeypatch):
        monkeypatch.delenv('DRAFTBUILDER_LLM_PROVIDER', raising=False)
        provider = get_provider()
        assert isinstance(provider, OllamaProvider)

    def test_openrouter_from_env(self, monkeypatch):
        monkeypatch.setenv('DRAFTBUILDER_LLM_PROVIDER', 'openrouter')
        provider = get_provider()
        assert isinstance(provider, OpenRouterProvider)

    def test_ollama_custom_model(self, monkeypatch):
        monkeypatch.delenv('DRAFTBUILDER_LLM_PROVIDER', raising=False)
        monkeypatch.setenv('DRAFTBUILDER_LLM_MODEL', 'qwen2.5:7b')
        provider = get_provider()
        assert isinstance(provider, OllamaProvider)
        assert provider.model == 'qwen2.5:7b'

    def test_provider_info(self, monkeypatch):
        monkeypatch.delenv('DRAFTBUILDER_LLM_PROVIDER', raising=False)
        provider = get_provider()
        info = provider.info()
        assert 'Ollama' in info
