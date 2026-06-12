from __future__ import annotations

from homeassistant.components.media_player import MediaPlayerEntity
from homeassistant.components.media_player.const import MediaPlayerEntityFeature, MediaPlayerState
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .client import BBHomeAudioRoom, BBHomeClient
from .const import DOMAIN

POWER_ICON = "201"
VOLUME_DOWN_ICON = "237"
MUTE_ICON = "511"
VOLUME_UP_ICON = "238"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    client: BBHomeClient = data["client"]
    coordinator = data["coordinator"]
    async_add_entities([BBHomeMediaPlayer(coordinator, client, room) for room in client.audio_rooms])


class BBHomeMediaPlayer(CoordinatorEntity, MediaPlayerEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, client: BBHomeClient, audio_room: BBHomeAudioRoom) -> None:
        super().__init__(coordinator)
        self._client = client
        self._audio_room = audio_room
        self._attr_unique_id = f"bbhome_{audio_room.unique_id}"
        self._attr_name = f"{audio_room.name} Audio"

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, f"room_{self._audio_room.room}")},
            "manufacturer": "Bits & Bites",
            "name": self._audio_room.name,
        }

    @property
    def state(self) -> MediaPlayerState:
        return MediaPlayerState.ON if self.source else MediaPlayerState.OFF

    @property
    def supported_features(self) -> MediaPlayerEntityFeature:
        features = MediaPlayerEntityFeature.SELECT_SOURCE
        if self._has_control(POWER_ICON):
            features |= MediaPlayerEntityFeature.TURN_ON | MediaPlayerEntityFeature.TURN_OFF
        if self._has_control(VOLUME_UP_ICON) and self._has_control(VOLUME_DOWN_ICON):
            features |= MediaPlayerEntityFeature.VOLUME_STEP
        if self._has_control(MUTE_ICON):
            features |= MediaPlayerEntityFeature.VOLUME_MUTE
        return features

    @property
    def source_list(self) -> list[str]:
        return [source.name for source in self._audio_room.sources]

    @property
    def source(self) -> str | None:
        for source in self._audio_room.sources:
            if source.active:
                return source.name
        return None

    async def async_select_source(self, source: str) -> None:
        names = self.source_list
        if source in names:
            await self._client.select_audio_source(self._audio_room, names.index(source))
            await self.coordinator.async_request_refresh()

    async def async_turn_on(self) -> None:
        if self.source is None and self.source_list:
            await self.async_select_source(self.source_list[0])
            return
        await self._send_control(POWER_ICON)

    async def async_turn_off(self) -> None:
        await self._send_control(POWER_ICON)

    async def async_volume_up(self) -> None:
        await self._send_control(VOLUME_UP_ICON)

    async def async_volume_down(self) -> None:
        await self._send_control(VOLUME_DOWN_ICON)

    async def async_mute_volume(self, mute: bool) -> None:
        await self._send_control(MUTE_ICON)

    async def _send_control(self, icon_number: str) -> None:
        source = self._active_source()
        if source is not None and self._has_control(icon_number):
            await self._client.audio_control(self._audio_room, source, icon_number)
            await self.coordinator.async_request_refresh()

    def _has_control(self, icon_number: str) -> bool:
        source = self._active_source()
        return source is not None and icon_number in source.buttons

    def _active_source(self):
        for source in self._audio_room.sources:
            if source.active:
                return source
        return self._audio_room.sources[0] if self._audio_room.sources else None
