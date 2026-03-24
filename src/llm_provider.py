#!/usr/bin/env python3
"""
LLM Provider Abstraction for Draft Builder

Поддерживаемые провайдеры:
- ollama (по умолчанию)
- openrouter (OpenAI-совместимый API)

Настройка через переменные окружения:
  DRAFTBUILDER_LLM_PROVIDER  — ollama | openrouter (default: ollama)
  DRAFTBUILDER_LLM_MODEL     — имя модели (default: qwen3:32b)
  DRAFTBUILDER_LLM_URL       — URL API (default: зависит от провайдера)
  DRAFTBUILDER_LLM_API_KEY   — API ключ (для openrouter)
"""

import os
import re
import json
from abc import ABC, abstractmethod
from typing import Optional, List

import requests

# JSON Schema для валидации ответа LLM
LLM_RESPONSE_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "required": ["id", "entity", "field_name", "field_type"],
        "properties": {
            "id": {"type": "integer"},
            "entity": {"type": "string"},
            "field_name": {"type": "string"},
            "field_type": {"type": "string"},
        },
    },
}


class LLMProvider(ABC):
    """Абстрактный LLM провайдер"""

    @abstractmethod
    def generate(self, prompt: str, system: str = None) -> str:
        """Отправить промпт, получить текстовый ответ"""
        ...

    def info(self) -> str:
        """Описание провайдера для логов"""
        return self.__class__.__name__


class OllamaProvider(LLMProvider):
    """Ollama (локальная LLM)"""

    def __init__(self, url: str = None, model: str = None):
        self.url = url or os.environ.get(
            'DRAFTBUILDER_LLM_URL',
            'http://localhost:11434/api/generate'
        )
        self.model = model or os.environ.get(
            'DRAFTBUILDER_LLM_MODEL',
            'qwen3:32b'
        )

    def generate(self, prompt: str, system: str = None) -> str:
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.1,
                "num_predict": 2000,
            },
        }
        if system:
            payload["system"] = system

        try:
            resp = requests.post(self.url, json=payload, timeout=120)
            resp.raise_for_status()
            text = resp.json().get('response', '')
            # Убрать маркеры think из qwen3
            text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
            return text.strip()
        except requests.exceptions.ConnectionError:
            print(f"[ERROR] Cannot connect to Ollama at {self.url}")
            print("        Make sure Ollama is running: ollama serve")
            return ''
        except Exception as e:
            print(f"[WARN] Ollama call failed: {e}")
            return ''

    def info(self) -> str:
        return f"Ollama ({self.model} at {self.url})"


class OpenRouterProvider(LLMProvider):
    """OpenRouter (OpenAI-совместимый API)"""

    def __init__(self, api_key: str = None, model: str = None, url: str = None):
        self.api_key = api_key or os.environ.get('DRAFTBUILDER_LLM_API_KEY', '')
        self.model = model or os.environ.get(
            'DRAFTBUILDER_LLM_MODEL',
            'qwen/qwen3-32b'
        )
        self.url = url or os.environ.get(
            'DRAFTBUILDER_LLM_URL',
            'https://openrouter.ai/api/v1/chat/completions'
        )

    def generate(self, prompt: str, system: str = None) -> str:
        if not self.api_key:
            print("[ERROR] DRAFTBUILDER_LLM_API_KEY not set")
            return ''

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.1,
            "max_tokens": 2000,
        }

        try:
            resp = requests.post(self.url, json=payload, headers=headers, timeout=120)
            resp.raise_for_status()
            data = resp.json()
            return data['choices'][0]['message']['content'].strip()
        except Exception as e:
            print(f"[WARN] OpenRouter call failed: {e}")
            return ''

    def info(self) -> str:
        return f"OpenRouter ({self.model})"


def get_provider() -> LLMProvider:
    """Получить LLM провайдер на основе env vars"""
    provider_name = os.environ.get('DRAFTBUILDER_LLM_PROVIDER', 'ollama').lower()

    if provider_name == 'openrouter':
        return OpenRouterProvider()
    else:
        return OllamaProvider()


def parse_llm_json(response: str) -> Optional[List[dict]]:
    """Извлечь и валидировать JSON массив из ответа LLM.

    Returns None если ответ невалидный.
    """
    if not response:
        return None

    # Извлечь JSON массив
    json_match = re.search(r'\[[\s\S]*?\]', response)
    if not json_match:
        return None

    try:
        data = json.loads(json_match.group())
    except json.JSONDecodeError:
        return None

    # Валидация структуры
    if not isinstance(data, list):
        return None

    validated = []
    for item in data:
        if not isinstance(item, dict):
            continue
        if 'id' not in item:
            continue
        # Привести к нужной структуре, заполнить отсутствующие поля
        validated.append({
            'id': item['id'],
            'entity': item.get('entity', ''),
            'field_name': item.get('field_name', ''),
            'field_type': item.get('field_type', 'text'),
        })

    return validated if validated else None
