"""The zAI HA Agent integration."""

from __future__ import annotations

from functools import partial
import logging

import openai

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .assistant_memory import AssistantMemory
from .config_flow import async_fetch_available_models
from .const import DEFAULT_BASE_URL, DOMAIN, MEMORY_KEY, MODELS_CACHE_KEY

type ZaiConfigEntry = ConfigEntry[openai.AsyncOpenAI]

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.CONVERSATION]

__all__ = ["ZaiConfigEntry"]


async def async_setup_entry(hass: HomeAssistant, entry: ZaiConfigEntry) -> bool:
    """Set up zAI HA Agent from a config entry."""
    api_key = entry.data[CONF_API_KEY]
    base_url = DEFAULT_BASE_URL

    try:
        client = await hass.async_add_executor_job(
            partial(
                openai.AsyncOpenAI,
                api_key=api_key,
                base_url=base_url,
            )
        )
    except Exception as err:
        _LOGGER.exception("Error setting up z.ai client: %s", err)
        raise ConfigEntryNotReady from err

    entry.runtime_data = client

    if DOMAIN not in hass.data:
        hass.data[DOMAIN] = {}

    memory = AssistantMemory(hass, entry.entry_id)
    await memory.async_load()

    hass.data[DOMAIN][entry.entry_id] = {
        MEMORY_KEY: memory,
    }

    try:
        models = await async_fetch_available_models(hass, api_key)
        hass.data[DOMAIN][entry.entry_id][MODELS_CACHE_KEY] = models
    except Exception:
        _LOGGER.debug("Failed to fetch models during setup", exc_info=True)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        if DOMAIN in hass.data and entry.entry_id in hass.data[DOMAIN]:
            memory = hass.data[DOMAIN][entry.entry_id].get(MEMORY_KEY)
            if memory:
                await memory.async_save()
            hass.data[DOMAIN].pop(entry.entry_id)

        if DOMAIN in hass.data and not hass.data[DOMAIN]:
            hass.data.pop(DOMAIN)

    return unload_ok


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle removal of an entry."""
    if DOMAIN in hass.data and entry.entry_id in hass.data[DOMAIN]:
        memory = hass.data[DOMAIN][entry.entry_id].get(MEMORY_KEY)
        if memory:
            await memory.async_delete_storage()


async def async_remove_config_entry_device(
    hass: HomeAssistant, config_entry: ConfigEntry, device_entry
) -> bool:
    """Remove a config entry from a device."""
    return True
