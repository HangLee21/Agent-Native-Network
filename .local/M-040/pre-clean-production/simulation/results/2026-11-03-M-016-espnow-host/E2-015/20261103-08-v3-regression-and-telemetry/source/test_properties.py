import unittest
from protocol_properties import check_trace

ID=["a","boot-a",1]


class PropertyCheckerTests(unittest.TestCase):
    def test_valid_trace(self):
        rows=[dict(event="generated",identity=ID),dict(event="queue",size=1),
              dict(event="link_send",identity=ID),dict(event="delivered",identity=ID,destination="c",path_valid=True),
              dict(event="complete",identity=ID),dict(event="queue",size=0)]
        self.assertEqual(check_trace(rows,capacity=2),[])

    def test_partition_must_not_fabricate_delivery_but_may_attempt(self):
        rows=[dict(event="generated",identity=ID),dict(event="link_send",identity=ID,physical_link_available=False)]
        self.assertFalse(check_trace(rows,capacity=1))
        rows.append(dict(event="delivered",identity=ID,destination="c",path_valid=False))
        self.assertIn("delivery across partition",check_trace(rows,capacity=1))

    def test_duplicate_delivery_and_ack_completion(self):
        rows=[dict(event="generated",identity=ID)]+[dict(event="delivered",identity=ID,destination="c")]*2+[dict(event="complete",identity=ID)]*2
        result=check_trace(rows,capacity=1)
        self.assertIn("duplicate application delivery",result)
        self.assertIn("duplicate completion from ACK",result)

    def test_cancel_and_expiry_stop_retries(self):
        for terminal in ["cancel","expired"]:
            rows=[dict(event="generated",identity=ID),dict(event=terminal,identity=ID),dict(event="link_send",identity=ID)]
            with self.subTest(terminal=terminal):
                self.assertIn("retry after cancel/expiry/complete",check_trace(rows,capacity=1))

    def test_late_ack_does_not_override_cancellation(self):
        rows=[dict(event="generated",identity=ID),dict(event="cancel",identity=ID),dict(event="complete",identity=ID)]
        self.assertIn("conflicting terminal completion after cancel/expiry",check_trace(rows,capacity=1))

    def test_reboot_reuse_requires_new_boot_id(self):
        rows=[dict(event="generated",identity=ID),dict(event="generated",identity=["a","boot-b",1])]
        self.assertFalse(check_trace(rows,capacity=1))
        rows.append(dict(event="generated",identity=ID))
        self.assertIn("invalid/repeated origin+boot+sequence",check_trace(rows,capacity=1))

    def test_queue_cap(self):
        self.assertIn("queue capacity exceeded",check_trace([dict(event="queue",size=3)],capacity=2))

    def test_no_delivery_without_generation(self):
        self.assertIn("delivery without generation",check_trace([dict(event="delivered",identity=ID,destination="c")],capacity=2))
