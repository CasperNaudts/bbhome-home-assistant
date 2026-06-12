from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .client import BBHomeClient
from .const import CONF_RAW_FUNCTION_COUNT, DOMAIN, config_value


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    client: BBHomeClient = data["client"]
    coordinator = data["coordinator"]
    count = config_value(entry, CONF_RAW_FUNCTION_COUNT, 0)
    async_add_entities([BBHomeRawFunctionButton(coordinator, client, address) for address in range(1, count + 1)])


class BBHomeRawFunctionButton(CoordinatorEntity, ButtonEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, client: BBHomeClient, address: int) -> None:
        super().__init__(coordinator)
        self._client = client
        self._address = address
        self._attr_unique_id = f"bbhome_raw_f_{address:03d}"
        self._attr_name = f"F {address:03d}"

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, "raw_functions")},
            "manufacturer": "Bits & Bites",
            "name": "B&B Home Raw Functions",
        }

    async def async_press(self) -> None:
        await self._client.pulse_raw_function(self._address)
        await self.coordinator.async_request_refresh()
