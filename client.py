from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field

from .const import DIMMER_MAX

_LOGGER = logging.getLogger(__name__)


@dataclass
class BBHomeButton:
    room: int
    slot: int
    room_name: str
    name: str
    function: str
    feedback: str
    is_on: bool = False
    dim_value: int = 0

    @property
    def unique_id(self) -> str:
        return f"button_{self.room}_{self.slot}_{self.function or self.feedback}"

    @property
    def full_name(self) -> str:
        return f"{self.room_name} {self.name}".strip()

    @property
    def function_type(self) -> str:
        return _suffix(self.function)

    @property
    def feedback_type(self) -> str:
        return _suffix(self.feedback)

    @property
    def function_address(self) -> int | None:
        return _address(self.function)

    @property
    def feedback_address(self) -> int | None:
        return _address(self.feedback)


@dataclass
class BBHomeTemperature:
    index: int
    room_name: str = ""
    name: str = ""
    controllable: bool = False
    active: bool = False
    mode: str = "OFF"
    current: float | None = None
    target: float | None = None

    @property
    def unique_id(self) -> str:
        return f"temperature_{self.index + 1}"

    @property
    def full_name(self) -> str:
        return self.name or f"{self.room_name} thermostat".strip() or f"Temperature {self.index + 1}"


@dataclass
class BBHomeAudioSource:
    name: str
    buttons: list[str] = field(default_factory=list)
    active: bool = False


@dataclass
class BBHomeAudioRoom:
    room: int
    number: int
    name: str
    sources: list[BBHomeAudioSource] = field(default_factory=list)

    @property
    def unique_id(self) -> str:
        return f"audio_{self.number}_{self.room}"


class BBHomeClient:
    def __init__(self, host: str, port: int, init_string: str, password: str) -> None:
        self.host = host
        self.port = port
        self.init_string = init_string
        self.password = password or ""
        self.rooms: list[str] = []
        self.buttons: list[BBHomeButton] = []
        self.temperatures: list[BBHomeTemperature] = [BBHomeTemperature(i) for i in range(84)]
        self.audio_rooms: list[BBHomeAudioRoom] = []
        self.raw_switch_states: dict[int, bool] = {}
        self.raw_input_states: dict[int, bool] = {}
        self.raw_function_states: dict[int, bool] = {}
        self.raw_dimmer_values: dict[int, int] = {}
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._buffer = ""
        self._lock = asyncio.Lock()

    async def async_close(self) -> None:
        if self._writer is not None:
            self._writer.close()
            await self._writer.wait_closed()
        self._reader = None
        self._writer = None

    async def async_update(self) -> "BBHomeClient":
        async with self._lock:
            await self._ensure_connected()
            await self._read_available(5.0 if not self.buttons else 0.2)
            return self

    async def send_button(self, button: BBHomeButton) -> None:
        kind = button.function_type
        address = button.function_address
        if address is None:
            return
        if kind == "F":
            await self.pulse_raw_function(address)
        elif kind == "S":
            await self.toggle_raw_switch(address)
        elif kind == "D":
            value = DIMMER_MAX if button.dim_value <= 0 else 0
            await self.set_dim(button, value)

    async def set_dim(self, button: BBHomeButton, value: int) -> None:
        address = button.function_address
        if address is not None:
            await self.set_raw_dimmer(address, value)

    async def toggle_raw_switch(self, address: int) -> None:
        await self._write(f"$#S{address:03d}XXX")

    async def pulse_raw_function(self, address: int) -> None:
        await self._write(f"$#K{address:03d}XXX")

    async def set_raw_dimmer(self, address: int, value: int) -> None:
        await self._write(f"$#D{address:03d}{max(0, min(DIMMER_MAX, value)):03d}")

    async def raw_temperature_step(self, address: int, command: str) -> None:
        await self._write(f"$#T{address:03d}{command}")

    async def temperature_step(self, temperature: BBHomeTemperature, command: str) -> None:
        await self.raw_temperature_step(temperature.index + 1, command)

    async def select_audio_source(self, audio_room: BBHomeAudioRoom, source_index: int) -> None:
        # The Android app maps audio source/control buttons onto the generic input command range.
        await self._write(f"$#I{audio_room.room * 368 + source_index * 46:04d}XX")

    async def audio_button(self, code: str) -> None:
        if code.isdigit():
            await self._write(f"$#I{int(code):04d}XX")

    async def audio_control(self, audio_room: BBHomeAudioRoom, audio_source: BBHomeAudioSource, icon_number: str) -> None:
        for source_index, source in enumerate(audio_room.sources):
            if source is not audio_source:
                continue
            for button_index, button_icon in enumerate(source.buttons):
                if button_icon == icon_number:
                    await self.audio_button(str(audio_room.room * 368 + source_index * 46 + button_index + 1))
                    return

    async def _ensure_connected(self) -> None:
        if self._writer is not None and not self._writer.is_closing():
            return
        self._reader, self._writer = await asyncio.wait_for(
            asyncio.open_connection(self.host, self.port), timeout=5
        )
        data = await asyncio.wait_for(self._reader.read(20000), timeout=5)
        self._buffer += data.decode("utf-8", "replace").strip()
        await self._write_now(self._login_command())

    def _login_command(self) -> str:
        if not self.password:
            return f"$#L{self.init_string}PD+"
        # Passworded logins are supported by the APK but not implemented until a sample is available.
        return f"$#L{self.init_string}PD+"

    async def _write(self, value: str) -> None:
        async with self._lock:
            await self._ensure_connected()
            await self._write_now(value)

    async def _write_now(self, value: str) -> None:
        assert self._writer is not None
        _LOGGER.debug("BBHome send: %s", value)
        self._writer.write(value.encode("utf-8"))
        await self._writer.drain()

    async def _read_available(self, timeout: float) -> None:
        assert self._reader is not None
        end = asyncio.get_running_loop().time() + timeout
        while asyncio.get_running_loop().time() < end:
            try:
                data = await asyncio.wait_for(self._reader.read(20000), timeout=0.2)
            except TimeoutError:
                continue
            if not data:
                await self.async_close()
                break
            self._buffer += data.decode("utf-8", "replace").strip("\x00\r\n ")
            self._parse_buffer()

    def _parse_buffer(self) -> None:
        while "$#PDAINI$#" in self._buffer and "$#PDAINIEND$#" in self._buffer:
            start = self._buffer.index("$#PDAINI$#")
            end = self._buffer.index("$#PDAINIEND$#") + len("$#PDAINIEND$#")
            self._parse_init(self._buffer[start:end])
            self._buffer = self._buffer[end:]
        while "$#PDAAUD$#" in self._buffer and "$#PDAAUDEND$#" in self._buffer:
            start = self._buffer.index("$#PDAAUD$#")
            end = self._buffer.index("$#PDAAUDEND$#") + len("$#PDAAUDEND$#")
            self._parse_audio(self._buffer[start:end])
            self._buffer = self._buffer[end:]
        while "DaTa" in self._buffer and "END" in self._buffer[self._buffer.index("DaTa"):]:
            start = self._buffer.index("DaTa")
            end = self._buffer.index("END", start) + len("END")
            self._parse_data(self._buffer[start:end])
            self._buffer = self._buffer[end:]

    def _parse_init(self, frame: str) -> None:
        parts = frame.split("$#")
        if len(parts) < 334:
            return
        rooms: list[str] = []
        room_temps: list[tuple[int, int]] = []
        for i in range(10):
            base = 3 + i * 3
            rooms.append(parts[base][2:].strip())
            room_temps.append((_int(parts[base + 1][2:]), _int(parts[base + 2][2:])))
        buttons: list[BBHomeButton] = []
        for room in range(10):
            for slot in range(10):
                idx = room * 10 + slot
                base = 33 + idx * 3
                function = parts[base][3:].strip()
                name = parts[base + 1][3:].strip()
                feedback = parts[base + 2][3:].strip()
                if name or function or feedback:
                    button = BBHomeButton(room, slot, rooms[room], name, function, feedback)
                    buttons.append(button)
        self.rooms = rooms
        self.buttons = buttons
        _LOGGER.debug("Discovered %s BBHome rooms and %s buttons", len(self.rooms), len(self.buttons))
        for room, (temp1, temp2) in enumerate(room_temps):
            for temp_index in (temp1, temp2):
                if 0 < temp_index <= len(self.temperatures):
                    self.temperatures[temp_index - 1].room_name = rooms[room]
            if 0 < temp2 <= len(self.temperatures):
                temperature = self.temperatures[temp2 - 1]
                temperature.controllable = True
                temperature.name = f"{rooms[room]} thermostat"

    def _parse_audio(self, frame: str) -> None:
        body = frame.removeprefix("$#PDAAUD$#").removesuffix("$#PDAAUDEND$#")
        audio_rooms: list[BBHomeAudioRoom] = []
        chunks = re.split(r"#<R\d", body)[1:]
        for room_index, chunk in enumerate(chunks):
            match = re.match(r"#<(-?\d+)", chunk)
            if not match:
                continue
            number = int(match.group(1))
            if number < 0:
                continue
            source_chunks = re.split(r"#<S\d", chunk)[1:]
            sources: list[BBHomeAudioSource] = []
            for source_chunk in source_chunks:
                if "#<B#<" not in source_chunk:
                    continue
                name, buttons = source_chunk.split("#<B#<", 1)
                name = name.replace("#<", "").strip()
                if name:
                    sources.append(BBHomeAudioSource(name=name, buttons=_split_fixed(buttons, 3)))
            audio_rooms.append(BBHomeAudioRoom(room_index, number, self.rooms[room_index], sources))
        self.audio_rooms = audio_rooms
        _LOGGER.debug("Discovered %s BBHome audio rooms", len(self.audio_rooms))

    def _parse_data(self, frame: str) -> None:
        sections = _sections(frame, [
            "OUTP", "INPU", "GALI", "DIMM", "TEMM", "TEMI", "AMOT", "CAML", "MUSI", "COMS", "TIMS", "INDI", "TOGL", "MEDP", "TEXE", "MEL1", "MEL2", "END"
        ])
        self.raw_switch_states = _bool_map(sections.get("OUTP", ""))
        self.raw_input_states = _bool_map(sections.get("INPU", ""))
        self.raw_function_states = _bool_map(sections.get("COMS", ""))
        self.raw_dimmer_values = {
            index + 1: value for index, value in enumerate(_dim_values(sections.get("DIMM", "")))
        }
        for button in self.buttons:
            ftype = button.feedback_type
            address = button.feedback_address
            if not address:
                continue
            if ftype == "S":
                button.is_on = _bool_at(sections.get("OUTP", ""), address)
            elif ftype == "I":
                button.is_on = _bool_at(sections.get("INPU", ""), address)
            elif ftype == "D":
                values = _dim_values(sections.get("DIMM", ""))
                if address - 1 < len(values):
                    button.dim_value = values[address - 1]
                    button.is_on = button.dim_value > 0
            elif ftype == "F":
                button.is_on = _bool_at(sections.get("COMS", ""), address)
            elif ftype == "T":
                button.is_on = _bool_at(sections.get("TIMS", ""), address)
        temm = _temperatures(sections.get("TEMM", ""), measured=True)
        temi = _temperatures(sections.get("TEMI", ""), measured=False)
        modes = sections.get("AMOT", "")
        for i, temp in enumerate(self.temperatures):
            if i < len(temm) and temm[i] is not None:
                temp.current = temm[i]
                temp.active = True
            if i < len(temi) and temi[i] is not None:
                temp.target = temi[i]
            if i < len(modes):
                temp.mode = {"0": "OFF", "1": "AUTO", "2": "MAN", "X": "OFF"}.get(modes[i], temp.mode)
        music = sections.get("MUSI", "")
        for idx, source_index in enumerate(music[:16]):
            if not source_index.isdigit():
                continue
            for audio_room in self.audio_rooms:
                if audio_room.number == idx:
                    for source in audio_room.sources:
                        source.active = False
                    selected = int(source_index)
                    if selected < len(audio_room.sources):
                        audio_room.sources[selected].active = True


def _suffix(value: str) -> str:
    return value[-1:] if value else ""


def _address(value: str) -> int | None:
    match = re.match(r"(\d+)", value or "")
    return int(match.group(1)) if match else None


def _int(value: str) -> int:
    try:
        return int(value)
    except ValueError:
        return 0


def _split_every(value: str, size: int) -> list[str]:
    return [value[i : i + size] for i in range(0, len(value), size) if value[i : i + size].strip("0")]


def _sections(frame: str, markers: list[str]) -> dict[str, str]:
    positions = [(marker, frame.find(marker)) for marker in markers if frame.find(marker) >= 0]
    positions.sort(key=lambda item: item[1])
    result: dict[str, str] = {}
    for index, (marker, pos) in enumerate(positions[:-1]):
        next_pos = positions[index + 1][1]
        result[marker] = frame[pos + len(marker) : next_pos]
    return result


def _bool_at(hex_string: str, one_based_index: int) -> bool:
    bits = _bits(hex_string)
    index = one_based_index - 1
    return index < len(bits) and bits[index] == "1"


def _bool_map(hex_string: str) -> dict[int, bool]:
    return {index + 1: bit == "1" for index, bit in enumerate(_bits(hex_string))}


def _bits(hex_string: str) -> str:
    return "".join(
        format(int(char, 16), "04b")[::-1] if char.upper() != "X" else "0000"
        for char in hex_string
        if char.upper() in "0123456789ABCDEFX"
    )


def _dim_values(hex_string: str) -> list[int]:
    values: list[int] = []
    for part in re.findall(r"..", hex_string):
        if "X" in part.upper():
            values.append(0)
        else:
            values.append(int(int(part, 16) / 2.55))
    return values


def _temperatures(value: str, measured: bool) -> list[float | None]:
    temps: list[float | None] = []
    for part in _split_fixed(value, 5):
        if part == "XXXXX" or len(part) < 5:
            temps.append(None)
            continue
        sign = -1 if part[0] == "-" else 1
        if measured:
            temps.append(sign * (int(part[1:5]) / 47.0))
        else:
            temps.append(sign * (int(part[1:4]) + int(part[4:5]) / 10.0))
    return temps


def _split_fixed(value: str, size: int) -> list[str]:
    return [value[i : i + size] for i in range(0, len(value), size)]
