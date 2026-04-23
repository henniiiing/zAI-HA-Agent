"""Config flow for zAI HA Agent integration."""

from __future__ import annotations

from functools import partial
import logging
from typing import Any

import httpx
import openai
import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_API_KEY, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TemplateSelector,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .assistant_memory import AssistantMemory
from .const import (
    CONF_AREA_FILTER,
    CONF_CHAT_MODEL,
    CONF_LLM_HASS_API,
    CONF_MAX_TOKENS,
    CONF_MEMORY_ENABLED,
    CONF_PERSONALITY,
    CONF_PROMPT,
    CONF_RECOMMENDED,
    CONF_TEMPERATURE,
    CONF_USE_CUSTOM_PROMPT,
    DEFAULT,
    DEFAULT_BASE_URL,
    DEFAULT_CONVERSATION_NAME,
    DOMAIN,
    FALLBACK_MODELS,
    MEMORY_KEY,
    MODELS_CACHE_KEY,
    PERSONALITY_CONCISE,
    PERSONALITY_FORMAL,
    PERSONALITY_FRIENDLY,
    PERSONALITY_OPTIONS,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_API_KEY): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        ),
    }
)

RECOMMENDED_OPTIONS = {
    CONF_LLM_HASS_API: "assist",
    CONF_RECOMMENDED: True,
    CONF_PERSONALITY: DEFAULT[CONF_PERSONALITY],
    CONF_MEMORY_ENABLED: DEFAULT[CONF_MEMORY_ENABLED],
    CONF_USE_CUSTOM_PROMPT: DEFAULT[CONF_USE_CUSTOM_PROMPT],
}

MODELS_URL = "https://api.z.ai/api/paas/v4/models"


async def async_fetch_available_models(
    hass: HomeAssistant,
    api_key: str,
) -> list[str]:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                MODELS_URL,
                headers={"Authorization": f"Bearer {api_key}"},
            )
            response.raise_for_status()
            data = response.json()

        models = []
        for model_entry in data.get("data", []):
            model_id = model_entry.get("id", "")
            if model_id:
                models.append(model_id)

        if models:
            models.sort()
            _LOGGER.debug("Fetched %d models from %s", len(models), MODELS_URL)
            return models

    except Exception as err:
        _LOGGER.debug("Failed to fetch models from %s: %s", MODELS_URL, err)

    return list(FALLBACK_MODELS)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> None:
    """Validate the user input allows us to connect."""
    api_key = data[CONF_API_KEY]

    client = await hass.async_add_executor_job(
        partial(
            openai.AsyncOpenAI,
            api_key=api_key,
            base_url=DEFAULT_BASE_URL,
        )
    )

    try:
        await client.chat.completions.create(
            model="glm-5.1",
            max_tokens=10,
            messages=[{"role": "user", "content": "test"}],
            timeout=10.0,
        )
    except openai.AuthenticationError as err:
        _LOGGER.error("Authentication error: %s", err)
        raise
    except openai.APITimeoutError as err:
        _LOGGER.error("Timeout error: %s", err)
        raise
    except openai.APIConnectionError as err:
        _LOGGER.error("Connection error: %s", err)
        raise
    except openai.APIStatusError as err:
        _LOGGER.error("z.ai API error: %s", err)
        raise


class ZaiConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for zAI HA Agent."""

    VERSION = 1

    @staticmethod
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Get the options flow for this handler."""
        return ZaiOptionsFlowHandler()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                await validate_input(self.hass, user_input)
            except openai.APITimeoutError:
                errors["base"] = "timeout_connect"
            except openai.APIConnectionError:
                errors["base"] = "cannot_connect"
            except openai.AuthenticationError:
                errors["base"] = "authentication_error"
            except openai.APIStatusError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(
                    title="z.ai",
                    data=user_input,
                    options=RECOMMENDED_OPTIONS,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )


class ZaiOptionsFlowHandler(OptionsFlow):
    """Handle options flow for zAI HA Agent."""

    _init_data: dict[str, Any]

    async def _get_available_models(self) -> list[str]:
        entry_data = self.config_entry.data
        api_key = entry_data.get(CONF_API_KEY, "")

        domain_data = self.hass.data.get(DOMAIN, {})
        entry_data_cache = domain_data.get(self.config_entry.entry_id, {})

        cached = entry_data_cache.get(MODELS_CACHE_KEY)
        if cached:
            return cached

        models = await async_fetch_available_models(self.hass, api_key)

        if DOMAIN not in self.hass.data:
            self.hass.data[DOMAIN] = {}
        if self.config_entry.entry_id not in self.hass.data[DOMAIN]:
            self.hass.data[DOMAIN][self.config_entry.entry_id] = {}
        self.hass.data[DOMAIN][self.config_entry.entry_id][MODELS_CACHE_KEY] = models

        return models

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the options menu."""
        return self.async_show_menu(
            step_id="init",
            menu_options=["configure", "view_memory", "clear_memory"],
        )

    async def async_step_configure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle conversation agent configuration."""
        errors: dict[str, str] = {}

        if user_input is not None:
            if CONF_RECOMMENDED in user_input:
                recommended = user_input.pop(CONF_RECOMMENDED)
                if not recommended:
                    self._init_data = user_input
                    return await self.async_step_advanced()

            return self.async_create_entry(title="", data=user_input)

        schema_dict: dict[vol.Marker, Any] = {}
        options = self.config_entry.options or {}

        schema_dict[
            vol.Optional(
                CONF_PERSONALITY,
                default=options.get(CONF_PERSONALITY, DEFAULT[CONF_PERSONALITY]),
            )
        ] = SelectSelector(
            SelectSelectorConfig(
                mode=SelectSelectorMode.DROPDOWN,
                options=[
                    {"value": PERSONALITY_FORMAL, "label": "Formell"},
                    {"value": PERSONALITY_FRIENDLY, "label": "Freundlich"},
                    {"value": PERSONALITY_CONCISE, "label": "Kurz"},
                ],
                translation_key=CONF_PERSONALITY,
            )
        )

        schema_dict[
            vol.Optional(
                CONF_MEMORY_ENABLED,
                default=options.get(CONF_MEMORY_ENABLED, DEFAULT[CONF_MEMORY_ENABLED]),
            )
        ] = BooleanSelector()

        schema_dict[
            vol.Optional(
                CONF_USE_CUSTOM_PROMPT,
                default=options.get(CONF_USE_CUSTOM_PROMPT, DEFAULT[CONF_USE_CUSTOM_PROMPT]),
            )
        ] = BooleanSelector()

        schema_dict[vol.Optional(CONF_PROMPT, default=options.get(CONF_PROMPT, ""))] = (
            TemplateSelector()
        )

        schema_dict[
            vol.Optional(
                CONF_LLM_HASS_API,
                default=options.get(CONF_LLM_HASS_API, "assist"),
            )
        ] = SelectSelector(
            SelectSelectorConfig(
                mode=SelectSelectorMode.DROPDOWN,
                options=["none", "assist", "intent"],
            )
        )

        schema_dict[
            vol.Optional(
                CONF_RECOMMENDED,
                default=options.get(CONF_RECOMMENDED, True),
            )
        ] = BooleanSelector()

        return self.async_show_form(
            step_id="configure",
            data_schema=vol.Schema(schema_dict),
            errors=errors,
        )

    async def async_step_view_memory(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the assistant's persistent memory."""
        if user_input is not None:
            return await self.async_step_init()

        memory_content = ""
        domain_data = self.hass.data.get(DOMAIN, {})
        entry_data = domain_data.get(self.config_entry.entry_id, {})
        memory: AssistantMemory | None = entry_data.get(MEMORY_KEY)

        if memory:
            await memory.async_load()
            memory_content = memory.build_memory_prompt()
            if not memory_content.strip():
                memory_content = "No memory entries stored yet."
        else:
            memory_content = "Memory is not available for this entry."

        return self.async_show_form(
            step_id="view_memory",
            description_placeholders={"memory_content": memory_content},
        )

    async def async_step_clear_memory(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Clear the assistant's persistent memory."""
        if user_input is not None:
            if user_input.get("confirm_clear"):
                domain_data = self.hass.data.get(DOMAIN, {})
                entry_data = domain_data.get(self.config_entry.entry_id, {})
                memory: AssistantMemory | None = entry_data.get(MEMORY_KEY)
                if memory:
                    await memory.async_clear()
            return await self.async_step_init()

        return self.async_show_form(
            step_id="clear_memory",
            data_schema=vol.Schema({
                vol.Required("confirm_clear"): BooleanSelector(),
            }),
        )

    async def async_step_advanced(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle advanced configuration."""
        errors: dict[str, str] = {}

        if user_input is not None:
            init_data = getattr(self, "_init_data", {})
            return self.async_create_entry(
                title="",
                data={CONF_RECOMMENDED: False, **init_data, **user_input},
            )

        options = self.config_entry.options or {}

        available_models = await self._get_available_models()

        area_reg = ar.async_get(self.hass)
        area_options = [
            {"value": area.id, "label": area.name}
            for area in area_reg.async_list_areas()
        ]

        current_model = options.get(CONF_CHAT_MODEL, DEFAULT[CONF_CHAT_MODEL])
        model_options = available_models
        if current_model not in model_options:
            model_options = [current_model] + model_options

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_CHAT_MODEL,
                    default=current_model,
                ): (
                    SelectSelector(
                        SelectSelectorConfig(
                            mode=SelectSelectorMode.DROPDOWN,
                            options=model_options,
                            custom_value=True,
                        )
                    )
                ),
                vol.Optional(
                    CONF_MAX_TOKENS,
                    default=options.get(CONF_MAX_TOKENS, DEFAULT[CONF_MAX_TOKENS]),
                ): (
                    NumberSelector(
                        NumberSelectorConfig(
                            min=1,
                            max=8000,
                            mode=NumberSelectorMode.BOX,
                        )
                    )
                ),
                vol.Optional(
                    CONF_TEMPERATURE,
                    default=options.get(CONF_TEMPERATURE, DEFAULT[CONF_TEMPERATURE]),
                ): (
                    NumberSelector(
                        NumberSelectorConfig(
                            min=0,
                            max=1,
                            step=0.05,
                            mode=NumberSelectorMode.SLIDER,
                        )
                    )
                ),
                vol.Optional(
                    CONF_AREA_FILTER,
                    default=options.get(CONF_AREA_FILTER, DEFAULT[CONF_AREA_FILTER]),
                ): (
                    SelectSelector(
                        SelectSelectorConfig(
                            mode=SelectSelectorMode.DROPDOWN,
                            options=area_options,
                            multiple=True,
                        )
                    )
                    if area_options
                    else SelectSelector(
                        SelectSelectorConfig(
                            mode=SelectSelectorMode.DROPDOWN,
                            options=[],
                            multiple=True,
                        )
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="advanced",
            data_schema=schema,
            errors=errors,
        )
