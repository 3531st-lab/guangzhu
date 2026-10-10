"""Fixed first-party AGH management DTOs; no profiles, credentials or model calls."""
import hashlib
import json
from pathlib import Path
import stat
import re
import time
import uuid
from urllib.request import Request, urlopen
from .config import AGH_ORIGIN, AGH_PORT

TOOLS = ['gz_project_summary', 'gz_set_requirements', 'gz_fetch_weather', 'gz_generate_layout', 'gz_analyze',
         'gz_edit_design', 'gz_compare_options', 'gz_crosscheck_yield', 'gz_record_review', 'gz_export', 'gz_new_project', 'gz_wait']
PERMISSIONS = dict(zip(['create', 'update', 'trust', 'disable', 'enable', 'reconnect'],
                       ['mcp.manage', 'mcp.manage', 'mcp.trust', 'mcp.activate', 'mcp.activate', 'mcp.reconnect']))
READS = {'resources': {'mcp/list', 'mcp/get', 'mcp/status', 'mcp/tools', 'skills/list', 'skills/get', 'operations/get'},
         'plugins': {'list', 'operation/get'}}
WRITES = {'resources': {*('mcp/' + name for name in PERMISSIONS), 'skills/refresh', 'skills/trust', 'skills/desired'},
          'plugins': {'inspect', 'install', 'update', 'trust', 'enable'}}


class NotReady(ValueError):
    pass


def regular(path):
    path = Path(path).absolute()
    for item in (path, *path.parents):
        if item.is_symlink() or item.exists() and getattr(item.lstat(), 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise ValueError('目录包含链接或重解析点，请选择普通目录')
    return path.resolve(strict=True)


def scope(home):
    values = [str(regular(home)), 'local-dev', str(regular(Path(home) / 'data'))]
    return 'sha256-' + hashlib.sha256(json.dumps(values, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def transport(surface, action, body=None):
    payload = None if body is None else json.dumps(body, ensure_ascii=False).encode()
    request = Request(f'{AGH_ORIGIN}/admin/{surface}/api/{action}', data=payload,
                      headers={'Origin': AGH_ORIGIN, 'Host': f'127.0.0.1:{AGH_PORT}', 'Content-Type': 'application/json'})
    with urlopen(request, timeout=3) as response:
        return json.load(response)


class Management:
    def __init__(self, home, log, send=transport):
        self.home, self.log, self.send = Path(home), log, send
        self.contexts = {}

    def call(self, surface, action, body=None):
        if action != 'context' and action not in READS[surface] | WRITES[surface]:
            raise ValueError('管理动作不在允许列表')
        for attempt in range(2):
            try:
                result = self.send(surface, action, body)
                if not isinstance(result, dict) or 'error' in result and action not in {'operation/get', 'operations/get'}:
                    self.log(dict(surface=surface, action=action, result='rejected', command=(body or {}).get('commandId')))
                    raise ValueError('官方管理接口拒绝动作')
                error = result.get('lastSafeError', result.get('error', {}))
                code = error.get('code', '')
                self.log(dict(surface=surface, action=action, args=sorted(body or {}), operation=result.get('operationId'),
                              state=result.get('state'), command=(body or {}).get('commandId'),
                              error_code=code if re.fullmatch('[A-Z][A-Z0-9_]{0,63}', code) else None))
                return result
            except OSError:
                self.log(dict(surface=surface, action=action, result='transport-unconfirmed', attempt=attempt + 1))
                if attempt:
                    raise ValueError(f'无法连接 AGH 管理接口（端口 {AGH_PORT}）') from None

    def identity(self):
        expected = scope(self.home)
        for surface, prefix in [('resources', 'resource-admin-web-'), ('plugins', 'admin-web-')]:
            context = self.call(surface, 'context')
            if context.get('profile') != 'local-dev' or context.get('clientId') != prefix + expected:
                raise ValueError('实例与所选目录不一致，或使用了非默认配置；请核对实例目录')
            if self.contexts and surface in self.contexts and self.contexts[surface] != context:
                raise ValueError('配置期间实例身份或权限发生变化，请重新开始')
            self.contexts[surface] = context

    def read(self, surface, action, **values):
        return self.call(surface, action, dict(profile='local-dev', **values))

    def write(self, surface, action, **values):
        self.identity()
        context = self.contexts[surface]
        permission = PERMISSIONS[action.split('/')[1]] if action.startswith('mcp/') else {
            'skills/refresh': 'skills.refresh', 'skills/trust': 'skills.trust', 'skills/desired': 'resources.skills.write',
            'inspect': 'packages.read', 'install': 'packages.install', 'update': 'packages.install',
            'trust': 'packages.trust', 'enable': 'packages.activate'}[action]
        if context.get('readOnly') is not False or permission not in context.get('permissions', []):
            raise ValueError('实例未授予配置权限，请在官方管理界面处理')
        receipt = self.call(surface, action, dict(profile='local-dev', clientId=context['clientId'],
                                                commandId='setup-' + uuid.uuid4().hex, **values))
        for _ in range(60):
            result = self.read(surface, 'operations/get' if surface == 'resources' else 'operation/get',
                               operationId=receipt['operationId'])
            if result.get('state') == ('succeeded' if surface == 'resources' else 'completed'):
                return result
            if result.get('state') in {'failed', 'cancelled', 'rolled-back', 'succeeded', 'completed'}:
                raise ValueError('官方动作未成功：' + action + '；请查看官方管理界面后重试')
            time.sleep(.2)
        raise ValueError('官方动作未确认完成：' + action + '；请检查实例后重试')

    def pages(self, surface, action, **values):
        rows, catalogs = [], set()
        for _ in range(100):
            page = self.read(surface, action, **values)
            if any(root.get('rootKey') == 'workspace-agnes' and root.get('state') in {'stale', 'unavailable'}
                   for root in page.get('skillRoots', [])):
                raise ValueError('Skill目录扫描不可用，请检查安装工作区')
            rows.extend(page['items'])
            catalogs.add(page.get('catalogRevision'))
            if not page.get('nextCursor'):
                return rows, catalogs
            values['cursor'] = page['nextCursor']
        raise ValueError('官方资源列表分页未完成')

    def mcp(self, definition, configure=False):
        rows, _ = self.pages('resources', 'mcp/list')
        exists = any(row.get('serverId') == 'guangzhu' for row in rows)
        get = lambda: self.read('resources', 'mcp/get', serverId='guangzhu')
        changed = exists and get()['definition'] != definition
        if configure:
            if exists and not changed:
                try:
                    self.mcp(definition)
                    return
                except NotReady:
                    pass
            if not exists:
                self.write('resources', 'mcp/create', definition=definition)
            actions = ['disable', 'update', 'trust', 'enable', 'reconnect'] if changed else ['trust', 'enable'] + (['reconnect'] if exists else [])
            for action in actions:
                row = get()
                if not changed and (action == 'trust' and row['trust'] == 'trusted'
                    or action == 'enable' and row['actual'] == 'ready' and row['desired'] == 'enabled'):
                    continue
                args = dict(serverId='guangzhu', expectedRevision=row['revision'])
                if action == 'update':
                    args['definition'] = definition
                if action == 'trust':
                    args['trust'] = 'trusted'
                self.write('resources', 'mcp/' + action, **args)
        row = get()
        status = self.read('resources', 'mcp/status', serverId='guangzhu')
        tools, catalogs = self.pages('resources', 'mcp/tools', serverId='guangzhu')
        if (row['definition'] != definition or row['trust'] != 'trusted' or row['desired'] != 'enabled' or row['actual'] != 'ready'
                or status.get('connectionState') != 'ready' or status.get('observedRevision') != row['revision']
                or status.get('toolCount') != 12 or catalogs != {status.get('catalogRevision')}
                or len(tools) != 12 or {tool['name'] for tool in tools} != set(TOOLS)):
            raise NotReady('光筑12个工具尚未全部就绪，请查看官方MCP管理界面')

    def plugin(self, package, source=None):
        if source:
            preview = self.write('plugins', 'inspect', source=source)['preview']
            if (preview.get('id') != package['name'] or preview.get('version') != package['version'] or preview.get('blockers') != []
                    or not re.fullmatch('sha256-[a-f0-9]{64}', preview.get('integrity', ''))
                    or not re.fullmatch('[a-f0-9]{64}', preview.get('capabilityHash', '')) or preview.get('license') != package['license']
                    or {(row.get('rowId'), row.get('path')) for row in preview.get('contributions', [])}
                    != {(row['rowId'], row['path']) for row in package['agnes']['clientDescriptors']}
                    or any(row['kind'] != 'client' for row in preview.get('contributions', []))):
                raise ValueError('插件来源检查未通过，请核对所选启动工作区')
        rows = self.read('plugins', 'list')['packages']
        row = next((row for row in rows if row['id'] == package['name']), {})
        if source:
            integrity = preview['integrity']
            if row.get('integrity') != integrity or row.get('version') != package['version']:
                self.write('plugins', 'update' if row else 'install', source=source, expectedIntegrity=integrity,
                           **({'id': package['name']} if row else {}))
            for action in ('trust', 'enable'):
                row = next(row for row in self.read('plugins', 'list')['packages'] if row['id'] == package['name'])
                if row['integrity'] != integrity:
                    raise ValueError('插件安装摘要发生变化，请重新开始')
                if (action == 'trust' and row.get('trusted') and row.get('capabilityHash') == preview['capabilityHash']
                        or action == 'enable' and row.get('actual') == 'running' and row.get('desired') == 'enabled'):
                    continue
                values = dict(expectedIntegrity=integrity, capabilityHash=preview['capabilityHash']) if action == 'trust' else {
                    'expectedInstalledIntegrity': integrity}
                self.write('plugins', action, id=package['name'], **values)
            row = next(row for row in self.read('plugins', 'list')['packages'] if row['id'] == package['name'])
        if (row.get('version') != package['version'] or row.get('trusted') is not True or row.get('desired') != 'enabled'
                or row.get('actual') != 'running' or row.get('blockers') != [] or not row.get('integrity')
                or row.get('actualIntegrity', row['integrity']) != row['integrity']
                or row.get('actualVersion', row['version']) != row['version']
                or source and (row['integrity'] != preview['integrity'] or row.get('capabilityHash') != preview['capabilityHash'])):
            raise ValueError('光筑插件尚未运行或版本不匹配，请查看官方插件管理界面')
        return row['integrity']

    def skill(self, workspace, configure=False):
        if configure:
            self.write('resources', 'skills/refresh', workspaceId=workspace, rootKey='workspace-agnes')
        rows, _ = self.pages('resources', 'skills/list', kind='skill', workspaceId=workspace)
        matches = [row for row in rows if row.get('workspaceId') == workspace and row['name'] == 'pv-rooftop-design'
                   and row.get('sourceIdentity', {}).get('rootKey') == 'workspace-agnes' and row.get('resolution', {}).get('winner')]
        if len(matches) != 1:
            raise ValueError('安装工作区的光筑Skill不可用，请核对工作区')
        for action, values in ([('trust', dict(trust='trusted')), ('desired', dict(state='enabled'))] if configure else []):
            row = self.read('resources', 'skills/get', resourceId=matches[0]['resourceId'])
            if row.get('workspaceId') != workspace or row.get('sourceIdentity', {}).get('rootKey') != 'workspace-agnes':
                raise ValueError('Skill来源发生变化，请重新核对工作区')
            self.write('resources', 'skills/' + action, resourceId=row['resourceId'], expectedRevision=row['revision'], **values)
        row = self.read('resources', 'skills/get', resourceId=matches[0]['resourceId'])
        if (row.get('workspaceId') != workspace or row.get('stale') is not False or not row.get('resolution', {}).get('winner')
                or row['trust'] != 'trusted' or row['desired'] != 'enabled' or row['actual'] != 'ready'):
            raise ValueError('安装工作区的光筑Skill尚未就绪')

