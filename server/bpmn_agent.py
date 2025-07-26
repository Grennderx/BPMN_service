import os
import logging
import bpmn_python.bpmn_python_consts as consts
from bpmn_python.bpmn_diagram_rep import BpmnDiagramGraph
from datetime import datetime
from typing import Tuple

logger = logging.getLogger(__name__)

class BPMNAgent:
    def __init__(self, client=None):
        self.client = client

    def generate_raw_bpmn(self, bpmn_data: dict, filename: str = None) -> Tuple[str, str]:
        """
        Генерирует "сырую" BPMN-диаграмму (без ручных координат).
        Возвращает кортеж (bpmn_xml, filename).
        """
        try:
            logger.info("Начало генерации сырого BPMN")

            if not isinstance(bpmn_data, dict):
                raise ValueError("Ожидался словарь, но получен другой тип данных")

            # Создание нового графа диаграммы
            bpmn_graph = BpmnDiagramGraph()
            bpmn_graph.create_new_diagram_graph(diagram_name="Process")
            process_id = bpmn_graph.add_process_to_diagram("MainProcess")
            node_map = {}

            # Добавляем узлы
            for node in bpmn_data.get("nodes", []):
                node_type = node.get("type")
                node_name = node.get("name", "Unnamed")

                if node_type == "start":
                    node_id, _ = bpmn_graph.add_start_event_to_diagram(
                        process_id,
                        node_name,
                        start_event_definition="message"
                    )
                elif node_type == "end":
                    node_id, _ = bpmn_graph.add_end_event_to_diagram(
                        process_id,
                        node_name,
                        end_event_definition="terminate"
                    )
                elif node_type == "gateway":
                    gateway_type = node.get("gateway_type")
                    if gateway_type == "exclusive":
                        node_id, _ = bpmn_graph.add_exclusive_gateway_to_diagram(
                            process_id,
                            node_name,
                            gateway_direction="Diverging"
                        )
                    else:
                        node_id, _ = bpmn_graph.add_parallel_gateway_to_diagram(
                            process_id,
                            node_name,
                            gateway_direction="Diverging"
                        )
                else:
                    node_id, _ = bpmn_graph.add_task_to_diagram(
                        process_id,
                        node_name
                    )

                node_map[node["id"]] = node_id

            # Добавляем потоки
            for flow in bpmn_data.get("flows", []):
                src = node_map.get(flow["source"])
                trg = node_map.get(flow["target"])
                if src and trg:
                    bpmn_graph.add_sequence_flow_to_diagram(
                        process_id,
                        src,
                        trg,
                        "Flow"
                    )

            # Подготовка имени файла
            if not filename:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"diagram_{timestamp}.bpmn"

            output_dir = "exported_diagrams/"
            os.makedirs(output_dir, exist_ok=True)
            bpmn_graph.export_xml_file(output_dir, filename)

            file_path = os.path.join(output_dir, filename)

            # Проверяем, что файл есть
            if not os.path.exists(file_path):
                logger.error("BPMN-файл не найден после экспорта: %s", file_path)
                raise FileNotFoundError(f"BPMN-файл не создан: {file_path}")

            # Читаем и возвращаем XML
            with open(file_path, "r", encoding="utf-8") as f:
                bpmn_xml = f.read()

            return bpmn_xml, filename

        except Exception as e:
            logger.error("Ошибка генерации сырого BPMN: %s", e, exc_info=True)
            raise
