import json
import logging
import os
from typing import Any

logger = logging.getLogger("WrenAIClient")

class MockWrenToolkit:
    """Mock for WrenToolkit from wren-langchain SDK."""
    
    def __init__(self, project_path: str):
        self.project_path = project_path
        
    def get_tools(self) -> list[Any]:
        return []
        
    def query(self, sql: str):
        logger.info(f"[WrenAI] Executing query via semantic layer: {sql}")
        return []

class WrenAIClient:
    def __init__(self):
        self.project_path = "./wren_project"
        self.toolkit = MockWrenToolkit(self.project_path)
        self.rules_file = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'semantic_rules.json')
        logger.info("WrenAI Client initialized (SDK adapter)")

    def get_rules(self) -> list[dict]:
        if not os.path.exists(self.rules_file):
            return [
                {"id": "rule_1", "name": "VIP Клиент", "description": "Сумма налогов больше 10 млн", "active": True}
            ]
        try:
            with open(self.rules_file, encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading semantic rules: {e}")
            return []
            
    def save_rules(self, rules: list[dict]):
        os.makedirs(os.path.dirname(self.rules_file), exist_ok=True)
        with open(self.rules_file, 'w', encoding='utf-8') as f:
            json.dump(rules, f, ensure_ascii=False, indent=2)

    def sync_schema(self, schema_def: dict[str, Any]):
        """Синхронизация схемы ClickHouse со слоем контекста WrenAI."""
        logger.info(f"Syncing schema with WrenAI Context Layer: {json.dumps(schema_def)}")
        return True
        
    def get_semantic_context(self, question: str) -> str:
        """Получить контекст таблиц для формирования SQL через слой WrenAI."""
        logger.info(f"Fetching context from WrenAI for: {question}")
        return "В таблице tax_data есть поля: region, accrued (начисления), paid, debt (задолженности). В enterprise_taxes есть поля: amount, status ('Оплачено' - начисления, 'Взыскание'/'Просрочка' - задолженности)."

wren_client = WrenAIClient()
