DOMAIN = "bbhome"

CONF_INIT_STRING = "init_string"
CONF_RAW_SWITCH_COUNT = "raw_switch_count"
CONF_RAW_INPUT_COUNT = "raw_input_count"
CONF_RAW_FUNCTION_COUNT = "raw_function_count"
CONF_RAW_DIMMER_COUNT = "raw_dimmer_count"
CONF_RAW_TEMPERATURE_COUNT = "raw_temperature_count"

DEFAULT_HOST = ""
DEFAULT_PORT = 2555
DEFAULT_INIT_STRING = "001"
DIMMER_MAX = 100
DEFAULT_RAW_SWITCH_COUNT = 0
DEFAULT_RAW_INPUT_COUNT = 0
DEFAULT_RAW_FUNCTION_COUNT = 0
DEFAULT_RAW_DIMMER_COUNT = 0
DEFAULT_RAW_TEMPERATURE_COUNT = 0

PLATFORMS = ["light", "climate", "media_player", "button", "binary_sensor"]


def config_value(entry, key: str, default=None):
    return entry.options.get(key, entry.data.get(key, default))
