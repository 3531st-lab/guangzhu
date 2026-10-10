"""Named parks and immutable source roofs, in metres east/north."""
import hashlib
import json
import math
import os
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
import shutil
import threading
import uuid

from pydantic import Field, field_validator, model_validator
from shapely import affinity
from shapely.geometry import Polygon

from .config import ROOT
from .models import Obstacle, ParkAssociation, Point2, Project, Record, project_id
from .templates import resolve, read_template

LOCK = threading.RLock()
HELD = set()
SCALE = math.pi * 6378137 / 180
FORM_FIELDS = set(('text keep notes maxRounds compare review exportOn prefer moduleId inverterBrand inverterId tiltMin tiltMax '
                   'payback budget capMin capMax walkway obstacle edge curtail transformer transformerShare maxHeight phaseKw phaseBudget '
                   'noExport parapetCap priceSelf selfUse capex priceExport fRoof fAge fCore fSky fOwned fKva fKwh fShifts fExport '
                   'loanRatio loanRate loanYears tariffClass posttaxPayback cleaningTimes refurbish '
                   'taxHoliday mechanismShare mechanismPrice mechanismYears greenSoldShare publicSubsidy subsidyYear').split())


@contextmanager
def transaction(root=ROOT):
    """Hold through consumption; the OS releases this lock if a publisher crashes."""
    key = os.path.normcase(str(root.resolve()))
    with LOCK:
        if key in HELD:
            yield
            return
        path = Path(tempfile.gettempdir()) / ('guangzhu-park-' + hashlib.sha256(key.encode()).hexdigest() + '.lock')
        with path.open('a+b') as handle:
            if os.name == 'nt':
                import msvcrt
                if path.stat().st_size == 0:
                    handle.write(b'0')
                    handle.flush()
                handle.seek(0)
                while True:
                    try:
                        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                        break
                    except OSError as error:
                        if error.errno not in (13, 36):
                            raise
                        time.sleep(.05)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            HELD.add(key)
            try:
                yield
            finally:
                HELD.remove(key)


class Building(Record):
    template: str
    x_m: float = Field(default=0.0, strict=True)
    y_m: float = Field(default=0.0, strict=True)
    rotation_deg: float = Field(default=0.0, ge=-360, le=360, strict=True)
    _template = field_validator('template')(project_id)


class Park(Record):
    id: str
    name: str = Field(min_length=1, max_length=100)
    buildings: list[Building] = Field(default_factory=list, max_length=100)
    transformer_kva: float | None = Field(default=None, gt=0, strict=True)
    grid_kw: float | None = Field(default=None, ge=0, strict=True)
    budget_cny: float | None = Field(default=None, ge=0, strict=True)
    origin: Point2 | None = None
    settings: dict[str, dict] = Field(default_factory=dict)
    _id = field_validator('id')(project_id)

    @model_validator(mode='after')
    def unique(self):
        if len({b.template for b in self.buildings}) != len(self.buildings):
            raise ValueError('每个来源屋顶只能加入一次')
        for building in self.buildings:
            project_id(self.id + '--' + building.template)
        for key, form in self.settings.items():
            if key not in {'shared', *(b.template for b in self.buildings)} or set(form) - FORM_FIELDS:
                raise ValueError('园区设置只能包含每栋公开条件')
            if any(not isinstance(v, (str, bool, int, float, list)) for v in form.values()):
                raise ValueError('园区设置不能保存账户或运行对象')
        if self.origin and not (-180 <= self.origin[0] <= 180 and -90 <= self.origin[1] <= 90):
            raise ValueError('园区地理原点超出经纬度范围')
        return self


def folder(identifier, root=ROOT):
    base = root / 'data/parks'
    path = base / project_id(identifier)
    if not base.resolve().is_relative_to(root.resolve()) or not path.resolve().is_relative_to(base.resolve()) or path.is_symlink():
        raise ValueError('园区路径超出目录')
    if path.exists() and any(p.is_symlink() for p in path.rglob('*')):
        raise ValueError('园区文件不允许链接到其他目录')
    return path


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name('.' + path.name + '-' + uuid.uuid4().hex)
    try:
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def load(identifier, root=ROOT):
    with transaction(root):
        recover(root)
        return Park.model_validate(read(folder(identifier, root) / 'park.json'))


def listing(root=ROOT):
    with transaction(root):
        recover(root)
        return [load(p.parent.name, root).model_dump() for p in sorted((root / 'data/parks').glob('*/park.json'))
                if not p.parent.name.startswith('.')]


def recover(root=ROOT):
    """A durable publication journal selects old data until the new directory exists."""
    with transaction(root):
        base = root / 'data/parks'
        for journal in base.glob('.publish-*.json'):
            publication = read(journal)
            target = folder(publication['id'], root)
            token = uuid.UUID(hex=publication['token']).hex
            staging, backup = base / ('.stage-' + token), base / ('.backup-' + token)
            if any(path.is_symlink() for path in (staging, backup, journal)):
                raise ValueError('园区发布事务不允许目录链接')
            if not target.exists():
                (backup if backup.exists() else staging).rename(target)
            for disposable in (staging, backup):
                if disposable.exists():
                    shutil.rmtree(disposable)
            journal.unlink()


def transform(points, building, inverse=False):
    angle = math.radians(building.rotation_deg) * (-1 if inverse else 1)
    c, s = math.cos(angle), math.sin(angle)
    result = []
    for x, y in points:
        if inverse:
            x, y = x - building.x_m, y - building.y_m
        u, v = c * x - s * y, s * x + c * y
        result.append([u, v] if inverse else [u + building.x_m, v + building.y_m])
    return result


def geographic(template, root=ROOT):
    """Match frozen raw OSM geometry, never the city's rounded site coordinates."""
    if not template.startswith('t12-real-'):
        return None
    outline = Polygon(read_template(template, root=root)['roof']['outline'])
    matches = []
    for element in read(root / 'data/roofs/osm-raw.json')['elements']:
        points = element.get('geometry', [])
        if len(points) < 4 or points[0] != points[-1]:
            continue
        lat = sum(p['lat'] for p in points[:-1]) / (len(points) - 1)
        lon = sum(p['lon'] for p in points[:-1]) / (len(points) - 1)
        east = SCALE * math.cos(math.radians(lat))
        raw = Polygon([((p['lon'] - lon) * east, (p['lat'] - lat) * SCALE) for p in points])
        if not raw.is_valid:
            continue
        shape = raw.simplify(.3, preserve_topology=True)
        center = shape.centroid
        local = affinity.translate(shape, -center.x, -center.y)
        if outline.hausdorff_distance(local) < .002:
            matches.append((lon + center.x / east, lat + center.y / SCALE))
    if len(matches) != 1:
        raise ValueError('真实屋顶没有唯一的原始坐标匹配')
    return matches[0]


def place(park, root=ROOT):
    park = park.model_copy(deep=True)
    positions = {b.template: geographic(b.template, root) for b in park.buildings}
    park.origin = park.origin or next((p for p in positions.values() if p), None)
    occupied = []
    for building in sorted(park.buildings, key=lambda b: positions[b.template] is None):
        source = Project.model_validate(read_template(building.template, root=root))
        location = positions[building.template]
        if location:
            lon, lat = park.origin
            building.x_m = (location[0] - lon) * SCALE * math.cos(math.radians(lat))
            building.y_m = (location[1] - lat) * SCALE
        else:
            east = max((shape.bounds[2] for shape in occupied), default=0) + 20
            shape = Polygon(transform(source.roof.outline, building))
            building.x_m += east - shape.bounds[0]
        occupied.append(Polygon(transform(source.roof.outline, building)))
    return park


def available_to_edit(path):
    queue = read(path / 'queue.json') if (path / 'queue.json').exists() else {}
    if any(item['status'] not in ('completed', 'failed', 'skipped') for item in queue.get('items', [])):
        raise ValueError('队列使用已冻结的园区模板，请先完成或跳过全部任务再修改园区')


def save(payload, root=ROOT):
    park = Park.model_validate(payload)
    with transaction(root):
        recover(root)
        target = folder(park.id, root)
        available_to_edit(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        token = uuid.uuid4().hex
        staging = target.parent / ('.stage-' + token)
        backup = target.parent / ('.backup-' + token)
        journal = target.parent / ('.publish-' + park.id + '.json')
        try:
            if target.exists():
                shutil.copytree(target, staging)
            else:
                staging.mkdir()
            roofs = staging / 'roofs'
            if roofs.exists():
                shutil.rmtree(roofs)
            if (staging / 'queue.json').exists():  # the finished batch was for the old buildings; the edited park starts a fresh one
                write(staging / 'queue.json', dict(revision=read(staging / 'queue.json').get('revision', 0) + 1, paused=False, items=[]))
            sources = {b.template: resolve(b.template, root=root) for b in park.buildings}
            projects = {key: Project.model_validate(read(path)) for key, path in sources.items()}
            if any(p.park for p in projects.values()):
                raise ValueError('加入原始屋顶，不要把园区副本再次加入')
            content = dict(buildings=[b.model_dump() for b in park.buildings], sources={key: read(path) for key, path in sources.items()})
            signature = hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()
            for building in park.buildings:
                original = projects[building.template]
                generated = original.model_copy(deep=True)
                generated.id = park.id + '--' + building.template
                generated.designs = []
                generated.park = ParkAssociation(id=park.id, template=building.template, snapshot=signature,
                                                x_m=building.x_m, y_m=building.y_m, rotation_deg=building.rotation_deg)
                for other in park.buildings:
                    neighbour = projects[other.template].roof
                    height = neighbour.height_m + neighbour.parapet_height_m - original.roof.height_m
                    if neighbour.type in ('pitched', 'carport') and neighbour.planes:
                        from .roofplane import plane_elevation
                        height += max(plane_elevation(p, xy) for p in neighbour.planes for xy in p.outline)
                    if other.template == building.template or height <= 0:
                        continue
                    points = transform(transform(neighbour.outline, other), building, inverse=True)
                    label = projects[other.template].name + ('（按最高安装面棱柱保守示意）' if neighbour.type == 'carport' else
                            '（按最高屋面棱柱保守示意）' if neighbour.type == 'pitched' else '')
                    generated.roof.surroundings.append(Obstacle(id='park-' + other.template, label=label,
                                                               kind='prism', height_m=height, footprint=points))
                destination = roofs / generated.id
                if generated.roof.underlay:
                    image = Path(generated.roof.underlay.image)
                    source = (sources[building.template].parent / image).resolve()
                    if image.is_absolute() or '..' in image.parts or not source.is_relative_to(sources[building.template].parent.resolve()):
                        raise ValueError('来源底图必须在屋顶模板目录内')
                    output = destination / 'underlay' / image.name
                    output.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, output)
                    generated.roof.underlay.image = 'underlay/' + image.name
                write(destination / 'project.json', Project.model_validate(generated.model_dump()).model_dump(by_alias=True))
            write(staging / 'park.json', park.model_dump())
            write(journal, dict(id=park.id, token=token))
            if target.exists():
                target.rename(backup)
            try:
                staging.rename(target)
            except OSError:
                if backup.exists():
                    backup.rename(target)
                raise
        finally:
            for disposable in (staging, *([backup] if target.exists() else [])):
                if disposable.exists():
                    shutil.rmtree(disposable)
            if target.exists() or not backup.exists():
                journal.unlink(missing_ok=True)
        return park.model_dump()


def delete(identifier, root=ROOT):
    with transaction(root):
        path = folder(identifier, root)
        available_to_edit(path)
        shutil.rmtree(path)


def demo(root=ROOT):
    park = Park(id='wujin-demo', name='武进某厂区（示意）',
                buildings=[Building(template='t12-real-' + n) for n in ('07', '09', '10', '11')])
    return save(place(park, root).model_dump(), root)
