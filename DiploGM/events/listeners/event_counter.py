import logging

from DiploGM.events.base_listener import BaseListener
from DiploGM.events.events import Event

logger = logging.getLogger(__name__)


class EventCounter(BaseListener):
    """
    As Event Listeners, these are best used for non side-effect processes.
    Otherwise you need an infrastructure that can keep track of the progress of events or what not.
    """
    def __init__(self, bot) -> None:
        self.bot = bot
        self.counter = 0

    def setup(self, bus):
        self.bus = bus
        bus.subscribe(Event, self)

    def close(self):
        logger.info(f"Shutting down {self.__class__.__name__}")

    def supports(self, event) -> bool:
        """ 
        What conditions are required for the Event to be handled.
        Examples could be:
            - gametype / data_file (is event from impdip.1.6 or helladip.0.3)
            - event type `isinstance(event, OrderSubmitted)`
        """
        return True

    async def process(self, event):
        self.counter += 1
