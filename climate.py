from __future__ import annotations

from time import monotonic

from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import ClimateEntityFeature, HVACMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .client import BBHomeClient, BBHomeTemperature
from .const import CONF_RAW_TEMPERATURE_COUNT, DOMAIN, config_value

_OPTIMISTIC_TIMEOUT = 8.0
_HVAC_MODE_CYCLE = [HVACMode.OFF, HVACMode.AUTO, HVACMode.HEAT]


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


class _OptimisticClimateState:
    _optimistic_until: float | None = None
    _optimistic_hvac_mode: HVACMode | None = None
    _optimistic_target_temperature: float | None = None

    @property
    def target_temperature(self) -> float | None:
        if self._optimistic_active and self._optimistic_target_temperature is not None:
            return self._optimistic_target_temperature
        return self._actual_target_temperature

    @property
    def hvac_mode(self) -> HVACMode:
        if self._optimistic_active and self._optimistic_hvac_mode is not None:
            return self._optimistic_hvac_mode
        return self._actual_hvac_mode

    @property
    def _optimistic_active(self) -> bool:
        if self._optimistic_until is None:
            return False
        if monotonic() >= self._optimistic_until:
            self._clear_optimistic()
            return False
        mode_matches = self._optimistic_hvac_mode is None or self._actual_hvac_mode == self._optimistic_hvac_mode
        temperature_matches = (
            self._optimistic_target_temperature is None
            or self._actual_target_temperature == self._optimistic_target_temperature
        )
        if mode_matches and temperature_matches:
            self._clear_optimistic()
            return False
        return True

    def _set_optimistic(
        self,
        *,
        hvac_mode: HVACMode | None = None,
        target_temperature: float | None = None,
    ) -> None:
        if self._optimistic_active:
            if hvac_mode is None:
                hvac_mode = self._optimistic_hvac_mode
            if target_temperature is None:
                target_temperature = self._optimistic_target_temperature
        self._optimistic_until = monotonic() + _OPTIMISTIC_TIMEOUT
        self._optimistic_hvac_mode = hvac_mode
        self._optimistic_target_temperature = target_temperature
        self.async_write_ha_state()

    def _clear_optimistic(self) -> None:
        self._optimistic_until = None
        self._optimistic_hvac_mode = None
        self._optimistic_target_temperature = None


class BBHomeClimate(_OptimisticClimateState, CoordinatorEntity, ClimateEntity):
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
    def _actual_target_temperature(self) -> float | None:
        return self._temperature.target

    @property
    def _actual_hvac_mode(self) -> HVACMode:
        if self._temperature.mode == "AUTO":
            return HVACMode.AUTO
        if self._temperature.mode == "MAN":
            return HVACMode.HEAT
        return HVACMode.OFF

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        for _ in range(_mode_step_count(self._actual_hvac_mode, hvac_mode)):
            await self._client.temperature_step(self._temperature, "SEL")
        self._set_optimistic(hvac_mode=hvac_mode)
        await self.coordinator.async_request_refresh()

    async def async_set_temperature(self, **kwargs) -> None:
        target = kwargs.get(ATTR_TEMPERATURE)
        current = self._actual_target_temperature
        if target is None or current is None:
            return
        command = "+++" if target > current else "---"
        for _ in range(min(10, int(abs(target - current) / 0.5 + 0.5))):
            await self._client.temperature_step(self._temperature, command)
        self._set_optimistic(target_temperature=target)
        await self.coordinator.async_request_refresh()


class BBHomeRawClimate(_OptimisticClimateState, CoordinatorEntity, ClimateEntity):
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
    def _actual_target_temperature(self) -> float | None:
        return self._temperature.target if self._temperature else None

    @property
    def _actual_hvac_mode(self) -> HVACMode:
        temperature = self._temperature
        if temperature and temperature.mode == "AUTO":
            return HVACMode.AUTO
        if temperature and temperature.mode == "MAN":
            return HVACMode.HEAT
        return HVACMode.OFF

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        for _ in range(_mode_step_count(self._actual_hvac_mode, hvac_mode)):
            await self._client.raw_temperature_step(self._address, "SEL")
        self._set_optimistic(hvac_mode=hvac_mode)
        await self.coordinator.async_request_refresh()

    async def async_set_temperature(self, **kwargs) -> None:
        target = kwargs.get(ATTR_TEMPERATURE)
        current = self._actual_target_temperature
        if target is None or current is None:
            return
        command = "+++" if target > current else "---"
        for _ in range(min(10, int(abs(target - current) / 0.5 + 0.5))):
            await self._client.raw_temperature_step(self._address, command)
        self._set_optimistic(target_temperature=target)
        await self.coordinator.async_request_refresh()


def _mode_step_count(current: HVACMode, target: HVACMode) -> int:
    if current not in _HVAC_MODE_CYCLE or target not in _HVAC_MODE_CYCLE:
        return 0
    return (_HVAC_MODE_CYCLE.index(target) - _HVAC_MODE_CYCLE.index(current)) % len(_HVAC_MODE_CYCLE)
