"""Validated project geometry and immutable design-file records (metres)."""

import math
import re
from datetime import datetime, timezone
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_serializer, model_validator
from shapely.geometry import Polygon
from shapely.geometry.polygon import orient

Point2 = tuple[float, float]
Point3 = tuple[float, float, float]
Tilt = Annotated[float, Field(ge=0, le=35)]
Hour = Annotated[float, Field(ge=0, le=24)]


class GzError(Exception):
    def __init__(self, error_code, message_zh, fix_hint):
        super().__init__(message_zh)
        self.error_code, self.message_zh, self.fix_hint = error_code, message_zh, fix_hint

    def as_dict(self):
        return dict(ok=False, error_code=self.error_code, message_zh=self.message_zh, fix_hint=self.fix_hint)


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, populate_by_name=True, serialize_by_alias=True)


def project_id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", value):
        raise GzError("PROJECT_ID_INVALID", "项目编号格式不正确", "使用1至64位英文字母、数字、下划线或短横线")
    return value


def ccw(points, code="ROOF_POLYGON_INVALID", label="屋顶轮廓"):
    polygon = orient(Polygon(points), sign=1) if len(points) >= 3 else Polygon()
    if polygon.is_empty or not polygon.is_valid or polygon.area <= 0:
        raise GzError(code, f"{label}须有至少3个顶点、面积大于0且不能自相交", "按轮廓顺序填写坐标，检查重叠边和交叉边")
    return list(polygon.exterior.coords)[:-1]


class Site(Record):
    lat: float = Field(ge=0, le=55)
    lon: float = Field(ge=-180, le=180)
    timezone: str = "Asia/Shanghai"
    albedo: float = Field(default=0.2, ge=0, le=1)
    design_temp_min_c: float | None = Field(default=None, ge=-100, le=70)
    design_temp_max_c: float | None = Field(default=None, ge=-100, le=70)
    wind_city: str | None = None

    @field_validator('wind_city')
    @classmethod
    def known_wind_city(cls, value):
        from .wind import catalog
        if value is not None and value not in catalog():
            raise ValueError('风压城市须为江苏13市之一；其他地区请填写示意风压并复核')
        return value

    @model_serializer(mode='wrap')
    def omit_wind_city(self, handler):
        data = handler(self)
        if self.wind_city is None:
            data.pop('wind_city', None)
        return data

    @model_validator(mode="after")
    def design_temperature_order(self):
        if self.design_temp_min_c is not None and self.design_temp_max_c is not None and self.design_temp_min_c > self.design_temp_max_c:
            raise GzError("SITE_TEMPERATURE_INVALID", "设计最低气温不能高于最高气温", "检查当地气象站极值，按最低、最高气温填写")
        return self


class Obstacle(Record):
    id: str
    label: str
    kind: Literal["prism", "cylinder"]
    height_m: float
    footprint: list[Point2] | None = None
    center: Point2 | None = None
    radius_m: float | None = None

    @model_validator(mode="after")
    def geometry(self):
        if self.height_m <= 0:
            raise GzError("OBSTACLE_HEIGHT_INVALID", "障碍物高度必须大于0米", "填写障碍物高出屋面的实测高度")
        if self.kind == "prism":
            if self.footprint is None or self.center is not None or self.radius_m is not None:
                raise GzError("OBSTACLE_GEOMETRY_INVALID", "棱柱障碍物需要平面轮廓", "填写footprint，不要填写圆心和半径")
            self.footprint = ccw(self.footprint, "OBSTACLE_POLYGON_INVALID", "障碍物轮廓")
        elif self.center is None or self.radius_m is None or self.radius_m <= 0 or self.footprint is not None:
            raise GzError("OBSTACLE_GEOMETRY_INVALID", "圆柱障碍物需要圆心和正半径", "填写center和大于0的radius_m，不要填写footprint")
        return self


def obstacle_polygon(obstacle):
    if obstacle.kind == "prism":
        return Polygon(obstacle.footprint)
    x, y = obstacle.center
    return Polygon([(x + obstacle.radius_m * math.cos(i * math.tau / 32),
                     y + obstacle.radius_m * math.sin(i * math.tau / 32)) for i in range(32)])


class Keepout(Record):
    id: str
    label: str
    polygon: list[Point2]
    preset: Literal['vent', 'skylight'] | None = None
    clearance_m: float | None = Field(default=None, ge=0)

    @model_serializer(mode='wrap')
    def optional_preset(self, handler):
        return {key: value for key, value in handler(self).items() if value is not None}

    @field_validator("polygon")
    @classmethod
    def geometry(cls, value):
        return ccw(value, "KEEPOUT_POLYGON_INVALID", "禁区轮廓")


class Calibration(Record):
    p1_px: Point2
    p2_px: Point2
    distance_m: float
    # Where north points on the drawing, clockwise from straight up; drawings saved before this field are north-up.
    north_deg: float = Field(default=0, ge=-360, le=360)

    @model_validator(mode="after")
    def distance(self):
        if self.distance_m <= 0 or self.p1_px == self.p2_px:
            raise GzError("CALIBRATION_INVALID", "标定距离须大于0且两个像素点不能重合", "选择两个不同点，并填写它们的实测距离（米）")
        return self

    @model_serializer(mode="wrap")
    def omit_north_up(self, handler):
        data = handler(self)
        if not data.get("north_deg"):
            data.pop("north_deg", None)
        return data


class Underlay(Record):
    image: str
    calibration: Calibration


def validated(cls, value, code="PROJECT_INVALID"):
    try:
        if isinstance(value, BaseModel):
            value = value.model_dump(by_alias=True)
        return cls.model_validate(value)
    except (ValidationError, TypeError, ValueError) as error:
        raise GzError(code, "数据字段、类型或数值范围不正确", "按项目和工具规格检查必填字段、枚举值与数值范围") from error


def px_to_m(points_px, calibration):
    calibration = validated(Calibration, calibration, "CALIBRATION_INVALID")
    scale = calibration.distance_m / math.dist(calibration.p1_px, calibration.p2_px)
    turn = math.radians(calibration.north_deg)
    try:
        result = [[(x - calibration.p1_px[0]) * scale, (calibration.p1_px[1] - y) * scale] for x, y in points_px]
        result = [[u * math.cos(turn) - v * math.sin(turn), u * math.sin(turn) + v * math.cos(turn)] for u, v in result]
        if not all(math.isfinite(v) for p in result for v in p):
            raise ValueError("nonfinite")
        return result
    except (TypeError, ValueError) as error:
        raise GzError("CALIBRATION_INVALID", "像素坐标须是有限数值的二维点", "检查每个点的x、y像素坐标") from error


class WindSettings(Record):
    basic_pressure_kpa: float | None = Field(default=None, ge=0, le=5)
    roughness: Literal['A', 'B', 'C', 'D'] = 'B'
    friction: float = Field(default=.5, gt=0, le=2)
    block_kg: float = Field(default=15, gt=0, le=100)
    clamp_capacity_kn: float = Field(default=.8, gt=0, le=100)
    seam_spacing_m: float = Field(default=.5, ge=.05, le=10)
    seam_azimuth_deg: float | None = Field(default=None, ge=0, le=360)
    seam_offset_m: float = Field(default=0, ge=0, le=10)
    clamp_min_spacing_m: float = Field(default=.2, ge=.05, le=5)
    clamp_max_spacing_m: float = Field(default=1.2, ge=.05, le=10)
    clamp_edge_m: float = Field(default=.1, ge=.01, le=1)

    @model_validator(mode='after')
    def spacing_order(self):
        if self.clamp_min_spacing_m > self.clamp_max_spacing_m:
            raise ValueError('夹具最小安装距离不能大于最大允许间距')
        return self


class RoofPlane(Record):
    id: int = Field(gt=0, strict=True)
    outline: list[Point2]
    slope_deg: float = Field(ge=0, lt=90)
    slope_azimuth_deg: float = Field(ge=0, le=360)
    offset_m: float = Field(default=0, ge=0)
    material: Literal['metal', 'concrete', 'glass'] = 'metal'
    load_capacity_kn_m2: float | None = Field(default=None, gt=0)
    load_verified: bool | None = None
    _outline = field_validator('outline')(ccw)


class PitchedSettings(Record):
    kind: Literal['single', 'gable', 'hip', 'sawtooth'] = 'gable'
    slope_deg: float = Field(default=5, gt=0, lt=90)
    azimuth_deg: float = Field(default=180, ge=0, le=360)
    material: Literal['metal', 'concrete'] = 'metal'
    ridge_mode: Literal['long', 'short'] = 'long'
    ridge: tuple[Point2, Point2] | None = None
    teeth: int = Field(default=4, ge=1, strict=True)
    tooth_width_m: float | None = Field(default=None, gt=0)
    glass_deg: float = Field(default=70, gt=0, lt=90)


class GroundSettings(Record):
    lower_edge_m: float = Field(default=.5, ge=.3, le=3)
    road_every: int = Field(default=4, ge=0, strict=True)
    road_width_m: float = Field(default=4, gt=0)
    fence_setback_m: float = Field(default=2, ge=0)


class CarportSettings(Record):
    direction_deg: float | None = Field(default=None, ge=0, le=360)
    bay_rows: int = Field(default=2, ge=1, le=2, strict=True)
    column_rows: int = Field(default=1, ge=1, le=2, strict=True)
    clear_height_m: float = Field(default=2.5, ge=0, le=10)
    structure_depth_m: float = Field(default=.3, gt=0, le=2)
    structural_strip_m: float = Field(default=.6, ge=.4, le=3)
    tilt_deg: float = Field(default=5, ge=0, le=15)
    facing: Literal['south', 'row'] = 'south'
    bays: list[Keepout] = Field(default_factory=list)
    aisles: list[Keepout] = Field(default_factory=list)
    strips: list[Keepout] = Field(default_factory=list)
    columns: dict[str, list[Point2]] = Field(default_factory=dict)


class Roof(Record):
    use: Literal['barn', 'grazing'] | None = None
    animal: Literal['sheep', 'cow'] | None = None
    ground_sun_min_pct: float | None = Field(default=None, ge=0, le=100)
    ground: GroundSettings | None = None
    carport: CarportSettings | None = None
    planes: list[RoofPlane] = Field(default_factory=list)
    pitched: PitchedSettings | None = None
    seam_setback_m: float | None = Field(default=None, ge=0)
    wind: WindSettings | None = None
    inverter_positions: list[Point2] = Field(default_factory=list)
    grid_point: Point2 | None = None
    type: Literal["flat", "metal", "pitched", "ground", "carport"] = "flat"
    slope_deg: float | None = Field(default=None, ge=1, le=30)
    slope_azimuth_deg: float | None = Field(default=None, ge=0, le=360)
    building: str | None = None
    outline: list[Point2]
    height_m: float
    parapet_height_m: float
    load_capacity_kn_m2: float
    # True only when the user confirms the allowed load comes from a structural check; otherwise it is an illustrative value.
    load_verified: bool = False
    obstacles: list[Obstacle] = Field(default_factory=list)
    keepouts: list[Keepout] = Field(default_factory=list)
    underlay: Underlay | None = None
    # T19: buildings and trees off the roof; height counts from the roof surface like obstacles.
    surroundings: list[Obstacle] = Field(default_factory=list)

    @field_validator("outline")
    @classmethod
    def geometry(cls, value):
        return ccw(value)

    @model_validator(mode='before')
    @classmethod
    def animal_defaults(cls, value):
        if isinstance(value, dict) and value.get('use') == 'grazing':
            value = dict(value)
            value['animal'] = value.get('animal') or 'sheep'
            ground = value.get('ground')
            if ground is None or isinstance(ground, dict):
                ground = dict(ground or {})
                ground.setdefault('lower_edge_m', 2.5 if value['animal'] == 'cow' else 1.5)
                value['ground'] = ground
        return value

    @model_validator(mode="after")
    def bounds(self):
        if self.use == 'grazing' and self.type != 'ground':
            raise ValueError('牧光用途只适用于空地')
        if self.use == 'barn' and not (self.type == 'metal' or self.type == 'pitched'
                                     and any(p.material == 'metal' for p in self.planes)):
            raise ValueError('养殖场棚顶须包含彩钢瓦安装面')
        if self.use != 'grazing' and (self.animal is not None or self.ground_sun_min_pct is not None):
            raise ValueError('牲畜和地面受光要求只用于牧光')
        if self.type == 'pitched':
            if any(p.slope_deg <= 0 for p in self.planes):
                raise ValueError('斜屋面坡度必须大于0')
            from .roofplane import validate_planes
            validate_planes(self)
        if self.type in ('ground', 'carport'):
            from .installation import validate_site
            validate_site(self)
        if self.type == "metal" and (self.slope_deg is None or self.slope_azimuth_deg is None):
            raise GzError("ROOF_SLOPE_INVALID", "彩钢瓦需要坡度和坡面朝向", "填写1至30度坡度和0至360度朝向")
        for invalid, code, message, hint in (
            (self.height_m <= 0 and self.type not in ('ground', 'carport'),
             "ROOF_HEIGHT_INVALID", "屋顶高度必须大于0米", "填写屋面离地高度"),
            (not 0 <= self.parapet_height_m <= 3, "PARAPET_HEIGHT_INVALID", "女儿墙高度须在0至3米之间", "无女儿墙时填写0"),
            (self.load_capacity_kn_m2 <= 0, "ROOF_LOAD_INVALID", "屋顶承重必须大于0", "填写结构核定的允许附加荷载，单位kN/m²")):
            if invalid:
                raise GzError(code, message, hint)
        roof = Polygon(self.outline)
        zones = [(o, obstacle_polygon(o), "OBSTACLE_OUTSIDE_ROOF") for o in self.obstacles]
        zones += [(k, Polygon(k.polygon), "KEEPOUT_OUTSIDE_ROOF") for k in self.keepouts]
        if len({z.id for z, _, _ in zones}) != len(zones):
            raise GzError("ZONE_ID_DUPLICATE", "障碍物和禁区编号重复", "为每块障碍物和禁区填写不同编号")
        for zone, polygon, code in zones:
            if not roof.covers(polygon):
                raise GzError(code, f"{zone.label}（{zone.id}）超出屋顶", "调整其轮廓或圆心半径，使它完全位于屋顶内")
        if len({z.id for z, _, _ in zones} | {s.id for s in self.surroundings}) != len(zones) + len(self.surroundings):
            raise GzError("ZONE_ID_DUPLICATE", "周边遮挡物和障碍物、禁区或彼此编号重复", "为每个周边遮挡物填写不同编号")
        for row in self.surroundings:
            if roof.intersection(obstacle_polygon(row)).area > 1e-6:
                raise GzError("SURROUNDING_ON_ROOF", f"{row.label}（{row.id}）压在屋顶上", "屋面上的设备填到障碍物里；周边遮挡物要放在屋顶外")
        return self

    @model_serializer(mode="wrap")
    def omit_empty_surroundings(self, handler):
        # Roofs without surroundings or a confirmed load keep their exact earlier file bytes.
        data = handler(self)
        for key in ('use', 'animal', 'ground_sun_min_pct'):
            if data.get(key) is None:
                data.pop(key, None)
        if self.type not in ('pitched', 'carport'):
            data.pop('planes', None)
        if self.type != 'pitched':
            for key in ('pitched', 'seam_setback_m'):
                data.pop(key, None)
        for key in ('ground', 'carport'):
            if data.get(key) is None:
                data.pop(key, None)
        if self.type != "metal":
            for key in ("slope_deg", "slope_azimuth_deg", "building"):
                data.pop(key, None)
        for name in ("surroundings", "load_verified", "inverter_positions", "grid_point", "wind"):
            if not data.get(name):
                data.pop(name, None)
        return data


class StructuredRequirements(Record):
    export_allowed: bool | None = Field(default=None, strict=True)
    ballast_only: bool | None = Field(default=None, strict=True)  # owner forbids drilling the roof: no anchors
    curtail_pct_max: float | None = Field(default=None, ge=0, le=100)
    transformer_kva: float | None = Field(default=None, gt=0)
    transformer_share: float | None = Field(default=None, gt=0, le=1)
    max_height_m: float | None = Field(default=None, ge=0)
    phase1_kw: float | None = Field(default=None, gt=0)
    phase1_budget_cny: float | None = Field(default=None, gt=0)
    budget_cny_max: float | None = Field(default=None, ge=0)
    payback_years_max: float | None = Field(default=None, gt=0)
    capacity_kw_min: float | None = Field(default=None, ge=0)
    capacity_kw_max: float | None = Field(default=None, ge=0)
    walkway_m_min: float | None = Field(default=None, ge=0)
    obstacle_clearance_m_min: float | None = Field(default=None, ge=0)
    edge_setback_m_min: float | None = Field(default=None, ge=0)
    keep_clear_ids: list[str] = Field(default_factory=list)
    tilt_deg_range: tuple[Tilt, Tilt] | None = None
    notes: str | None = None

    @model_serializer(mode="wrap")
    def optional_constraints(self, handler):
        values = handler(self)
        for key in ('export_allowed', 'ballast_only', 'curtail_pct_max', 'transformer_kva', 'transformer_share', 'max_height_m', 'phase1_kw',
                    'phase1_budget_cny'):
            if values.get(key) is None:
                values.pop(key, None)
        return values

    @model_validator(mode='after')
    def exclusive_phase(self):
        if self.phase1_kw is not None and self.phase1_budget_cny is not None:
            raise ValueError('一期装机与一期预算只能填一项')
        return self

    @field_validator("tilt_deg_range")
    @classmethod
    def tilt_range(cls, value):
        if value is not None and not 0 <= value[0] <= value[1] <= 35:
            raise GzError("REQUIREMENTS_INVALID", "倾角范围须递增且在0至35度内", "例如填写[15, 25]")
        return value


class Requirements(Record):
    text: str = ""
    structured: StructuredRequirements = Field(default_factory=StructuredRequirements)


class Equipment(Record):
    inverter_brand: Literal['Sungrow', 'Huawei'] | None = None
    module_id: str
    inverter_id: str | None = None
    racking: str = "ballast_tilt"

    @model_serializer(mode='wrap')
    def optional_brand(self, handler):
        values = handler(self)
        if values.get('inverter_brand') is None:
            values.pop('inverter_brand', None)
        return values


class Economics(Record):
    land_rent_cny_mu_year: float | None = Field(default=None, ge=0)
    loan_ratio: float | None = Field(default=None, ge=0, lt=1)
    loan_rate: float | None = Field(default=None, ge=0, le=1)
    loan_years: int | None = Field(default=None, ge=1, le=50)
    tariff_class: Literal['two_part', 'single100', 'single_small'] | None = None
    posttax_payback: bool | None = Field(default=None, strict=True)
    cleaning_times: int | None = Field(default=None, ge=0, le=365)
    refurbish: bool | None = Field(default=None, strict=True)
    tax_holiday_confirmed: bool | None = Field(default=None, strict=True)
    mechanism_share: float | None = Field(default=None, ge=0, le=.9)
    mechanism_price: float | None = Field(default=None, ge=0, le=2)
    mechanism_years: int | None = Field(default=None, ge=1, le=25)
    green_sold_share: float | None = Field(default=None, ge=0, le=1)
    public_subsidy_confirmed: bool | None = Field(default=None, strict=True)
    subsidy_year: int | None = Field(default=None, ge=1, le=25)
    monthly_kwh: float | None = Field(default=None, ge=1)
    shifts: Literal[1, 2, 3, 4] | None = None
    capex_cny_per_w: float | None = Field(default=None, ge=0)
    self_use_ratio: float | None = Field(default=None, ge=0, le=1)
    price_self_cny_kwh: float | None = Field(default=None, ge=0)
    price_export_cny_kwh: float | None = Field(default=None, ge=0)
    om_cny_per_w_year: float | None = Field(default=None, ge=0)
    lifetime_years: int | None = Field(default=None, gt=0)
    discount_rate: float | None = Field(default=None, ge=0, lt=1)
    degradation_annual_pct: float | None = Field(default=None, ge=0, lt=100)
    emission_factor_kgco2_kwh: float | None = Field(default=None, ge=0)
    assumptions_note: str | None = None

    @model_serializer(mode="wrap")
    def omit_unused_load(self, handler):
        values = handler(self)
        for key in ('land_rent_cny_mu_year', 'monthly_kwh', 'shifts', 'loan_ratio', 'loan_rate', 'loan_years', 'tariff_class', 'posttax_payback',
                    'cleaning_times', 'refurbish', 'tax_holiday_confirmed', 'mechanism_share', 'mechanism_price',
                    'mechanism_years', 'green_sold_share', 'public_subsidy_confirmed', 'subsidy_year'):
            if values.get(key) is None:
                values.pop(key, None)
        return values

    @model_validator(mode='after')
    def financial_terms(self):
        if self.loan_ratio and self.loan_years is not None and self.loan_years > (self.lifetime_years or 25):
            raise ValueError('贷款期限不得超过计算期')
        if self.mechanism_share and (self.mechanism_price is None or self.mechanism_years is None):
            raise ValueError('已确认机制电量须同时提供机制价格与年限')
        if (self.mechanism_share or 0) + (self.green_sold_share or 0) > 1:
            raise ValueError('机制和已售绿电比例之和不得超过100%')
        return self


class LayoutParams(Record):
    extra_row_gap_m: float | None = Field(default=None, ge=0, le=30)
    road_every: int | None = Field(default=None, ge=0, strict=True)
    road_width_m: float | None = Field(default=None, gt=0)
    fence_setback_m: float | None = Field(default=None, ge=0)
    lower_edge_m: float | None = Field(default=None, ge=.3, le=3)
    clear_height_m: float | None = Field(default=None, ge=0, le=10)
    plane_ids: list[int] | None = None
    surface: bool = False
    align: Literal["south", "edge"] | None = None
    layout: Literal["rows", "ew"] = "rows"
    fill_landscape: bool = False
    tilt_deg: float = Field(default=25, ge=0, lt=90)
    azimuth_deg: float = Field(default=180, ge=0, le=360)
    orientation: Literal["landscape", "portrait"] = "portrait"
    rows_per_rack: int = Field(default=1, ge=1, le=2, strict=True)
    edge_setback_m: float = Field(default=1, ge=0)
    obstacle_clearance_m: float = Field(default=0.5, ge=0)
    keepout_clearance_m: float = Field(default=0.3, ge=0)
    walkway_every_n_rows: int = Field(default=0, ge=0, strict=True)
    walkway_width_m: float = Field(default=1, ge=0)
    winter_window_hours: tuple[Hour, Hour] = (9, 15)

    @model_validator(mode='after')
    def surface_limits(self):
        if not self.surface and self.tilt_deg > 35:
            raise ValueError('普通支架倾角不能超过35°')
        if self.plane_ids is not None and (not self.plane_ids or any(p < 1 for p in self.plane_ids)):
            raise ValueError('选用坡面须包含正整数编号')
        return self

    @model_serializer(mode="wrap")
    def omit_legacy_defaults(self, handler):
        values = handler(self)
        for key in ('lower_edge_m', 'clear_height_m', 'road_every', 'road_width_m', 'fence_setback_m', 'extra_row_gap_m'):
            if values.get(key) is None:
                values.pop(key, None)
        defaults = (("align", None), ("layout", "rows"), ("fill_landscape", False), ('surface', False), ('plane_ids', None))
        for key, default in defaults:
            if values.get(key) == default:
                values.pop(key, None)
        return values

    @field_validator("winter_window_hours")
    @classmethod
    def window(cls, value):
        if not 0 <= value[0] < value[1] <= 24:
            raise GzError("LAYOUT_PARAMS_INVALID", "冬至防遮挡时间窗口须在0至24时内递增", "例如填写[9, 15]")
        return value


class SiteFacts(Record):
    """T22: what the owner says about the site before construction; every answer may be left blank."""
    roof_type: Literal["concrete", "metal", "other"] | None = None
    land_type: Literal['construction', 'cultivated', 'permanent', 'forest', 'grass', 'pasture', 'unused'] | None = None
    within_redline: bool | None = None
    roof_age_years: float | None = Field(default=None, ge=0, le=100)
    core: Literal["none", "rockwool", "foam"] | None = None
    skylights: bool | None = None
    owned: bool | None = None
    transformer_kva: float | None = Field(default=None, ge=1, le=100000)
    monthly_kwh: float | None = Field(default=None, ge=1, le=1e9)
    shifts: Literal[1, 2, 3, 4] | None = None
    export_allowed: bool | None = None

    @model_serializer(mode="wrap")
    def answered(self, handler):
        return {key: value for key, value in handler(self).items() if value is not None}


class ParkAssociation(Record):
    id: str
    template: str
    snapshot: str = Field(pattern=r'^[a-f0-9]{64}$')
    x_m: float
    y_m: float
    rotation_deg: float = Field(ge=-360, le=360)
    _ids = field_validator('id', 'template')(project_id)


class Project(Record):
    facts: SiteFacts | None = None
    park: ParkAssociation | None = None
    schema_name: Literal["guangzhu.project/1"] = Field(default="guangzhu.project/1", alias="schema")
    id: str
    name: str
    collection: Literal["real", "boundary", "impossible"] | None = None
    site: Site
    roof: Roof
    requirements: Requirements = Field(default_factory=Requirements)
    equipment: Equipment
    economics: Economics
    designs: list[str] = Field(default_factory=list)
    _id = field_validator("id")(project_id)

    @model_serializer(mode='wrap')
    def omit_park(self, handler):
        values = handler(self)
        if values.get('park') is None:
            values.pop('park', None)
        if values.get('facts') is None:
            values.pop('facts', None)
        return values

    @model_validator(mode="after")
    def matching_rack(self):
        expected = "clamp_flush" if self.roof.type == "metal" else "ballast_tilt"
        if self.roof.type == 'metal' and self.roof.use == 'barn':
            expected = 'clamp_barn'
        if self.roof.type == 'pitched':
            expected = 'plane_flush'
        if self.roof.type in ('ground', 'carport'):
            expected = 'ground_pile' if self.roof.type == 'ground' else 'carport_steel'
        if self.equipment.racking != expected:
            raise GzError("RACK_TYPE_INVALID", "支架和屋面类型不匹配", f"此屋面须使用{expected}")
        return self


def validate_project(payload):
    return validated(Project, payload)


class Module(Record):
    phase: int | None = Field(default=None, strict=True, ge=1, le=2)
    id: str = Field(pattern=r"^(?:P[1-9]\d*-)?R\d{2,}-[12]-C\d{3,}$")
    row: int = Field(ge=1)
    tier: int = Field(ge=1, le=2)
    col: int = Field(ge=1)
    center: Point3
    corners: tuple[Point3, Point3, Point3, Point3]
    tilt: float = Field(ge=0, lt=90)
    azimuth: float = Field(ge=0, le=360)
    orientation: Literal["landscape", "portrait"]

    @model_validator(mode='after')
    def legacy_tilt(self):
        if not self.id.startswith('P') and self.tilt > 35:
            raise ValueError('普通支架组件倾角不能超过35°')
        return self

    @model_serializer(mode='wrap')
    def optional_phase(self, handler):
        values = handler(self)
        if values.get('phase') is None:
            values.pop('phase', None)
        return values


class RemovedModule(Module):
    reason: str


class Design(Record):
    installation_roof: Roof | None = None
    version: int = Field(default=1, ge=1, strict=True)
    params: LayoutParams
    modules: list[Module] = Field(default_factory=list)
    removed_modules: list[RemovedModule] = Field(default_factory=list)
    added_keepouts: list[Keepout] = Field(default_factory=list)
    modules_per_string: int | None = Field(default=None, gt=0)
    parent_version: int | None = Field(default=None, ge=1)
    reason: str = "初始排板"
    author: Literal["agent", "user", "rule"] = "rule"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    statistics: dict[str, Any] = Field(default_factory=dict)

    @model_serializer(mode='wrap')
    def optional_installation(self, handler):
        values = handler(self)
        if self.installation_roof is None:
            values.pop('installation_roof', None)
        return values
