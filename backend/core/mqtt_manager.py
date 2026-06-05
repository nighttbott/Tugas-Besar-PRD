import asyncio
import json
import logging
from typing import Optional
from aiomqtt import Client, MqttError
from core.config import get_settings

logger = logging.getLogger("mqtt_manager")

class MQTTManager:
    def __init__(self):
        self.settings = get_settings()
        self._loop_task: Optional[asyncio.Task] = None
        self._command_queue = asyncio.Queue()
        self._stop_event = asyncio.Event()

    async def start(self):
        """Starts the MQTT client and connection loop."""
        self._stop_event.clear()
        self._loop_task = asyncio.create_task(self._run_mqtt_loop())

    async def stop(self):
        """Stops the MQTT client connection."""
        self._stop_event.set()
        if self._loop_task:
            self._loop_task.cancel()
            try:
                await self._loop_task
            except asyncio.CancelledError:
                pass
        logger.info("🛑 Disconnected from MQTT Broker.")

    async def _run_mqtt_loop(self):
        """Maintains the MQTT connection and processes outgoing messages."""
        while not self._stop_event.is_set():
            try:
                async with Client(
                    hostname=self.settings.MQTT_BROKER_URL,
                    port=self.settings.MQTT_BROKER_PORT,
                    username=self.settings.MQTT_USERNAME or None,
                    password=self.settings.MQTT_PASSWORD or None,
                ) as client:
                    logger.info(f"✅ Connected to MQTT Broker at {self.settings.MQTT_BROKER_URL}:{self.settings.MQTT_BROKER_PORT}")
                    
                    # Consume the queue and publish
                    while not self._stop_event.is_set():
                        topic, payload = await self._command_queue.get()
                        try:
                            await client.publish(topic, payload=json.dumps(payload), qos=1)
                            logger.info(f"Published to {topic}: {payload}")
                        except MqttError as e:
                            logger.error(f"Failed to publish to {topic}: {e}")
                        finally:
                            self._command_queue.task_done()
            
            except MqttError as e:
                logger.error(f"❌ MQTT connection error: {e}. Reconnecting in 5s...")
                await asyncio.sleep(5)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ Unexpected MQTT error: {e}")
                await asyncio.sleep(5)

    async def publish_command(self, gate_id: str, payload: dict) -> bool:
        """Queues a command to be published to a specific gate's topic."""
        topic = f"gate/{gate_id}/command"
        self._command_queue.put_nowait((topic, payload))
        return True

mqtt_manager = MQTTManager()
