from datetime import timedelta

from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import DOMAIN


class SberCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, home):
        super().__init__(
            hass,
            logger=hass.data[DOMAIN]["logger"],
            name="sberdevices",
            update_interval=timedelta(seconds=15),
        )

        self.home = home

    async def _async_update_data(self):
        try:
            await self.home.update_devices_cache()
            return self.home.get_cached_devices()
        except Exception as err:
            raise UpdateFailed(err)
