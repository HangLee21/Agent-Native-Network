"""Empty UI mode. Never creates simulated boards or sends traffic."""
from .application import NoWirelessPath
from .protocol import MAX_PAYLOAD


class OfflineLink:
    def attach(self, callback, pc_id, pc_boot):
        pass

    def status(self):
        return dict(connected=False, entries=[], last_selected=None,
                    max_payload_bytes=MAX_PAYLOAD, entry_selection='dynamic_multi_entry',
                    status='no_wireless_path', host_planner_used=False)

    def select(self, dst):
        raise NoWirelessPath('offline UI mode; no wireless entry registered')

    def send(self, record):
        raise NoWirelessPath('offline UI mode')

    def close(self):
        pass
