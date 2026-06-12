from __future__ import annotations

from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import ClimateEntityFeature, HVACMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .client import BBHomeClient, BBHomeTemperature
from .const import CONF_RAW_TEMPERATURE_COUNT, DOMAIN, config_value


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    client: BBHomeClient = data["client"]
    coordinator = data["coordinator"]
    raw_count = config_value(entry, CONF_RAW_TEMPERATURE_COUNT, 0)
    if raw_count:
        entities = [BBHomeRawClimate(coordinator, client, address) for address in range(1, raw_count + 1)]
    else:
        entities = [BBHomeClimate(coordinator, client, temp) for temp in client.temperatures if temp.controllable]
    async_add_entities(entities)


class BBHomeClimate(CoordinatorEntity, ClimateEntity):
    _attr_has_entity_name = True
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE
    _attr_target_temperature_step = 0.5
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT, HVACMode.AUTO]

    def __init__(self, coordinator, client: BBHomeClient, temperature: BBHomeTemperature) -> None:
        super().__init__(coordinator)
        self._client = client
        self._temperature = temperature
        self._attr_unique_id = f"bbhome_{temperature.unique_id}"
        self._attr_name = temperature.full_name

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, f"temperature_{self._temperature.index + 1}")},
            "manufacturer": "Bits & Bites",
            "name": self._temperature.full_name,
        }

    @property
    def current_temperature(self) -> float | None:
        return self._temperature.current

    @property
    def target_temperature(self) -> float | None:
        return self._temperature.target

    @property
    def hvac_mode(self) -> HVACMode:
        if self._temperature.mode == "AUTO":
            return HVACMode.AUTO
        if self._temperature.mode == "MAN":
            return HVACMode.HEAT
        return HVACMode.OFF

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        # The original app cycles mode with SEL, so repeat until the next refresh reports the requested state.
        await self._client.temperature_step(self._temperature, "SEL")
        await self.coordinator.async_request_refresh()

    async def async_set_temperature(self, **kwargs) -> None:
        target = kwargs.get(ATTR_TEMPERATURE)
        current = self._temperature.target
        if target is None or current is None:
            return
        command = "+++" if target > current else "---"
        for _ in range(min(10, int(abs(target - current) / 0.5 + 0.5))):
            await self._client.temperature_step(self._temperature, command)
        await self.coordinator.async_request_refresh()


class BBHomeRawClimate(CoordinatorEntity, ClimateEntity):
    _attr_has_entity_name = True
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE
    _attr_target_temperature_step = 0.5
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT, HVACMode.AUTO]

    def __init__(self, coordinator, client: BBHomeClient, address: int) -> None:
        super().__init__(coordinator)
        self._client = client
        self._address = address
        self._attr_unique_id = f"bbhome_raw_t_{address:03d}"
        self._attr_name = f"T {address:03d}"

    @property
    def _temperature(self) -> BBHomeTemperature | None:
        index = self._address - 1
        if 0 <= index < len(self._client.temperatures):
            return self._client.temperatures[index]
        return None

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, "raw_temperatures")},
            "manufacturer": "Bits & Bites",
            "name": "B&B Home Raw Temperatures",
        }

    @property
    def current_temperature(self) -> float | None:
        return self._temperature.current if self._temperature else None

    @property
    def target_temperature(self) -> float | None:
        return self._temperature.target if self._temperature else None

    @property
    def hvac_mode(self) -> HVACMode:
        temperature = self._temperature
        if temperature and temperature.mode == "AUTO":
            return HVACMode.AUTO
        if temperature and temperature.mode == "MAN":
            return HVACMode.HEAT
        return HVACMode.OFF

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        await self._client.raw_temperature_step(self._address, "SEL")
        await self.coordinator.async_request_refresh()

    async def async_set_temperature(self, **kwargs) -> None:
        target = kwargs.get(ATTR_TEMPERATURE)
        current = self.target_temperature
        if target is None or current is None:
            return
        command = "+++" if target > current else "---"
        for _ in range(min(10, int(abs(target - current) / 0.5 + 0.5))):
            await self._client.raw_temperature_step(self._address, command)
        await self.coordinator.async_request_refresh()
