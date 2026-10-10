"""T05 annual acceptance: real cached weather, POA energy and 500 modules."""

import json
from pathlib import Path
import time

import numpy as np
import pandas as pd
import pytest

from guangzhu.layout import generate_layout
from guangzhu.models import LayoutParams, validate_project
from guangzhu.shading import analyze_design
from guangzhu.solar import sun_position, poa_irradiance
from guangzhu.weather import load_nasa_hourly


def performance_fixture():
    payload=json.loads(Path('data/demo/projects/changzhou-demo/project.json').read_text(encoding='utf-8'))
    payload['roof']['outline']=[[0,0],[70,0],[70,44],[0,44]]
    project=validate_project(payload)
    design=generate_layout(project,LayoutParams())
    assert len(design.modules)>=500
    design.modules=design.modules[:500]
    return project,design


def test_500_module_annual_analysis_under_five_seconds_and_energy_balances():
    project,design=performance_fixture()
    started=time.perf_counter()
    result=analyze_design(project,design,offline=True)
    elapsed=time.perf_counter()-started
    assert elapsed<5
    assert len(result['modules'])==500
    losses=np.array([m['total_loss_pct'] for m in result['modules']])
    assert ((losses>=0)&(losses<=100)).all()
    for module in result['modules']:
        assert module['total_loss_pct']==pytest.approx(module['beam_loss_pct']+module['diffuse_loss_pct'])
    summary=result['summary']
    assert summary['avg_loss_pct']==pytest.approx(losses.mean())
    assert sum(summary['source_loss_pct'].values())==pytest.approx(losses.mean())
    assert sum(summary['source_loss_share_pct'].values())==pytest.approx(100)
    assert result['metadata']['representative_days']==12
    assert result['metadata']['daylight_hours']==144
    assert result['metadata']['weather_sha256']=='9acbf5c97ee291eab4bc0f23bc4bb325118979d9b4c60e693efac1137445cb3d'
    print('T05 500 modules:',json.dumps(dict(elapsed_seconds=elapsed,metadata=result['metadata'],summary=summary)))


def test_month_hour_weights_equal_explicit_hourly_energy_for_known_full_beam_mask(monkeypatch):
    import guangzhu.shading as shading
    project,design=performance_fixture()
    design.modules=design.modules[:1]
    monkeypatch.setattr(shading,'ray_hits',lambda scene,points,vector,owners: np.full(points.shape[:-1],'test-wall',dtype=object))
    result=analyze_design(project,design,offline=True)
    weather,_=load_nasa_hourly(project.site.lat,project.site.lon,2023,offline=True)
    poa=poa_irradiance(weather,sun_position(weather.index+pd.Timedelta(minutes=30),project.site.lat,project.site.lon),25,180)
    instants=pd.DatetimeIndex([pd.Timestamp(year=2023,month=m,day=15,hour=h,tz='UTC')+pd.Timedelta(minutes=30) for m in range(1,13) for h in range(24)])
    daylight={ (t.month,t.hour):e>0 for t,e in zip(instants,sun_position(instants,31.81,119.97).elevation) }
    beam_lost=sum(value for t,value in poa.poa_direct.items() if daylight[(t.month,t.hour)])
    assert result['modules'][0]['beam_loss_pct']==pytest.approx(100*beam_lost/poa.poa_global.sum())
    assert result['modules'][0]['main_cause']=='test-wall'
    assert result['modules'][0]['diffuse_loss_pct']==0
    monkeypatch.undo()
    payload=project.model_dump()
    payload['roof'].update(obstacles=[],keepouts=[],parapet_height_m=0)
    clear=generate_layout(validate_project(payload),LayoutParams(tilt_deg=0))
    clear.modules=clear.modules[:1]
    unshaded=analyze_design(validate_project(payload),clear,offline=True)
    assert unshaded['summary']['avg_loss_pct']==0
    assert unshaded['metadata']['sky_masking_fraction']==0
