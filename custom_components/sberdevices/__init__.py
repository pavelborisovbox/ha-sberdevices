"""The SberDevices integration."""

from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .api import HomeAPI, SberAPI
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.LIGHT, Platform.SWITCH]


class SberCoordinator(DataUpdateCoordinator):
    """Coordinator to manage fetching SberDevices data."""

    def __init__(self, hass: HomeAssistant, home: HomeAPI):
        super().__init__(
            hass,
            _LOGGER,
            name="sberdevices",
            update_interval=timedelta(seconds=15),
        )
        self.home = home

    async def _async_update_data(self):
        """Fetch data from API."""
        try:
            await self.home.update_devices_cache()
            return self.home.get_cached_devices()
        except Exception as err:
            raise UpdateFailed(err) from err


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up SberDevices from a config entry."""

    hass.data.setdefault(DOMAIN, {})

    sber = SberAPI(token=entry.data["token"])
    home = HomeAPI(sber)

    coordinator = SberCoordinator(hass, home)

    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = {
        "sber": sber,
        "home": home,
        "coordinator": coordinator,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""

    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
