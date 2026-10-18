"""Plugin build exports only bridge constants and complete roof geometry."""
import importlib.util
import json
from pathlib import Path
import pytest
from guangzhu.config import ROOT
from guangzhu.templates import catalog, resolve

spec = importlib.util.spec_from_file_location('build_agh_plugin', ROOT / 'scripts/build_agh_plugin.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def test_geometry_exports_every_template_zone_without_losing_circle_or_polygon():
    data = builder.make_data()
    assert set(data) == {'templates', 'toolPrefix', 'desktopOrigins'}
    assert data['desktopOrigins'] == ['http://127.0.0.1:8765', 'http://127.0.0.1:8766']
    legacy_ids = {'changzhou-demo', 'l-shape', 'metal-demo-n', 'metal-demo-s', 'rotated', 'south-tower'}
    legacy_ids |= {f't12-{group}-{number:02d}' for group, count in [('boundary', 6), ('impossible', 6), ('real', 12)]
                   for number in range(1, count + 1)}
    pitched_ids = {'pitched-gable-demo', 'pitched-saw-demo'}
    installation_ids = {'ground-demo', 'carport-demo'}
    livestock_ids = {'grazing-demo', 'barn-demo'}
    assert len(legacy_ids) == 30 and len(pitched_ids) == 2
    assert {row['id'] for row in data['templates']} == set(catalog(all=True)) == legacy_ids | pitched_ids | installation_ids | livestock_ids
    assert len(data['templates']) == 36
    for template in data['templates']:
        roof = json.loads(resolve(template['id']).read_text(encoding='utf8'))['roof']
        for key in ('outline', 'obstacles', 'keepouts'):
            assert template[key] == roof[key]


@pytest.mark.parametrize('origin', ['*', 'https://example.com', 'http://localhost:8765', 'http://127.0.0.1:8765/',
                                  'http://user:secret@127.0.0.1:8765', 'http://127.0.0.1:8765?token=secret'])
def test_build_rejects_nonlocal_or_ambiguous_origins(origin):
    with pytest.raises(ValueError):
        builder.make_data(desktop_origins=['http://127.0.0.1:8766', origin])


def test_build_constants_do_not_embed_backend_prompts_or_economics():
    data = builder.make_data('mcp_other_123_', ['http://127.0.0.1:8888'])
    assert data['toolPrefix'] == 'mcp_other_123_'
    assert data['desktopOrigins'] == ['http://127.0.0.1:8888']
    assert all(set(row) == {'id', 'name', 'outline', 'obstacles', 'keepouts'} for row in data['templates'])


def test_skin_assets_obey_official_allowlist_and_licenses_are_bundled_separately():
    skin = json.loads((builder.PLUGIN / 'extensions/main/skins/agnes.client.json').read_text(encoding='utf-8'))['skins'][0]
    assert skin['name'] == '光筑'
    assets = builder.PLUGIN / 'extensions/main/skins/guangzhu/assets'
    allowed = {'.webp', '.png', '.jpg', '.jpeg', '.avif', '.woff2', '.woff'}
    assert all(path.suffix in allowed for path in assets.rglob('*') if path.is_file())
    for name in ('LICENSE-IBM-Plex.txt', 'LICENSE-Noto-Serif-SC.txt', 'LICENSE-OSM.md'):
        assert (builder.PLUGIN / 'licenses' / name).is_file()


def test_release_is_repeatable_runtime_only_and_keeps_both_font_licenses(tmp_path):
    release = builder.release(tmp_path)
    assert builder.release(tmp_path) == release
    assert sorted(path.name for path in release.iterdir()) == ['extensions', 'index.mjs', 'licenses', 'package.json']
    metadata = json.loads((release / 'package.json').read_text(encoding='utf-8'))
    assert 'devDependencies' not in metadata and 'scripts' not in metadata
    assert metadata['agnes'] == json.loads((builder.PLUGIN / 'package.json').read_text(encoding='utf-8'))['agnes']
    for source in (builder.PLUGIN / 'extensions').rglob('*'):
        if source.is_file(): assert (release / source.relative_to(builder.PLUGIN)).read_bytes() == source.read_bytes()
    for notice in ('LICENSE-IBM-Plex.txt', 'LICENSE-Noto-Serif-SC.txt', 'LICENSE-guangzhu.txt'):
        assert (release / 'licenses' / notice).read_bytes() == (builder.PLUGIN / 'licenses' / notice).read_bytes()
    assert (release / 'licenses/LICENSE-guangzhu.txt').read_bytes() == (ROOT / 'LICENSE').read_bytes()
