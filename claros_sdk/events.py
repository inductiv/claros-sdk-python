from __future__ import annotations

import inspect
import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


class EventEmitter:
    """Async-compatible event emitter for ClarOS SDK."""

    def __init__(self) -> None:
        self._listeners: dict[str, list[Callable[..., Any]]] = {}

    def on(
        self, event: str, handler: Callable[..., Any] | None = None
    ) -> Callable[..., Any]:
        """
        Register a listener for the given event name.
        Supports usage both as a direct method call and as a decorator:

            client.dispatcher.on("slack.message", my_handler)

            @client.dispatcher.on("slack.message")
            async def my_handler(event): ...
        """

        def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
            if event not in self._listeners:
                self._listeners[event] = []
            if fn not in self._listeners[event]:
                self._listeners[event].append(fn)
            return fn

        if handler is not None:
            return decorator(handler)
        return decorator

    def off(self, event: str, handler: Callable[..., Any]) -> None:
        """Remove a previously registered listener for the event."""
        if event in self._listeners and handler in self._listeners[event]:
            self._listeners[event].remove(handler)

    def remove_listener(self, event: str, handler: Callable[..., Any]) -> None:
        """Alias for off()."""
        self.off(event, handler)

    def remove_all_listeners(self, event: str | None = None) -> None:
        """Remove all listeners for a specific event or for all events if event is None."""
        if event is not None:
            self._listeners.pop(event, None)
        else:
            self._listeners.clear()

    def listeners(self, event: str) -> list[Callable[..., Any]]:
        """Return the list of listeners registered for an event."""
        return list(self._listeners.get(event, []))

    async def emit(self, event: str, *args: Any, **kwargs: Any) -> None:
        """
        Emit an event, invoking all registered sync and async handlers.
        Catches and logs handler exceptions to avoid disrupting other listeners.
        """
        handlers = list(self._listeners.get(event, []))
        for handler in handlers:
            try:
                res = handler(*args, **kwargs)
                if inspect.iscoroutine(res):
                    await res
            except Exception as exc:
                logger.error(
                    "Error executing event handler for '%s': %s",
                    event,
                    exc,
                    exc_info=True,
                )
