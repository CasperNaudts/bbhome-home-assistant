from __future__ import annotations

from time import monotonic

from homeassistant.components.light import ColorMode, LightEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .client import BBHomeButton, BBHomeClient
from .const import CONF_RAW_DIMMER_COUNT, CONF_RAW_SWITCH_COUNT, DIMMER_MAX, DOMAIN, config_value

_OPTIMISTIC_TIMEOUT = 8.0


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    client: BBHomeClient = data["client"]
    coordinator = data["coordinator"]
    raw_switch_count = config_value(entry, CONF_RAW_SWITCH_COUNT, 0)
    raw_dimmer_count = config_value(entry, CONF_RAW_DIMMER_COUNT, 0)
    if raw_switch_count or raw_dimmer_count:
        entities = [
            *[BBHomeRawSwitchLight(coordinator, client, address) for address in range(1, raw_switch_count + 1)],
            *[BBHomeRawDimmerLight(coordinator, client, address) for address in range(1, raw_dimmer_count + 1)],
        ]
    else:
        entities = [
            BBHomeLight(coordinator, client, button)
            for button in client.buttons
            if button.name and button.function_type in {"S", "F", "D"}
        ]
    async_add_entities(entities)


class _OptimisticLightState:
    _optimistic_until: float | None = None
    _optimistic_is_on: bool | None = None
    _optimistic_brightness: int | None = None

    @property
    def is_on(self) -> bool:
        return self._optimistic_is_on if self._optimistic_active else self._actual_is_on

    @property
    def brightness(self) -> int | None:
        actual_brightness = self._actual_brightness
        if actual_brightness is None:
            return None
        if self._optimistic_active and self._optimistic_brightness is not None:
            return self._optimistic_brightness
        return actual_brightness

    @property
    def _optimistic_active(self) -> bool:
        if self._optimistic_until is None or self._optimistic_is_on is None:
            return False
        if monotonic() >= self._optimistic_until:
            self._clear_optimistic()
            return False
        if self._actual_is_on == self._optimistic_is_on:
            if self._optimistic_brightness is None or self._actual_brightness == self._optimistic_brightness:
                self._clear_optimistic()
                return False
        return True

    def _set_optimistic(self, is_on: bool, brightness: int | None = None) -> None:
        self._optimistic_until = monotonic() + _OPTIMISTIC_TIMEOUT
        self._optimistic_is_on = is_on
        self._optimistic_brightness = brightness
        self.async_write_ha_state()

    def _clear_optimistic(self) -> None:
        self._optimistic_until = None
        self._optimistic_is_on = None
        self._optimistic_brightness = None


class BBHomeLight(_OptimisticLightState, CoordinatorEntity, LightEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, client: BBHomeClient, button: BBHomeButton) -> None:
        super().__init__(coordinator)
        self._client = client
        self._button = button
        self._attr_unique_id = f"bbhome_{button.unique_id}"
        self._attr_name = button.full_name
        if self._is_dimmer:
            self._attr_supported_color_modes = {ColorMode.BRIGHTNESS}
            self._attr_color_mode = ColorMode.BRIGHTNESS
        else:
            self._attr_supported_color_modes = {ColorMode.ONOFF}
            self._attr_color_mode = ColorMode.ONOFF

    @property
    def _is_dimmer(self) -> bool:
        return self._button.function_type == "D" or self._button.feedback_type == "D"

    @property
    def supported_color_modes(self) -> set[ColorMode]:
        return {ColorMode.BRIGHTNESS} if self._is_dimmer else {ColorMode.ONOFF}

    @property
    def color_mode(self) -> ColorMode:
        return ColorMode.BRIGHTNESS if self._is_dimmer else ColorMode.ONOFF

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, f"room_{self._button.room}")},
            "manufacturer": "Bits & Bites",
            "name": self._button.room_name,
        }

    @property
    def _actual_is_on(self) -> bool:
        return self._button.is_on

    @property
    def _actual_brightness(self) -> int | None:
        if not self._is_dimmer:
            return None
        return round(self._button.dim_value / DIMMER_MAX * 255)

    async def async_turn_on(self, **kwargs) -> None:
        if self._is_dimmer:
            brightness = kwargs.get("brightness", 255)
            value = round(brightness / 255 * DIMMER_MAX)
            await self._client.set_dim(self._button, value)
            self._set_optimistic(value > 0, round(value / DIMMER_MAX * 255))
        elif not self.is_on:
            await self._client.send_button(self._button)
            self._set_optimistic(True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs) -> None:
        if self._is_dimmer:
            await self._client.set_dim(self._button, 0)
            self._set_optimistic(False, 0)
        elif self.is_on:
            await self._client.send_button(self._button)
            self._set_optimistic(False)
        await self.coordinator.async_request_refresh()


class BBHomeRawSwitchLight(_OptimisticLightState, CoordinatorEntity, LightEntity):
    _attr_has_entity_name = True
    _attr_supported_color_modes = {ColorMode.ONOFF}
    _attr_color_mode = ColorMode.ONOFF

    def __init__(self, coordinator, client: BBHomeClient, address: int) -> None:
        super().__init__(coordinator)
        self._client = client
        self._address = address
        self._attr_unique_id = f"bbhome_raw_s_{address:03d}"
        self._attr_name = f"S {address:03d}"

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, "raw_switches")},
            "manufacturer": "Bits & Bites",
            "name": "B&B Home Raw Switches",
        }

    @property
    def _actual_is_on(self) -> bool:
        return self._client.raw_switch_states.get(self._address, False)

    @property
    def _actual_brightness(self) -> int | None:
        return None

    async def async_turn_on(self, **kwargs) -> None:
        if not self.is_on:
            await self._client.toggle_raw_switch(self._address)
            self._set_optimistic(True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs) -> None:
        if self.is_on:
            await self._client.toggle_raw_switch(self._address)
            self._set_optimistic(False)
        await self.coordinator.async_request_refresh()


class BBHomeRawDimmerLight(_OptimisticLightState, CoordinatorEntity, LightEntity):
    _attr_has_entity_name = True
    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}
    _attr_color_mode = ColorMode.BRIGHTNESS

    def __init__(self, coordinator, client: BBHomeClient, address: int) -> None:
        super().__init__(coordinator)
        self._client = client
        self._address = address
        self._attr_unique_id = f"bbhome_raw_d_{address:03d}"
        self._attr_name = f"D {address:03d}"

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, "raw_dimmers")},
            "manufacturer": "Bits & Bites",
            "name": "B&B Home Raw Dimmers",
        }

    @property
    def _actual_is_on(self) -> bool:
        return self._client.raw_dimmer_values.get(self._address, 0) > 0

    @property
    def _actual_brightness(self) -> int:
        return round(self._client.raw_dimmer_values.get(self._address, 0) / DIMMER_MAX * 255)

    async def async_turn_on(self, **kwargs) -> None:
        brightness = kwargs.get("brightness", 255)
        value = round(brightness / 255 * DIMMER_MAX)
        await self._client.set_raw_dimmer(self._address, value)
        self._set_optimistic(value > 0, round(value / DIMMER_MAX * 255))
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs) -> None:
        await self._client.set_raw_dimmer(self._address, 0)
        self._set_optimistic(False, 0)
        await self.coordinator.async_request_refresh()
