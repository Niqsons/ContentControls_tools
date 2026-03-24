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
  DRAFTBUILDER_LLM_TIMEOUT   — timeout запроса в секундах (default: 300)
"""

import os
import re
import json
import logging
from abc import ABC, abstractmethod
from typing import Optional, List

import requests

logger = logging.getLogger('draftbuilder.llm')

DEFAULT_TIMEOUT = None  # без ограничения — локальные LLM на слабом железе могут генерировать долго


def _parse_timeout():
    """Прочитать timeout из env. None = без ограничения."""
    val = os.environ.get('DRAFTBUILDER_LLM_TIMEOUT')
    if val is None:
        return DEFAULT_TIMEOUT
    try:
        return int(val)
    except ValueError:
        return DEFAULT_TIMEOUT


def _fmt_timeout(timeout):
    return f"{timeout}s" if timeout else "unlimited"


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

    def __init__(self, url: str = None, model: str = None, timeout: int = None):
        self.url = url or os.environ.get(
            'DRAFTBUILDER_LLM_URL',
            'http://localhost:11434/api/generate'
        )
        self.model = model or os.environ.get(
            'DRAFTBUILDER_LLM_MODEL',
            'qwen3:32b'
        )
        self.timeout = timeout if timeout is not None else _parse_timeout()

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

        logger.debug("Ollama request: model=%s, timeout=%s, prompt_len=%d",
                      self.model, _fmt_timeout(self.timeout), len(prompt))

        try:
            resp = requests.post(self.url, json=payload, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
            text = data.get('response', '')

            # Метрики из ответа Ollama
            eval_duration = data.get('eval_duration', 0)
            total_duration = data.get('total_duration', 0)
            eval_count = data.get('eval_count', 0)
            if total_duration:
                total_sec = total_duration / 1e9
                tokens_per_sec = eval_count / (eval_duration / 1e9) if eval_duration else 0
                logger.info("Ollama response: %.1fs, %d tokens, %.1f tok/s",
                            total_sec, eval_count, tokens_per_sec)

            # Убрать маркеры think из qwen3
            text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
            result = text.strip()
            logger.debug("Ollama output (%d chars): %s", len(result), result[:200])
            return result

        except requests.exceptions.ConnectionError:
            logger.error("Cannot connect to Ollama at %s. Make sure Ollama is running: ollama serve",
                         self.url)
            return ''
        except requests.exceptions.ReadTimeout:
            logger.error("Ollama timeout after %s. Model %s may need more time. "
                         "Increase DRAFTBUILDER_LLM_TIMEOUT or remove it for unlimited",
                         _fmt_timeout(self.timeout), self.model)
            return ''
        except requests.exceptions.HTTPError as e:
            logger.error("Ollama HTTP error: %s", e)
            if hasattr(e, 'response') and e.response is not None:
                logger.error("Response body: %s", e.response.text[:500])
            return ''
        except Exception as e:
            logger.error("Ollama call failed: %s: %s", type(e).__name__, e)
            return ''

    def info(self) -> str:
        return f"Ollama ({self.model} at {self.url}, timeout={_fmt_timeout(self.timeout)})"


class OpenRouterProvider(LLMProvider):
    """OpenRouter (OpenAI-совместимый API)"""

    def __init__(self, api_key: str = None, model: str = None,
                 url: str = None, timeout: int = None):
        self.api_key = api_key or os.environ.get('DRAFTBUILDER_LLM_API_KEY', '')
        self.model = model or os.environ.get(
            'DRAFTBUILDER_LLM_MODEL',
            'qwen/qwen3-32b'
        )
        self.url = url or os.environ.get(
            'DRAFTBUILDER_LLM_URL',
            'https://openrouter.ai/api/v1/chat/completions'
        )
        self.timeout = timeout if timeout is not None else _parse_timeout()

    def generate(self, prompt: str, system: str = None) -> str:
        if not self.api_key:
            logger.error("DRAFTBUILDER_LLM_API_KEY not set")
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

        logger.debug("OpenRouter request: model=%s, timeout=%s", self.model, _fmt_timeout(self.timeout))

        try:
            resp = requests.post(self.url, json=payload, headers=headers, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
            result = data['choices'][0]['message']['content'].strip()

            usage = data.get('usage', {})
            if usage:
                logger.info("OpenRouter response: %d prompt + %d completion tokens",
                            usage.get('prompt_tokens', 0), usage.get('completion_tokens', 0))

            logger.debug("OpenRouter output (%d chars): %s", len(result), result[:200])
            return result
        except requests.exceptions.ReadTimeout:
            logger.error("OpenRouter timeout after %s. Set DRAFTBUILDER_LLM_TIMEOUT to increase",
                         _fmt_timeout(self.timeout))
            return ''
        except requests.exceptions.HTTPError as e:
            logger.error("OpenRouter HTTP error: %s", e)
            if hasattr(e, 'response') and e.response is not None:
                logger.error("Response body: %s", e.response.text[:500])
            return ''
        except Exception as e:
            logger.error("OpenRouter call failed: %s: %s", type(e).__name__, e)
            return ''

    def info(self) -> str:
        return f"OpenRouter ({self.model}, timeout={_fmt_timeout(self.timeout)})"


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
        logger.warning("No JSON array found in LLM response (%d chars): %s",
                        len(response), response[:300])
        return None

    try:
        data = json.loads(json_match.group())
    except json.JSONDecodeError as e:
        logger.warning("JSON parse error: %s. Raw: %s", e, json_match.group()[:300])
        return None

    if not isinstance(data, list):
        logger.warning("LLM response is not a JSON array: %s", type(data).__name__)
        return None

    validated = []
    for item in data:
        if not isinstance(item, dict):
            continue
        if 'id' not in item:
            continue
        validated.append({
            'id': item['id'],
            'entity': item.get('entity', ''),
            'field_name': item.get('field_name', ''),
            'field_type': item.get('field_type', 'text'),
        })

    if not validated:
        logger.warning("No valid items in LLM response (parsed %d items, 0 valid)", len(data))
    return validated if validated else None
