"""Tests for event bus."""

import pytest
import asyncio
from job_agent_contracts.events import EventBus, Event, EventType


@pytest.fixture
def bus():
    return EventBus()


class TestEventBus:
    @pytest.mark.asyncio
    async def test_subscribe_and_publish(self, bus):
        received = []

        async def handler(event: Event):
            received.append(event)

        bus.subscribe(EventType.JOB_DISCOVERED, handler)
        await bus.publish(Event(type=EventType.JOB_DISCOVERED, data={"job_id": "123"}))

        assert len(received) == 1
        assert received[0].data["job_id"] == "123"

    @pytest.mark.asyncio
    async def test_multiple_subscribers(self, bus):
        count = {"a": 0, "b": 0}

        async def handler_a(event):
            count["a"] += 1

        async def handler_b(event):
            count["b"] += 1

        bus.subscribe(EventType.JOB_APPLIED, handler_a)
        bus.subscribe(EventType.JOB_APPLIED, handler_b)
        await bus.publish(Event(type=EventType.JOB_APPLIED))

        assert count["a"] == 1
        assert count["b"] == 1

    @pytest.mark.asyncio
    async def test_no_cross_event_firing(self, bus):
        received = []

        async def handler(event):
            received.append(event)

        bus.subscribe(EventType.JOB_DISCOVERED, handler)
        await bus.publish(Event(type=EventType.JOB_APPLIED))

        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_unsubscribe(self, bus):
        received = []

        async def handler(event):
            received.append(event)

        bus.subscribe(EventType.JOB_MATCHED, handler)
        bus.unsubscribe(EventType.JOB_MATCHED, handler)
        await bus.publish(Event(type=EventType.JOB_MATCHED))

        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_history(self, bus):
        await bus.publish(Event(type=EventType.PIPELINE_STARTED))
        await bus.publish(Event(type=EventType.PIPELINE_COMPLETED))

        assert len(bus.get_history()) == 2
        assert len(bus.get_history(EventType.PIPELINE_STARTED)) == 1

    @pytest.mark.asyncio
    async def test_handler_error_doesnt_break_others(self, bus):
        results = []

        async def bad_handler(event):
            raise ValueError("oops")

        async def good_handler(event):
            results.append("ok")

        bus.subscribe(EventType.JOB_DISCOVERED, bad_handler)
        bus.subscribe(EventType.JOB_DISCOVERED, good_handler)
        await bus.publish(Event(type=EventType.JOB_DISCOVERED))

        assert results == ["ok"]
