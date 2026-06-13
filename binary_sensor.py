from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .client import BBHomeClient
from .const import CONF_RAW_INPUT_COUNT, DOMAIN, config_value


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    client: BBHomeClient = data["client"]
    coordinator = data["coordinator"]
    count = config_value(entry, CONF_RAW_INPUT_COUNT, 0)
    async_add_entities([BBHomeRawInputBinarySensor(coordinator, client, address) for address in range(1, count + 1)])


class BBHomeRawInputBinarySensor(CoordinatorEntity, BinarySensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, client: BBHomeClient, address: int) -> None:
        super().__init__(coordinator)
        self._client = client
        self._address = address
        self._attr_unique_id = f"bbhome_raw_i_{address:03d}"
        self._attr_name = f"I {address:03d}"

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, "raw_inputs")},
            "manufacturer": "Bits & Bites",
            "name": "B&B Home Raw Inputs",
        }

    @property
    def is_on(self) -> bool:
        return not self._client.raw_input_states.get(self._address, False)
