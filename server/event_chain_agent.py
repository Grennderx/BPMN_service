# event_chain_agent.py
import re
import json
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)

class JSONParseError(Exception):
    pass

class EventChainAgent:

    def __init__(self, llm_callable: Any):
            """
            llm_callable(prompt: str, **kwargs) -> {"choices": [{"text": str}, ...]}
            """
            self.llm = llm_callable

    def generate_chain(self, process_description):
        prompt = f"""
**Вы эксперт в BPMN 2.0. Создайте максимально информативную и логичную диаграмму, используя:**
- Задачи (Tasks)
- События: start, end, intermediate
- Шлюзы: exclusive (условия), parallel (параллельные потоки)
- Последовательности потоков (Sequence Flow)

**Формат ответа:**
{{
  "nodes": [
    {{"id": "str", "name": "str", "type": "start/end/task/gateway/intermediate"}},
    {{"id": "g1", "name": "Пример шлюза", "type": "gateway", "gateway_type": "exclusive/parallel"}}
  ],
  "flows": [
    {{"source": "source_id", "target": "target_id"}}
  ]
}}

**Правила:**
1. Используйте ДВОЙНЫЕ КАВЫЧКИ для всех ключей и значений
2. Все элементы должны быть связаны корректными потоками
3. Для шлюзов (gateway) обязательно поле gateway_type
4. Пример использования intermediate события:
   {{"id": "i1", "name": "Уведомление", "type": "intermediate"}}

Описание процесса: {process_description}
ВАЖНО: Только JSON без пояснений! Проверьте валидность перед отправкой.
```json
"""
        logging.debug("Формирование промпта для генерации цепочки: %s", prompt)
        
        response = self.llm(
            prompt=prompt,
            max_tokens=4096,
            temperature=0.3,
            stop=["\n\n"]
        )
        raw = response["choices"][0]["text"]
        logger.debug("Сырой ответ LLM:\n%s", raw)
        
        json_str = self._extract_json(raw)
        logging.debug("Выделенный JSON-строковый блок: %s", json_str)
        
        data = self._validate_json(json_str)
        logging.debug("Валидированный event_chain: %s", data)
        return data
    def _extract_json(self, text: str) -> str:
        # Извлекаем JSON из блока кода
        match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
        if match:
            return match.group(1).strip()
        
        # Или находим первый валидный JSON
        first = text.find("{")
        last = text.rfind("}")
        if first != -1 and last != -1 and last > first:
            return text[first:last+1].strip()
        
        raise ValueError("Не найден корректный JSON")

    def _validate_json(self, json_str: str) -> dict:
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            # Логируем позицию ошибки
            error_pos = getattr(e, 'pos', None)
            logging.error(f"Ошибка декодирования JSON на позиции {error_pos}: {e}")
            raise ValueError(f"Некорректный JSON: {str(e)}")
        
        # Проверка структуры
        if not isinstance(data, dict):
            raise ValueError("Ожидался объект JSON, но получен другой тип данных")
        
        required_keys = ["nodes", "flows"]
        if not all(k in data for k in required_keys):
            raise ValueError(f"Отсутствуют обязательные ключи: {required_keys}")
        
        # Проверка узлов
        for node in data["nodes"]:
            if not all(k in node for k in ["id", "name", "type"]):
                raise ValueError(f"Неполный узел: {node}")
            if node["type"] == "gateway" and "gateway_type" not in node:
                raise ValueError(f"Шлюз без типа: {node['id']}")
        
        # Проверка потоков
        for flow in data["flows"]:
            if not all(k in flow for k in ["source", "target"]):
                raise ValueError(f"Некорректный поток: {flow}")
        
        return data
