import json
import logging
import re
from typing import Any, Dict

class CriticAgent:
    def __init__(self, llm_callable: Any):
        """
        Ожидает LLM-функцию с сигнатурой:
        llm_callable(prompt: str, **kwargs) -> {"choices": [{"text": str}]}
        или
        llm_callable(prompt: str, **kwargs) -> {"choices": [{"message": {"content": str}}]}
        """
        self.llm = llm_callable

    def analyze_diagram(self, bpmn_json: dict) -> dict:
        """Основной метод анализа диаграммы"""
        errors = self._find_structural_errors(bpmn_json)
        llm_analysis = self._analyze_with_llm(bpmn_json, errors)

        return {
            "algorithm_errors": errors,
            "llm_recommendations": llm_analysis
        }

    def _find_structural_errors(self, data: dict) -> list[dict]:
        """Алгоритмическая проверка базовых ошибок"""
        errors = []

        # 1. Проверка стартового события
        if not any(n['type'] == 'start' for n in data['nodes']):
            errors.append({
                "code": "NO_START",
                "message": "Отсутствует стартовое событие",
                "elements": []
            })

        # 2. Проверка конечного события
        if not any(n['type'] == 'end' for n in data['nodes']):
            errors.append({
                "code": "NO_END",
                "message": "Отсутствует конечное событие",
                "elements": []
            })

        # 3. Поиск висячих элементов
        all_elements = {n['id']: n for n in data['nodes']}
        connected = set()
        for flow in data['flows']:
            connected.add(flow['source'])
            connected.add(flow['target'])

        for elem_id, elem in all_elements.items():
            if elem_id not in connected and elem['type'] not in ['start', 'end']:
                errors.append({
                    "code": "ORPHAN_ELEMENT",
                    "message": f"Несвязанный элемент: {elem['name']}",
                    "elements": [elem_id]
                })

        # 4. Проверка шлюзов
        for node in data['nodes']:
            if node['type'] == 'gateway':
                if 'gateway_type' not in node:
                    errors.append({
                        "code": "GATEWAY_TYPE_MISSING",
                        "message": f"Шлюз {node['name']} не имеет типа",
                        "elements": [node['id']]
                    })

        return errors

    def _analyze_with_llm(self, data: dict, found_errors: list[dict]) -> dict:
        """Анализ с помощью LLM"""
        prompt = f"""
**Ты эксперт в BPMN 2.0. Проанализируйте диаграмму:**

Текущая структура:
{json.dumps(data, indent=2)}

Имеется список известных проблем, которые нужно исправить обязательно. 
Найденные ошибки:
{json.dumps(found_errors, indent=2)}

Используй не только этот список, но также и самостоятельно попробуй найти ошибки, нестыковки или 
нарушения стандартов BPMN 2.0.
Рассуждай последовательно, шаг за шагом, это очень важно.
При формировании ответа указывай элементы по имени, а не по индексам, например, не
"Убрать задачу t5", а "Убрать задачу 'Ожидание'";
переводи "gateway" как "шлюз", а не как "ворота"

Использовать можно ТОЛЬКО следующие элементы:
- Задачи (Tasks)
- События: start, end, intermediate
- Шлюзы: exclusive (условия), parallel (параллельные потоки)
- Последовательности потоков (Sequence Flow)

**Сформулируй:**
1. Краткий вывод о качестве диаграммы;
2. Рекомендации по улучшению (как минимум одна должна быть обязательно, больше четырех не надо);
3. Найденные критические проблемы (не забудь включить уже найденные).

Обрати внимание - ВАЖНО, чтобы была как минимум одна рекомендация

Обрати внимание, что все допустимые названия типов элементов я тебе предоставил, иные делать 
категорические нельзя, поэтому если собираешься дать рекомендацию про название типа элемента, 
то выбирай только из перечисленных - это очень важно.

Используй только указанный далее формат ответа, ни в коем случае не нарушайте его.
**Формат ответа:**
{{
  "assessment": "текст оценки качества диаграммы",
  "recommendations": ["список рекомендаций по улучшению"],
  "critical_issues": ["список проблем"]
}}

ВАЖНО: Только JSON без пояснений и любого лишнего текста! Проверьте валидность перед отправкой.
"""

        try:
            response = self.llm(
                prompt=prompt,
                max_tokens=4096,
                temperature=0.3,
                stop=["\n\n"]
            )

            content = self._extract_llm_content(response)
            if not content:
                return {}

            # Извлекаем первый валидный JSON
            json_data = self._parse_first_json(content)
            if not json_data:
                return {}

            # Валидация структуры
            if not all(k in json_data for k in ['assessment', 'recommendations', 'critical_issues']):
                logging.error("Неполный JSON ответ: %s", json_data)
                return {}

            return json_data

        except json.JSONDecodeError as e:
            logging.error(f"JSON Decode Error: {str(e)}")
            logging.debug(f"Problem content: {content}")
            return {}
        except Exception as e:
            logging.exception("LLM analysis failed")
            return {}
    def generate_llm_fixes(self, data: dict, issues: list[str]) -> dict:
        """Генерация полного исправления через LLM с учетом как ошибок, так и рекомендаций"""
        prompt = f"""
**Ты эксперт в BPMN 2.0. Исправь все ошибки в диаграмме:**

**Текущая структура:**
{json.dumps(data, indent=2)}

**Список проблем и рекомендаций:**
{chr(10).join(issues)}

Использовать можно следующие элементы:
- Задачи (Tasks)
- События: start, end, intermediate
- Шлюзы: exclusive (условия), parallel (параллельные потоки)
- Последовательности потоков (Sequence Flow)

**ОБЯЗАТЕЛЬНЫЕ ТРЕБОВАНИЯ:**
1. Исправь ВСЕ указанные проблемы
2. Измени диаграмму в соответствии со ВСЕМИ рекомендациями
3. Верни формат JSON
4. Для новых элементов генерируй уникальные ID
5. Сохрани логику работы, изменив только то, что указано в ошибках или рекомендациях
6. Убедись, что:
   - Есть ровно одно стартовое и одно конечное событие
   - Все элементы связаны корректными потоками
   - Шлюзы имеют явно указанный тип (exclusive/parallel)

**Верни ТОЛЬКО исправленный JSON без комментариев.**

Формат ответа:
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
1. Используй ДВОЙНЫЕ КАВЫЧКИ для всех ключей и значений
2. Все элементы должны быть связаны корректными потоками
3. Для шлюзов (gateway) обязательно поле gateway_type
4. Пример использования intermediate события:
   {{"id": "i1", "name": "Уведомление", "type": "intermediate"}}

ВАЖНО: Только JSON без пояснений и любого лишнего текста! Проверь валидность перед отправкой.
"""

        try:
            response = self.llm(
                prompt=prompt,
                max_tokens=4096,
                temperature=0.3,
                stop=["\n\n"]
            )

            content = self._extract_llm_content(response)
            if not content:
                return data

            json_data = self._parse_first_json(content)
            if not json_data:
                return data

            # Валидация ключей
            if not all(k in json_data for k in ['nodes', 'flows']):
                logging.error("Некорректный формат исправлений: %s", json_data)
                return data

            return json_data

        except json.JSONDecodeError as e:
            logging.error(f"JSON Decode Error: {str(e)}")
            return data
        except Exception as e:
            logging.exception("Fix generation failed")
            return data

    def _extract_llm_content(self, response: dict) -> str:
        """Универсальное извлечение содержимого из ответа LLM"""
        content = ""
        if isinstance(response, dict) and 'choices' in response:
            choice = response['choices'][0]
            content = choice.get('message', {}).get('content') or choice.get('text', '')
        return content.strip()

    def _parse_first_json(self, text: str) -> dict:
        pattern = r'\{[\s\S]*?\}'
        for match in re.finditer(pattern, text):
            snippet = match.group(0)
            try:
                return json.loads(snippet)
            except json.JSONDecodeError:
                continue
        return {}
