"""Support for SberDevices lights with coordinator."""

from __future__ import annotations

import math

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_HS_COLOR,
    ColorMode,
    LightEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util.color import brightness_to_value, value_to_brightness
from homeassistant.util.scaling import scale_ranged_value_to_int_range

from .api import DeviceAPI
from .const import DOMAIN

H_RANGE = (0, 360)
S_RANGE = (0, 100)


def get_color_temp_range(device_type: str) -> tuple[int, int]:
    """Return the color temperature range for device type."""
    return {
        "ledstrip": (2000, 6500),
        "bulb": (2700, 6500),
        "night_lamp": (2700, 6500),
    }.get(device_type, (2700, 6500))


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up lights from a config entry using the coordinator."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    home = data["home"]

    light_types = ("bulb", "ledstrip", "night_lamp")
    entities = []

    for device in coordinator.data.values():
        if any(t in device["image_set_type"] for t in light_types):
            device_type = next(t for t in light_types if t in device["image_set_type"])
            api = DeviceAPI(home, device["id"])
            entities.append(SberLightEntity(coordinator, api, device_type))

    async_add_entities(entities)


class SberLightEntity(CoordinatorEntity, LightEntity):
    """Sber light entity."""

    def __init__(self, coordinator, api: DeviceAPI, device_type: str) -> None:
        super().__init__(coordinator)
        self._api = api
        self._hs_color: tuple[float, float] | None = None
        self._real_color_temp_range = get_color_temp_range(device_type)

    @property
    def unique_id(self) -> str:
        return self._api.device["id"]

    @property
    def name(self) -> str:
        return self._api.device["name"]["name"]

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._api.device["serial_number"])},
            name=self.name,
            manufacturer=self._api.device["device_info"]["manufacturer"],
            model=self._api.device["device_info"]["model"],
            sw_version=self._api.device["sw_version"],
            serial_number=self._api.device["serial_number"],
        )

    @property
    def is_on(self) -> bool:
        return self._api.get_state("on_off")["bool_value"]

    @property
    def supported_color_modes(self) -> set[ColorMode]:
        light_mode = self._api.get_attribute("light_mode")["enum_values"]["values"]
        modes: set[ColorMode] = set()
        if "colour" in light_mode:
            modes.add(ColorMode.HS)
        if "white" in light_mode:
            modes.add(ColorMode.COLOR_TEMP)
        if not modes:
            modes.add(ColorMode.ONOFF)
        return modes

    @property
    def color_mode(self) -> ColorMode:
        mode = self._api.get_state("light_mode")["enum_value"]
        if mode == "colour":
            return ColorMode.HS
        if mode == "white":
            return ColorMode.COLOR_TEMP
        return ColorMode.ONOFF

    @property
    def brightness_range(self) -> tuple[int, int]:
        br_range = self._api.get_attribute("light_brightness")["int_values"]["range"]
        return br_range["min"], br_range["max"]

    @property
    def brightness(self) -> int | None:
        if self.color_mode not in (ColorMode.HS, ColorMode.COLOR_TEMP):
            return None
        if self.color_mode == ColorMode.HS:
            v = self._api.get_state("light_colour")["color_value"]["v"]
            return value_to_brightness(self.color_range["v"], v)
        b = int(self._api.get_state("light_brightness")["integer_value"])
        return value_to_brightness(self.brightness_range, b)

    @property
    def min_color_temp_kelvin(self) -> int:
        return self._real_color_temp_range[0]

    @property
    def max_color_temp_kelvin(self) -> int:
        return self._real_color_temp_range[1]

    @property
    def color_temp_range(self) -> tuple[int, int]:
        r = self._api.get_attribute("light_colour_temp")["int_values"]["range"]
        return r["min"], r["max"]

    @property
    def color_temp_kelvin(self) -> int | None:
        if self.color_mode != ColorMode.COLOR_TEMP:
            return None
        val = int(self._api.get_state("light_colour_temp")["integer_value"])
        return scale_ranged_value_to_int_range(
            self.color_temp_range, self._real_color_temp_range, val
        )

    @property
    def color_range(self) -> dict[str, tuple[int, int]]:
        c = self._api.get_attribute("light_colour")["color_values"]
        return {
            "h": (c["h"]["min"], c["h"]["max"]),
            "s": (c["s"]["min"], c["s"]["max"]),
            "v": (c["v"]["min"], c["v"]["max"]),
        }

    @property
    def hs_color(self) -> tuple[float, float] | None:
        if self.color_mode != ColorMode.HS:
            return None
        if self._hs_color is not None:
            return self._hs_color
        c = self._api.get_state("light_colour")["color_value"]
        return (
            scale_ranged_value_to_int_range(self.color_range["h"], H_RANGE, c["h"]),
            scale_ranged_value_to_int_range(self.color_range["s"], S_RANGE, c["s"]),
        )

    async def async_turn_on(self, **kwargs) -> None:
        states = [{"key": "on_off", "bool_value": True}]

        if ATTR_BRIGHTNESS in kwargs:
            b = kwargs[ATTR_BRIGHTNESS]
            states.append(
                {"key": "light_brightness", "integer_value": math.ceil(
                    brightness_to_value(self.brightness_range, b)
                )}
            )

        if ATTR_COLOR_TEMP_KELVIN in kwargs:
            t = scale_ranged_value_to_int_range(
                self._real_color_temp_range,
                self.color_temp_range,
                kwargs[ATTR_COLOR_TEMP_KELVIN],
            )
            states.extend((
                {"key": "light_mode", "enum_value": "white"},
                {"key": "light_colour_temp", "integer_value": t},
            ))

        if ATTR_HS_COLOR in kwargs:
            h, s = kwargs[ATTR_HS_COLOR]
            states.extend((
                {"key": "light_mode", "enum_value": "colour"},
                {"key": "light_colour",
                 "color_value": {
                     "h": scale_ranged_value_to_int_range(H_RANGE, self.color_range["h"], h),
                     "s": scale_ranged_value_to_int_range(S_RANGE, self.color_range["s"], s),
                     "v": math.ceil(brightness_to_value(self.color_range["v"], self.brightness or 255))
                 }}
            ))

        await self._api.set_states(states)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs) -> None:
        await self._api.set_on_off(False)
        await self.coordinator.async_request_refresh()
