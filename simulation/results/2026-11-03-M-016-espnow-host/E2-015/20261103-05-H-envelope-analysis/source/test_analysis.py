import copy
import json
import unittest

from analyze_logs import analyze, parse_lines, validate_measurement_record


def config(**changes):
    value=dict(run_id="fixture",destination_id="b",mode="raw_no_retry",evidence_kind="synthetic",
               receiver_log_complete=True,measurement_duration_us=1_000_000,
               duration_clock="host_monotonic_controlled_window")
    value.update(changes)
    return value


def event(kind,node="a",boot="a1",t=10,**changes):
    value=dict(schema="ann.serial.v1",event=kind,run_id="fixture",node_id=node,boot_id=boot,
               origin_id="a",origin_boot_id="a1",seq=1,t_us=t,frame_bytes=128,payload_bytes=16)
    value.update(changes)
    return value


class AnalysisTests(unittest.TestCase):
    def test_callback_success_is_not_delivery(self):
        result=analyze([event("generated"),event("tx_submit",t=20,accepted=True),
                        event("tx_result",t=30,status="success")],config())
        self.assertEqual(result["driver_accepted"],1)
        self.assertEqual(result["link_callbacks_success"],1)
        self.assertEqual(result["destination_unique_rx_observed"],0)
        self.assertEqual(result["pdr"],0)

    def test_unique_payload_goodput_excludes_header_and_duplicate(self):
        rows=[event("generated"),event("rx","b","b1",900_000),event("rx","b","b1",900_010)]
        result=analyze(rows,config())
        self.assertEqual((result["destination_unique_rx_observed"],result["destination_duplicates_observed"]),(1,1))
        self.assertEqual(result["goodput_bps"],128)
        self.assertEqual(result["evidence_kind"],"synthetic")

    def test_no_cross_device_one_way_delay(self):
        result=analyze([event("generated",t=900_000),event("rx","b","b1",3)],config())
        self.assertEqual(result["pdr"],1)
        self.assertIsNone(result["one_way_delay_ms"])

    def test_same_clock_echo_rtt_and_duplicate_echo(self):
        result=analyze([event("generated",t=100),event("echo",t=10_100),event("echo",t=11_100)],config())
        self.assertEqual(result["rtt_p95_ms"],10)
        self.assertEqual(result["successful_same_boot_rtt_count"],1)
        self.assertEqual(result["generated_without_echo"],0)

    def test_echo_after_source_reboot_is_not_rtt(self):
        result=analyze([event("generated"),event("echo",boot="a2",t=20)],config())
        self.assertIsNone(result["rtt_p95_ms"])
        self.assertEqual(result["invalid_echoes"],1)

    def test_missing_receiver_coverage_is_unknown_not_zero_pdr(self):
        result=analyze([event("generated")],config(receiver_log_complete=False))
        self.assertIsNone(result["pdr"])
        self.assertIsNone(result["goodput_bps"])

    def test_missing_measured_window_is_unknown_goodput(self):
        result=analyze([event("generated"),event("rx","b","b1",10)],config(measurement_duration_us=None))
        self.assertEqual(result["pdr"],1)
        self.assertIsNone(result["goodput_bps"])

    def test_nominal_or_cross_clock_window_is_not_accepted(self):
        result=analyze([event("generated"),event("rx","b","b1",10)],config(duration_clock="nominal_interval_times_count"))
        self.assertIsNone(result["goodput_bps"])

    def test_reboot_sequence_collision_without_origin_boot_is_ambiguous(self):
        rows=[event("generated"),event("generated",boot="a2",origin_boot_id="a2"),event("rx","b","b1",50)]
        del rows[-1]["origin_boot_id"]
        result=analyze(rows,config())
        self.assertEqual(result["generated_unique"],2)
        self.assertEqual(result["unmatched_or_ambiguous_rx"],1)
        self.assertIsNone(result["pdr"])

    def test_explicit_origin_boot_resolves_sequence_reuse(self):
        result=analyze([event("generated"),event("generated",boot="a2",origin_boot_id="a2"),
                        event("rx","b","b1",50,origin_boot_id="a2")],config())
        self.assertEqual(result["generated_unique"],2)
        self.assertEqual(result["pdr"],.5)

    def test_foreign_receiver_is_not_final_delivery(self):
        result=analyze([event("generated"),event("rx","relay","r1",80)],config())
        self.assertEqual(result["destination_unique_rx_observed"],0)

    def test_receiver_reboot_duplicate_still_deduplicated(self):
        result=analyze([event("generated"),event("rx","b","b1",50),event("rx","b","b2",5)],config())
        self.assertEqual(result["destination_unique_rx_observed"],1)
        self.assertEqual(result["destination_duplicates_observed"],1)

    def test_raw_retries_are_reported_reliable_mode_separate(self):
        rows=[event("generated"),event("tx_submit",t=20,accepted=True),event("tx_submit",t=30,accepted=True)]
        self.assertTrue(analyze(rows,config())["issues"])
        self.assertFalse(analyze(rows,config(mode="reliable"))["issues"])

    def test_frame_limit_and_payload_mismatch(self):
        for row in [event("rx","b","b1",50,frame_bytes=251),event("rx","b","b1",50,payload_bytes=90),event("rx","b","b1",50,payload_bytes=15)]:
            with self.subTest(row=row):
                result=analyze([event("generated"),row],config())
                self.assertTrue(result["issues"])
                self.assertIsNone(result["pdr"])

    def test_unknown_payload_keeps_goodput_null(self):
        result=analyze([event("generated"),event("rx","b","b1",50,payload_bytes=None)],config())
        self.assertIsNone(result["goodput_bps"])

    def test_mixed_modes_refused(self):
        self.assertTrue(analyze([event("generated",mode="reliable")],config())["issues"])

    def test_out_of_order_local_clock_is_detected(self):
        self.assertTrue(analyze([event("generated",t=100),event("tx_result",t=90)],config())["issues"])

    def test_console_noise_and_unknown_schema(self):
        rows,counts=parse_lines(["boot log",'{"schema":"vendor"}',json.dumps(event("generated")),"{broken"])
        self.assertEqual(len(rows),1)
        self.assertEqual(counts,{"ignored_non_schema_lines":2,"malformed_json_lines":1})

    def test_oversized_serial_line_rejected(self):
        with self.assertRaises(ValueError): parse_lines(["x"*16385])

    def test_duplicate_keys_and_nan_are_not_valid_json_evidence(self):
        for line in ['{"schema":"ann.serial.v1","seq":1,"seq":2}',
                     '{"schema":"ann.serial.v1","t_us":NaN}']:
            with self.subTest(line=line):
                rows,counts=parse_lines([line])
                self.assertEqual(rows,[])
                self.assertEqual(counts["malformed_json_lines"],1)

    def test_H_capture_envelope_and_host_tx_exclusion(self):
        lines=[json.dumps(dict(direction="device_rx",event=event("generated"),evidence_kind="synthetic")),
               json.dumps(dict(direction="host_tx",event=event("generated"),evidence_kind="synthetic"))]
        rows,counts=parse_lines(lines)
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]["_capture_evidence_kind"],"synthetic")
        self.assertEqual(counts["ignored_non_schema_lines"],1)

    def test_synthetic_capture_cannot_be_promoted_to_measured(self):
        rows,_=parse_lines([json.dumps(dict(direction="device_rx",event=event("generated"),evidence_kind="synthetic"))])
        with self.assertRaises(ValueError):analyze(rows,config(evidence_kind="hardware_measured"))

    def test_no_generated_denominator_has_no_pdr(self):
        result=analyze([],config())
        self.assertIsNone(result["pdr"])
        self.assertIsNone(result["rtt_p95_ms"])
        self.assertIsNone(result["range_m"])
        self.assertIsNone(result["rf_retry_count"])
        self.assertIsNone(result["airtime_us"])


class HardwareRecordTests(unittest.TestCase):
    def setUp(self):
        self.record=dict(status="not_measured",reason="hardware_not_available",source=None,
                         range_m=None,pdr=None,goodput_bps=None,rtt_p95_ms=None)

    def test_unavailable_record_remains_null(self):
        validate_measurement_record(self.record)

    def test_unavailable_cannot_contain_numeric_metrics(self):
        for key in ["range_m","pdr","goodput_bps","rtt_p95_ms"]:
            row=copy.deepcopy(self.record); row[key]=0
            with self.subTest(key=key),self.assertRaises(ValueError): validate_measurement_record(row)

    def test_fixture_cannot_enter_hardware_registry(self):
        row=dict(status="measured",evidence_kind="synthetic",source="fixture.log",pdr=.5)
        with self.assertRaises(ValueError): validate_measurement_record(row,require_hardware=True)

    def test_measured_requires_source(self):
        with self.assertRaises(ValueError): validate_measurement_record(dict(status="measured"))

    def test_invalid_measured_values(self):
        for value in [True,-1,float("nan"),float("inf"),1.1]:
            with self.subTest(value=value),self.assertRaises(ValueError):
                validate_measurement_record(dict(status="measured",source="actual",pdr=value))
