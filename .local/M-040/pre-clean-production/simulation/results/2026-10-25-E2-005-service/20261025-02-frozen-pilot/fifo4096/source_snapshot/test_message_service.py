"""Analytic and invariant checks for the shared application-byte service."""

import math
import random
import unittest

from message_service import MessageService


class MessageServiceTests(unittest.TestCase):
    def test_fifo_serialization_and_propagation(self):
        # Analytic example 1: 10-byte packets, rate 10, propagation 0.5.
        service = MessageService("fifo", delay=0.5, rate_bytes_per_time=10)
        first = service.submit(0, 0, [1], "state", b"a" * 10)
        second = service.submit(0, 0, [1], "state", b"b" * 10)
        self.assertEqual(service.next_event_time(), 1)
        self.assertEqual(service.pop_due(1), [])
        self.assertEqual(service.stats(1)["propagation_bytes"], 10)
        self.assertEqual(service.pop_due(1.5)[0]["message_id"], first)
        self.assertEqual(service.pop_due(2.5)[0]["message_id"], second)
        stats = service.stats(2.5)
        self.assertEqual(stats["completed_service_bytes"], 20)
        self.assertEqual(stats["latency_mean"], 2)

    def test_broadcast_overhead_and_recipients(self):
        # Analytic example 2: body 8 + overhead 2, one send, two receivers.
        service = MessageService("fifo", rate_bytes_per_time=10, overhead_bytes=2)
        service.submit(0, 0, [1, 2, 1], "event", b"12345678")
        due = service.pop_due(1)
        self.assertEqual([x["recipient"] for x in due], [1, 2])
        stats = service.stats(1)
        self.assertEqual(stats["serviced_bytes"], 10)
        self.assertEqual(stats["recipient_delivered_application_bytes"], 16)
        self.assertEqual(stats["demand_application_bytes"], 8)

    def test_full_packet_capacity_and_same_time_release(self):
        # Analytic example 3: partial service does not free packet buffer.
        service = MessageService("fifo", delay=5, rate_bytes_per_time=10, capacity_bytes=10)
        service.submit(0, 0, [1], "event", b"a" * 10)
        rejected = service.submit(0.9, 0, [1], "event", b"b")
        stats = service.stats(0.9)
        self.assertAlmostEqual(stats["serviced_bytes"], 9)
        self.assertEqual(stats["buffer_occupied_bytes"], 10)
        self.assertEqual(stats["dropped"], 1)
        accepted = service.submit(1, 0, [1], "event", b"c" * 10)
        stats = service.stats(1)
        self.assertEqual(stats["accepted"], 2)
        self.assertEqual(stats["propagation_bytes"], 10)
        self.assertTrue(any(e["event"] == "rejected" and e["message_id"] == rejected for e in service.ledger))
        self.assertEqual([d["message_id"] for d in service.pop_due(7)], ["m00000001", accepted])

    def test_cutoff_partial_service_and_waiting_inventory(self):
        # Analytic example 4: at H=.5, 5 served, 5 in-service remaining, 10 waiting.
        service = MessageService("fifo", delay=3, rate_bytes_per_time=10, capacity_bytes=20)
        service.submit(0, 0, [1, 2], "state", b"a" * 10)
        service.submit(0, 1, [0], "event", b"b" * 10)
        stats = service.stats(0.5)
        self.assertEqual(stats["serviced_bytes"], 5)
        self.assertEqual(stats["remaining_service_bytes"], 15)
        self.assertEqual(stats["in_service_remaining_bytes"], 5)
        self.assertEqual(stats["queue_bytes"], 10)
        self.assertEqual(stats["in_service_buffer_bytes"], 10)
        self.assertEqual(stats["recipient_unmet"], 3)
        self.assertEqual(stats["completed_service_bytes"], 0)
        self.assertFalse(any(e["event"] in {"delivered", "service_completed"} for e in service.ledger))

    def test_relaxed_modes_and_same_time_redrain(self):
        # Analytic example 5: capacity/rate relaxed, exact delay and redrain.
        instant = MessageService("instant", delay=100, capacity_bytes=0)
        instant.submit(2, 0, [1], "state", b"a")
        self.assertEqual(instant.pop_due(2)[0]["delivered_at"], 2)
        instant.submit(2, 1, [0], "state", b"b")
        self.assertEqual(len(instant.pop_due(2)), 1)
        self.assertEqual(instant.pop_due(2), [])
        self.assertTrue(instant.stats(2)["resource_relaxed"])
        delayed = MessageService("fixed_delay", delay=3, capacity_bytes=0)
        delayed.submit(2, 0, [1], "state", b"a")
        self.assertEqual(delayed.pop_due(4.999), [])
        self.assertEqual(delayed.pop_due(5)[0]["delivered_at"], 5)

    def test_polling_frequency_does_not_change_service(self):
        def run(poll):
            service = MessageService("fifo", delay=0.2, rate_bytes_per_time=10, capacity_bytes=20)
            deliveries = []
            for i, when in enumerate((0, 0.3, 0.7, 1.0, 1.3, 2.0)):
                if poll:
                    deliveries.extend(service.pop_due(when))
                service.submit(when, 0, [1], "event", bytes([i]) * 10)
            deliveries.extend(service.pop_due(10))
            return deliveries, service.stats(10), service.ledger
        self.assertEqual(run(True), run(False))

    def test_key_never_replaces_ordered_events(self):
        service = MessageService("fifo", rate_bytes_per_time=1)
        service.submit(0, 0, [1], "intent", b"a", key="same")
        service.submit(0, 0, [1], "intent", b"b", key="same")
        self.assertEqual([d["payload"] for d in service.pop_due(2)], [b"a", b"b"])

    def test_validation_and_zero_bytes(self):
        with self.assertRaises(ValueError):
            MessageService("fifo", rate_bytes_per_time=0)
        service = MessageService("fifo", capacity_bytes=0)
        with self.assertRaises(TypeError):
            service.submit(0, 0, [1], "event", bytearray(b"a"))
        with self.assertRaises(ValueError):
            service.submit(0, 0, [], "event", b"a")
        service.submit(0, 0, [0], "event", b"")
        self.assertEqual(service.pop_due(0)[0]["recipient"], 0)
        self.assertEqual(service.next_event_time(), math.inf)
        service.stats(1)
        with self.assertRaises(ValueError):
            service.stats(0)

    def test_uncollected_deliveries_are_available_at_current_time(self):
        service = MessageService()
        service.submit(0, 0, [1], "event", b"a")
        service.stats(2)
        self.assertEqual(service.next_event_time(), 2)
        self.assertEqual(service.pop_due(2)[0]["delivered_at"], 0)

    def test_seeded_inventory_and_cost_conservation(self):
        random_source = random.Random(1905)
        service = MessageService("fifo", delay=0.7, rate_bytes_per_time=13,
                                 capacity_bytes=30, overhead_bytes=2)
        now = 0
        for i in range(100):
            now += random_source.random() * 0.2
            service.submit(now, i % 3, [(i + 1) % 3], "event", b"a" * random_source.randrange(1, 15))
            stats = service.stats(now)
            self.assertEqual(stats["demand_service_bytes"], stats["admitted_service_bytes"] + stats["rejected_service_bytes"])
            self.assertAlmostEqual(stats["admitted_service_bytes"], stats["serviced_bytes"] + stats["remaining_service_bytes"])
            self.assertEqual(stats["buffer_occupied_bytes"], stats["queue_bytes"] + stats["in_service_buffer_bytes"])
            self.assertLessEqual(stats["buffer_occupied_bytes"], 30)
            self.assertEqual(stats["accepted"], stats["pending"] + stats["delivered"])
            self.assertEqual(stats["demanded"], stats["accepted"] + stats["dropped"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
