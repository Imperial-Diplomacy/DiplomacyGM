import logging
from typing import List, Type

from DiploGM.utils.singleton import SingletonMeta
from DiploGM.events.base_listener import BaseListener
from DiploGM.events.events import Event

logger = logging.getLogger(__name__)


class EventBus(metaclass=SingletonMeta):
    def __init__(self) -> None:
        self.listeners: dict[BaseListener, List[Type[Event]]] = {}
        self.subscribers: dict[Type[Event], List[BaseListener]] = {}

    def close(self):
        logger.info("Stopping the Event Bus")
        for ln in self.listeners:
            ln.close()

        self.subscribers.clear()

    async def disconnect(self, ln: BaseListener):
        for event_type in self.listeners.get(ln, []):
            self.subscribers[event_type].remove(ln)

        del self.listeners[ln]

    async def disconnect_all(self):
        self.listeners = {}
        self.subscribers = {}

    async def publish(self, event: Event):
        logger.info(f"Publishing {event}")
        listeners: List[BaseListener] = self.subscribers.get(type(event), [])
        for ln in listeners:
            try:
                await ln.handle(event)
            except Exception as e:
                logger.error(f"Listener {ln} failed: {e}")

    def subscribe(self, event_type: Type[Event], ln: BaseListener):
        if event_type not in self.subscribers:
            self.subscribers[event_type] = []

        if ln not in self.listeners:
            self.listeners[ln] = []
            
        self.subscribers[event_type].append(ln)
        self.listeners[ln].append(event_type)

    def unsubscribe(self, event_type: Type[Event], ln: BaseListener):
        if ln not in self.listeners:
            return

        self.listeners[ln].remove(event_type)
        self.subscribers[event_type].remove(ln)
