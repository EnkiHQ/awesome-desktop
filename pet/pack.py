"""Character packs: a body picture per facing plus where the arms attach.

A pack is a folder with ``pet.json`` and one transparent PNG per facing. The
body pictures have no arms; the arms are drawn from the shoulder points so the
character can reach the keyboard and the mouse.
"""
import json
import shutil
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from .paths import builtin_dir, pets_dir

FACINGS = ('front', 'back')


@dataclass
class View:
    image: Path
    size: tuple
    shoulders: list
    arm: float
    line: float
    desk: float = None
    eyes: list = field(default_factory=list)


@dataclass
class Pack:
    name: str
    title: str
    skin: str
    outline: str
    views: dict
    root: Path


def find(name):
    candidate = Path(str(name)).expanduser()
    if candidate.is_dir() and (candidate / 'pet.json').is_file():
        return candidate
    for base in (pets_dir(), builtin_dir()):
        path = base / str(name)
        if (path / 'pet.json').is_file():
            return path
    raise FileNotFoundError(f'找不到形象 {name}')


def load(name='default'):
    root = find(name)
    data = json.loads((root / 'pet.json').read_text(encoding='utf-8'))
    views = {}
    for facing, spec in data.get('views', {}).items():
        image = root / spec['image']
        size = tuple(spec.get('size') or _image_size(image))
        views[facing] = View(
            image=image,
            size=size,
            shoulders=[tuple(p) for p in spec['shoulders']],
            arm=float(spec['arm']),
            line=float(spec.get('line', max(2.0, spec['arm'] * 0.18))),
            desk=float(spec['desk']) if spec.get('desk') is not None else None,
            eyes=[tuple(e) for e in spec.get('eyes', [])],
        )
    if 'front' not in views:
        raise ValueError(f'{root} 缺少正面 front')
    return Pack(
        name=data.get('name', root.name),
        title=data.get('title', data.get('name', root.name)),
        skin=data.get('skin', '#F4C7AE'),
        outline=data.get('outline', '#151515'),
        views=views,
        root=root,
    )


def available():
    seen = {}
    for base in (builtin_dir(), pets_dir()):
        if not base.is_dir():
            continue
        for path in sorted(base.iterdir()):
            meta = path / 'pet.json'
            if meta.is_file():
                try:
                    data = json.loads(meta.read_text(encoding='utf-8'))
                except ValueError:
                    continue
                seen[path.name] = data.get('title', path.name)
    return seen


def _image_size(path):
    from PIL import Image

    with Image.open(path) as image:
        return image.size


def key_out(source):
    """Remove a flat green background and crop to the character."""
    import numpy as np
    from PIL import Image, ImageFilter

    rgb = np.asarray(Image.open(source).convert('RGB')).astype(np.int16)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    spill = g - np.maximum(r, b)
    alpha = np.clip((70 - spill) / 40.0, 0.0, 1.0)
    alpha[g < 60] = 1.0
    g = np.where(spill > 0, np.maximum(r, b), g)
    out = np.dstack([r, g, b, np.round(alpha * 255)]).clip(0, 255).astype(np.uint8)
    image = Image.fromarray(out, 'RGBA')
    mask = image.getchannel('A').point(lambda v: 255 if v > 128 else 0)
    box = mask.filter(ImageFilter.MinFilter(5)).filter(ImageFilter.MaxFilter(5)).getbbox()
    if not box:
        raise ValueError(f'{source} 里没有找到人物，背景要是纯绿色')
    pad = 6
    box = (max(0, box[0] - pad), max(0, box[1] - pad),
           min(image.width, box[2] + pad), min(image.height, box[3] + pad))
    return image.crop(box)


def guess(image):
    """Guess shoulders, arm width, outline width and the desk line from the silhouette."""
    import numpy as np

    rgba = np.asarray(image)
    solid = rgba[..., 3] > 128
    height, width = solid.shape
    rows = np.where(solid.any(axis=1))[0]
    cols = np.where(solid.any(axis=0))[0]
    top, bottom = int(rows[0]), int(rows[-1])
    center = int(round((cols[0] + cols[-1]) / 2))
    span = bottom - top

    def run(y):
        line = solid[y]
        x = center
        if not line[x]:
            near = np.where(line[max(0, center - width // 10):center + width // 10])[0]
            if not len(near):
                return None
            x = int(near[np.argmin(abs(near + max(0, center - width // 10) - center))]) + max(0, center - width // 10)
        left = x
        while left > 0 and line[left - 1]:
            left -= 1
        right = x
        while right < width - 1 and line[right + 1]:
            right += 1
        return left, right

    widths = np.zeros(height)
    for y in range(top, bottom + 1):
        edges = run(y)
        if edges:
            widths[y] = edges[1] - edges[0] + 1
    smooth = np.convolve(widths, np.ones(5) / 5, mode='same')
    head_y = top + int(np.argmax(smooth[top:top + int(span * 0.65)]))
    lo = head_y + int(span * 0.05)
    hi = min(bottom, head_y + int(span * 0.45))
    band = np.where(smooth[lo:hi] > 0, smooth[lo:hi], np.inf)
    neck = lo + int(np.argmin(band))
    shoulder_y = min(bottom, neck + max(2, int(span * 0.02)))
    left, right = run(shoulder_y) or (center - span // 10, center + span // 10)
    torso = right - left

    dark = (rgba[..., :3].astype(np.int16).sum(axis=2) < 160) & solid
    runs = []
    for y in range(shoulder_y + int(span * 0.02), min(bottom, shoulder_y + int(span * 0.1)), 2):
        xs = np.where(solid[y])[0]
        if not len(xs):
            continue
        n = 0
        x = xs[0]
        while x < width and dark[y, x]:
            n += 1
            x += 1
        if 1 <= n <= torso * 0.2:
            runs.append(n)
    line = float(np.median(runs)) if runs else max(2.0, torso * 0.05)

    return {
        'shoulders': [[int(left), int(shoulder_y)], [int(right), int(shoulder_y)]],
        'arm': round(torso * 0.27, 1),
        'line': round(min(line, torso * 0.09), 1),
        'desk': int(shoulder_y + torso * 0.75),
        'neck': int(neck),
        'top': int(top),
    }


def _component(mask, seeds):
    """Pixels of ``mask`` connected to any seed (4-neighbour flood fill)."""
    import numpy as np

    height, width = mask.shape
    out = np.zeros_like(mask)
    stack = [s for s in seeds if mask[s]]
    for s in stack:
        out[s] = True
    while stack:
        y, x = stack.pop()
        for ny, nx in ((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)):
            if 0 <= ny < height and 0 <= nx < width and mask[ny, nx] and not out[ny, nx]:
                out[ny, nx] = True
                stack.append((ny, nx))
    return out


def find_eyes(image, top, neck, line):
    """Return eye boxes and an eye-interior mask (pupil, iris, white) for blinking."""
    import numpy as np
    from PIL import Image, ImageFilter

    rgba = np.asarray(image).astype(np.int16)
    r, g, b, a = rgba[..., 0], rgba[..., 1], rgba[..., 2], rgba[..., 3]
    solid = a > 200
    head = np.zeros_like(solid)
    head[top:neck] = True
    black = solid & head & (np.maximum(np.maximum(r, g), b) < 60)
    size = max(5, int(line * 2) | 1)
    opened = Image.fromarray((black * 255).astype(np.uint8))
    opened = np.asarray(opened.filter(ImageFilter.MinFilter(size)).filter(ImageFilter.MaxFilter(size))) > 128
    blobs = []
    left = opened.copy()
    while left.any() and len(blobs) < 6:
        ys, xs = np.nonzero(left)
        part = _component(left, [(int(ys[0]), int(xs[0]))])
        left &= ~part
        py, px = np.nonzero(part)
        if len(py) >= size * size:
            blobs.append((len(py), part, py.mean(), px.mean(), py.max() - py.min() + 1))
    blobs.sort(key=lambda b: -b[0])
    pair = None
    for i in range(len(blobs)):
        for j in range(i + 1, len(blobs)):
            if abs(blobs[i][2] - blobs[j][2]) < max(blobs[i][4], blobs[j][4]):
                pair = (blobs[i], blobs[j])
                break
        if pair:
            break
    if not pair:
        return [], None
    eye_like = solid & head & (((r > 232) & (g > 232) & (b > 232)) | ((b > r + 30) & (b > 150)) | opened)
    boxes = []
    mask = np.zeros_like(solid)
    for blob in sorted(pair, key=lambda b: b[3]):
        ys, xs = np.nonzero(blob[1])
        part = _component(eye_like, list(zip(ys.tolist(), xs.tolist())))
        mask |= part
        py, px = np.nonzero(part)
        boxes.append([int(px.min()), int(py.min()), int(px.max()) + 1, int(py.max()) + 1])
    return boxes, mask


def skin_tone(image):
    import numpy as np

    rgba = np.asarray(image).astype(np.int16)
    r, g, b, a = rgba[..., 0], rgba[..., 1], rgba[..., 2], rgba[..., 3]
    pick = (a > 200) & (r > 195) & (g > 140) & (g < 238) & (b > 110) & (b < 225) \
        & (r > g) & (g > b - 12) & (r - b > 22) & (r - b < 115)
    if pick.sum() < 50:
        return '#F4C7AE'
    tone = [int(np.median(channel[pick])) for channel in (r, g, b)]
    return '#{:02X}{:02X}{:02X}'.format(*tone)


def make(name, front, back=None, title=None, dest=None):
    """Turn green-screen pictures into a pack folder and return its path."""
    root = Path(dest) if dest else pets_dir() / name
    root.mkdir(parents=True, exist_ok=True)
    import numpy as np
    from PIL import Image

    views = {}
    skin = None
    for facing, source in (('front', front), ('back', back)):
        if not source:
            continue
        image = key_out(source)
        image.save(root / f'{facing}.png')
        spec = guess(image)
        top, neck = spec.pop('top'), spec.pop('neck')
        spec.update(image=f'{facing}.png', size=list(image.size))
        if facing == 'back':
            spec.pop('desk', None)
        else:
            skin = skin_tone(image)
            boxes, mask = find_eyes(image, top, neck, spec['line'])
            if boxes:
                spec['eyes'] = boxes
                tone = [int(skin[i:i + 2], 16) for i in (1, 3, 5)]
                lids = np.zeros((image.height, image.width, 4), np.uint8)
                lids[..., :3] = tone
                lids[..., 3] = mask * 255
                Image.fromarray(lids, 'RGBA').save(root / 'lids.png')
        views[facing] = spec
    data = {'name': name, 'title': title or name, 'skin': skin or '#F4C7AE', 'outline': '#151515', 'views': views}
    (root / 'pet.json').write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    return root


def add(source):
    """Install a pack from a folder or a zip file."""
    source = Path(source).expanduser()
    if source.is_dir():
        name = json.loads((source / 'pet.json').read_text(encoding='utf-8')).get('name', source.name)
        target = pets_dir() / name
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(source, target)
        return target
    with zipfile.ZipFile(source) as archive:
        meta = next((n for n in archive.namelist() if n.endswith('pet.json')), None)
        if not meta:
            raise ValueError('压缩包里没有 pet.json')
        prefix = meta[:-len('pet.json')]
        name = json.loads(archive.read(meta).decode('utf-8')).get('name', source.stem)
        target = pets_dir() / name
        if target.exists():
            shutil.rmtree(target)
        target.mkdir(parents=True)
        for item in archive.namelist():
            if not item.startswith(prefix) or item.endswith('/'):
                continue
            relative = Path(item[len(prefix):])
            if relative.is_absolute() or '..' in relative.parts:
                continue
            out = target / relative
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(archive.read(item))
    return target


def export(name, out):
    root = find(name)
    out = Path(out).expanduser()
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(root.iterdir()):
            if path.is_file():
                archive.write(path, f'{root.name}/{path.name}')
    return out
