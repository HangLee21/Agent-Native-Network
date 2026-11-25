"""E1-026 position_set v1 validation. This module never opens a port."""
import math
import secrets

FIELDS = {'position_boot', 'position_seq', 'source', 'fix', 'age_ms', 'lat', 'lon', 'accuracy_m'}


def validate_position(fields):
    if not isinstance(fields, dict) or set(fields) != FIELDS:
        raise ValueError('position_set requires exactly ' + '/'.join(sorted(FIELDS)))
    for key in ('position_boot', 'position_seq'):
        if type(fields[key]) is not int or not 1 <= fields[key] <= 0xffffffff:
            raise ValueError('nonzero uint32 ' + key + ' required')
    if type(fields['age_ms']) is not int or not 0 <= fields['age_ms'] <= 60000:
        raise ValueError('position age_ms must be 0..60000')
    if fields['source'] not in ('gnss', 'simulated', 'unavailable') or type(fields['fix']) is not bool:
        raise ValueError('invalid position source/fix')
    if not fields['fix']:
        if any(fields[k] is not None for k in ('lat', 'lon', 'accuracy_m')):
            raise ValueError('no fix requires null coordinates/accuracy')
    else:
        if fields['source'] == 'unavailable':
            raise ValueError('unavailable cannot have a fix')
        for key, low, high in [('lat', -90, 90), ('lon', -180, 180), ('accuracy_m', 0, 1000000)]:
            value = fields[key]
            if key == 'accuracy_m' and value is None:
                continue
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
                raise ValueError('invalid ' + key)
    return dict(fields)


class PositionStream:
    """One Pi process epoch, independent from board boot and radio business seq."""
    def __init__(self):
        self.boot = secrets.randbelow(0xffffffff) + 1
        self.seq = 0

    def encode(self, view):
        if self.seq == 0xffffffff:
            raise ValueError('position sequence exhausted; restart provider epoch')
        self.seq += 1
        valid = view is not None and view.get('valid', True) and not view.get('stale', False)
        source = 'unavailable' if view is None else 'simulated' if view['source'] == 'simulated' else 'gnss'
        return validate_position(dict(position_boot=self.boot, position_seq=self.seq, source=source,
                                      fix=bool(valid), age_ms=min(60000, int(view['age_ms'])) if view else 0,
                                      lat=view['lat'] if valid else None, lon=view['lon'] if valid else None,
                                      accuracy_m=view.get('accuracy_m') if valid else None))
