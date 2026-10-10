"""Shared demo and evaluation roof template lookup."""
import json
from .config import ROOT
from .models import GzError, project_id


def catalog(all=False, *, root=ROOT, mine=True):
    from . import park_store
    with park_store.transaction(root):
        park_store.recover(root)
        return _catalog(all, root=root, mine=mine)


def catalog_data(all=False, *, root=ROOT, mine=True):
    """Return detached JSON snapshots, not paths that outlive a publication lock."""
    from .park_store import transaction
    with transaction(root):
        return {key: (path, json.loads(path.read_text(encoding='utf-8')))
                for key, path in catalog(all, root=root, mine=mine).items()}


def read_template(identifier, *, root=ROOT):
    from .park_store import transaction
    with transaction(root):
        return json.loads(resolve(identifier, root=root).read_text(encoding='utf-8'))


def _catalog(all=False, *, root=ROOT, mine=True):
    paths = {}
    folders = [root / 'data/demo/projects', root / 'data/roofs', *([root / 'data/my-roofs'] if mine else [])]
    for park in sorted((root / 'data/parks').glob('*/roofs')):
        if park.parent.name.startswith('.'):
            continue
        if not park.resolve().is_relative_to((root / 'data/parks').resolve()):
            raise GzError('TEMPLATE_PATH_INVALID', '园区模板路径超出目录', '移除目录链接')
        folders.append(park)
    for folder in folders:
        for path in sorted(folder.glob("*/project.json")):
            identifier = project_id(path.parent.name)
            if identifier in paths:
                raise GzError("TEMPLATE_DUPLICATE", "屋顶模板编号重复", "演示和测试屋顶必须使用不同编号：" + identifier)
            if not path.resolve().is_relative_to(folder.resolve()):
                raise GzError("TEMPLATE_PATH_INVALID", "屋顶模板路径超出目录", "移除指向模板目录外的链接")
            paths[identifier] = path
    return {key: path for key, path in paths.items()
            if all or json.loads(path.read_text(encoding="utf-8")).get("collection") in (None, "real")}


def resolve(identifier, *, root=ROOT):
    """Path lookup; hold transaction(root) through copying files, or use read_template."""
    paths = catalog(all=True, root=root)
    identifier = project_id(identifier)
    if identifier not in paths:
        raise GzError("TEMPLATE_NOT_FOUND", "屋顶模板不存在", "可用模板：" + "、".join(list(paths)[:10]))
    return paths[identifier]
