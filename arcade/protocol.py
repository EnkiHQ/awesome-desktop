"""JSON lines and table snapshots for a host-authoritative match.

Positions are fractions of the table bounds and speeds are fractions of the
table height, so a guest with a different resolution still draws the same shot.
Only the host steps the simulation.
"""
import json


def dumps(message):
    return (json.dumps(message, ensure_ascii=False, separators=(',', ':')) + '\n').encode('utf-8')


def loads(line):
    if isinstance(line, bytes):
        line = line.decode('utf-8')
    return json.loads(line)


def _span(table):
    left, top, right, bottom = table.bounds
    return left, top, right - left, bottom - top


def capture(table):
    """Serialize the balls the guest needs to draw this frame."""
    left, top, width, height = _span(table)
    bodies = []
    for body in table.bodies:
        bodies.append([
            round((body.x - left) / width, 5),
            round((body.y - top) / height, 5),
            round(body.vx / height, 5),
            round(body.vy / height, 5),
            round(body.angle, 4),
            round(body.impact, 4),
        ])
    exits = []
    for index, (x, y, tx, ty, age) in table.exits.items():
        exits.append([
            index,
            round((x - left) / width, 5),
            round((y - top) / height, 5),
            round((tx - left) / width, 5),
            round((ty - top) / height, 5),
            round(age, 4),
        ])
    return {
        't': 'snap',
        'state': table.state,
        'aim': [round(table.aim[0], 5), round(table.aim[1], 5)],
        'charge': round(table.charge, 4),
        'power': round(table.power / height, 5),
        'stroke': round(table.stroke, 4),
        'shots': table.shots,
        'sunk': sorted(table.sunk),
        'bodies': bodies,
        'exits': exits,
        'round': table.round_serial,
        'clock': round(table.clock, 4),
        'break': table.break_shot,
        'white_sunk': table.white_sunk,
        'first': None if table.first_shot_at is None else round(table.first_shot_at, 4),
        'finished': None if table.finished_at is None else round(table.finished_at, 4),
    }


def apply_snapshot(table, snap):
    """Copy a host snapshot onto this table. The caller must not step afterwards."""
    if len(snap['bodies']) != len(table.bodies):
        raise ValueError('两边的图标数量不一致')
    if snap.get('round') != table.round_serial:
        table.reset()
        table.round_serial = snap['round']
    left, top, width, height = _span(table)
    for body, (u, v, vx, vy, angle, impact) in zip(table.bodies, snap['bodies']):
        body.x = left + u * width
        body.y = top + v * height
        body.vx = vx * height
        body.vy = vy * height
        body.angle = angle
        body.impact = impact
    table.state = snap['state']
    table.aim = (snap['aim'][0], snap['aim'][1])
    table.charge = snap['charge']
    table.power = snap['power'] * height
    table.stroke = snap['stroke']
    table.shots = snap['shots']
    table.sunk = set(snap['sunk'])
    table.white_sunk = bool(snap['white_sunk'])
    table.break_shot = bool(snap['break'])
    table.clock = snap['clock']
    table.first_shot_at = snap['first']
    table.finished_at = snap['finished']
    exits = {}
    for index, u, v, tu, tv, age in snap['exits']:
        exits[index] = (left + u * width, top + v * height, left + tu * width, top + tv * height, age)
    table.exits = exits
    table.poses = table._poses()


def world_point(table, u, v):
    left, top, width, height = _span(table)
    return left + u * width, top + v * height
