from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT

from .client import BBHomeClient
from .const import (
    CONF_INIT_STRING,
    CONF_RAW_DIMMER_COUNT,
    CONF_RAW_FUNCTION_COUNT,
    CONF_RAW_INPUT_COUNT,
    CONF_RAW_SWITCH_COUNT,
    CONF_RAW_TEMPERATURE_COUNT,
    DEFAULT_HOST,
    DEFAULT_INIT_STRING,
    DEFAULT_PORT,
    DEFAULT_RAW_DIMMER_COUNT,
    DEFAULT_RAW_FUNCTION_COUNT,
    DEFAULT_RAW_INPUT_COUNT,
    DEFAULT_RAW_SWITCH_COUNT,
    DEFAULT_RAW_TEMPERATURE_COUNT,
    DOMAIN,
)


def _data_schema(defaults: dict | None = None) -> vol.Schema:
    defaults = defaults or {}
    return vol.Schema(
        {
            vol.Required(CONF_HOST, default=defaults.get(CONF_HOST, DEFAULT_HOST)): str,
            vol.Required(CONF_PORT, default=defaults.get(CONF_PORT, DEFAULT_PORT)): int,
            vol.Required(CONF_INIT_STRING, default=defaults.get(CONF_INIT_STRING, DEFAULT_INIT_STRING)): str,
            vol.Optional(CONF_PASSWORD, default=defaults.get(CONF_PASSWORD, "")): str,
            vol.Required(CONF_RAW_SWITCH_COUNT, default=defaults.get(CONF_RAW_SWITCH_COUNT, DEFAULT_RAW_SWITCH_COUNT)): int,
            vol.Required(CONF_RAW_INPUT_COUNT, default=defaults.get(CONF_RAW_INPUT_COUNT, DEFAULT_RAW_INPUT_COUNT)): int,
            vol.Required(CONF_RAW_FUNCTION_COUNT, default=defaults.get(CONF_RAW_FUNCTION_COUNT, DEFAULT_RAW_FUNCTION_COUNT)): int,
            vol.Required(CONF_RAW_DIMMER_COUNT, default=defaults.get(CONF_RAW_DIMMER_COUNT, DEFAULT_RAW_DIMMER_COUNT)): int,
            vol.Required(
                CONF_RAW_TEMPERATURE_COUNT,
                default=defaults.get(CONF_RAW_TEMPERATURE_COUNT, DEFAULT_RAW_TEMPERATURE_COUNT),
            ): int,
        }
    )


class BBHomeConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @staticmethod
    def async_get_options_flow(config_entry):
        return BBHomeOptionsFlow(config_entry)

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            client = BBHomeClient(
                user_input[CONF_HOST],
                user_input[CONF_PORT],
                user_input[CONF_INIT_STRING],
                user_input.get(CONF_PASSWORD, ""),
            )
            try:
                await client.async_update()
            except Exception:
                errors["base"] = "cannot_connect"
            finally:
                await client.async_close()

            if not errors:
                await self.async_set_unique_id(f"{user_input[CONF_HOST]}:{user_input[CONF_PORT]}")
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title="B&B Home", data=user_input)

        return self.async_show_form(step_id="user", data_schema=_data_schema(), errors=errors)


class BBHomeOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        defaults = {**self._config_entry.data, **self._config_entry.options}
        return self.async_show_form(step_id="init", data_schema=_data_schema(defaults))
