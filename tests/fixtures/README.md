# T02 接口录样

`nasa_48h.json` 和 `pvgis_48h.json` 是 2026-10-01 实际接口响应的前 48 个小时，原值未修改；只截短 NASA 五个参数的时间字典、PVGIS 的 `tmy_hourly` 列表，其余服务元数据保留。测试需要填充值或异常值时仅修改内存深拷贝。

- NASA：常州 31.81, 119.97，2023-01-01 至 2023-12-31，`ALLSKY_SFC_SW_DWN,ALLSKY_SFC_SW_DNI,ALLSKY_SFC_SW_DIFF,T2M,WS10M`，`community=RE`、`time-standard=UTC`、`format=JSON`。[接口说明](https://power.larc.nasa.gov/docs/services/api/temporal/hourly/)
- PVGIS：`https://re.jrc.ec.europa.eu/api/v5_3/tmy?lat=31.81&lon=119.97&outputformat=json&raddatabase=PVGIS-ERA5`。TMY 原始首月年份 2007；规范年仅用于连续时间索引，原始选月保留在元数据。[官方手册](https://joint-research-centre.ec.europa.eu/photovoltaic-geographical-information-system-pvgis/using-pvgis-5/pvgis-5-user-manual_en)

数据许可与引用登记在 `docs/sources.md`。完整全年数据放在 `data/demo/weather/`；缓存原始响应不提交。

## T03 PVGIS 计算器录样

`pvgis_pvcalc.json` 是 2026-10-01 从 [JRC PVGIS 5.3 PVcalc](https://re.jrc.ec.europa.eu/api/v5_3/PVcalc?lat=31.81&lon=119.97&peakpower=1&loss=14&angle=25&aspect=0&raddatabase=PVGIS-ERA5&outputformat=json) 实际下载的完整响应，保留输入、十二个月和服务元数据。常州、1 kWp、25°、正南、损失 14%、PVGIS-ERA5；官方年值 1275.11 kWh。测试异常情况只修改内存副本。离线演示及下载时间、请求 URL、响应文件 SHA-256 放在 `data/demo/yields/`；许可同 `docs/sources.md` 中的 PVGIS 条目。
