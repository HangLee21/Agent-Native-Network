"""Check normalized black-box core traces. Synthetic checker tests are not C tests."""
from collections import Counter


def check_trace(events, *, capacity):
    errors, delivered, completed, terminal, boots = [], Counter(), Counter(), {}, {}
    generated = set()
    for event in events:
        kind, identity = event["event"], tuple(event.get("identity",[]))
        if kind == "generated":
            if len(identity) != 3 or identity in generated:
                errors.append("invalid/repeated origin+boot+sequence")
            generated.add(identity)
        elif kind == "queue":
            if type(event["size"]) is not int or not 0 <= event["size"] <= capacity:
                errors.append("queue capacity exceeded")
        elif kind == "link_send":
            if identity in terminal:
                errors.append("retry after cancel/expiry/complete")
        elif kind == "link_delivered":
            if event.get("physical_link_available") is False:
                errors.append("successful transfer across unavailable physical link")
        elif kind == "delivered":
            if identity not in generated:
                errors.append("delivery without generation")
            # Core v1 makes no exactly-once claim across receiver reboot/expiry.
            key = (identity,event["destination"],event.get("receiver_boot_id"),event.get("dedup_epoch"))
            delivered[key] += 1
            if delivered[key] > 1:
                errors.append("duplicate application delivery")
            if event.get("path_valid") is False:
                errors.append("delivery across partition")
        elif kind == "complete":
            if terminal.get(identity) in {"cancel", "expired"}:
                errors.append("conflicting terminal completion after cancel/expiry")
            completed[identity] += 1
            if completed[identity] > 1:
                errors.append("duplicate completion from ACK")
            terminal[identity] = kind
        elif kind in {"cancel", "expired"}:
            terminal[identity] = kind
        elif kind == "reboot":
            if boots.get(event["node"]) == event["boot_id"]:
                errors.append("reboot reused boot identity")
            boots[event["node"]] = event["boot_id"]
    return errors
