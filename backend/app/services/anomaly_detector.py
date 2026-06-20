import os
import logging
import clickhouse_connect
import numpy as np
from app.utils.memory import conversation_memory
from app.crew.tools import MessengerDeliveryTool

logger = logging.getLogger("anomaly_detector")

def detect_anomalies():
    """Проверка аномалий в данных реального времени (статистический подход)."""
    logger.info("Running statistical anomaly detection check...")
    try:
        client = clickhouse_connect.get_client(
            host=os.getenv("CLICKHOUSE_HOST", "localhost"),
            port=int(os.getenv("CLICKHOUSE_PORT", "8123")),
            username=os.getenv("CLICKHOUSE_USER", "default"),
            password=os.getenv("CLICKHOUSE_PASSWORD", ""),
        )
        
        query = """
        SELECT region, SUM(amount) as total_amount
        FROM enterprise_taxes
        GROUP BY region
        ORDER BY total_amount ASC
        """
        
        result = client.query(query)
        if not result.result_rows:
            logger.info("No data for anomaly check.")
            return

        data = []
        regions = []
        for row in result.result_rows:
            regions.append(row[0])
            data.append(float(row[1]))
            
        if len(data) < 3:
            logger.info("Not enough data to run statistics.")
            return

        mean = np.mean(data)
        std = np.std(data)
        
        anomalies = []
        if std > 0:
            for i, val in enumerate(data):
                z_score = (val - mean) / std
                if z_score < -1.5:  # Сильное падение
                    anomalies.append((regions[i], val))
                    
        if anomalies:
            msg = "⚠️ *SYSTEM ALERT*: Обнаружены аномалии в налоговых поступлениях:\n\n"
            for r, v in anomalies:
                msg += f"- **{r}**: аномально низкие сборы ({v:,.2f} руб.)\n"
            
            logger.warning(msg)
            
            # Сохраняем алерт в историю последнего диалога
            sessions = conversation_memory.get_all_sessions()
            if sessions:
                latest_session = list(sessions.keys())[-1]
                conversation_memory.add_message(latest_session, "assistant", msg)
                
            # Также отправляем в мессенджер
            tool = MessengerDeliveryTool()
            tool._run(msg)
            
        else:
            logger.info("No statistical anomalies found.")
            
    except Exception as e:
        logger.error(f"Failed anomaly check: {str(e)}")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    detect_anomalies()
