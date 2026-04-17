"""Constants for the zAI HA Agent integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "zai_ha_agent"

DEFAULT_CONVERSATION_NAME: Final = "zAI HA Agent"

CONF_CHAT_MODEL: Final = "chat_model"
CONF_MAX_TOKENS: Final = "max_tokens"
CONF_TEMPERATURE: Final = "temperature"
CONF_PROMPT: Final = "prompt"
CONF_LLM_HASS_API: Final = "llm_hass_api"
CONF_RECOMMENDED: Final = "recommended"

CONF_PERSONALITY: Final = "personality"
CONF_MEMORY_ENABLED: Final = "memory_enabled"
CONF_AREA_FILTER: Final = "area_filter"
CONF_USE_CUSTOM_PROMPT: Final = "use_custom_prompt"

PERSONALITY_FORMAL: Final = "formal"
PERSONALITY_FRIENDLY: Final = "friendly"
PERSONALITY_CONCISE: Final = "concise"

PERSONALITY_OPTIONS: Final = [
    PERSONALITY_FORMAL,
    PERSONALITY_FRIENDLY,
    PERSONALITY_CONCISE,
]

DEFAULT_BASE_URL: Final = "https://api.z.ai/api/coding/paas/v4"

DEFAULT: Final = {
    CONF_CHAT_MODEL: "glm-5.1",
    CONF_MAX_TOKENS: 3000,
    CONF_TEMPERATURE: 0.7,
    CONF_RECOMMENDED: True,
    CONF_PERSONALITY: PERSONALITY_FRIENDLY,
    CONF_MEMORY_ENABLED: True,
    CONF_AREA_FILTER: [],
    CONF_USE_CUSTOM_PROMPT: True,
}

FALLBACK_MODELS: Final = [
    "glm-5.1",
    "glm-5",
    "glm-5-turbo",
    "glm-4.7",
    "glm-4.7-flashx",
    "glm-4.7-flash",
    "glm-4.6",
    "glm-4.5-air",
    "glm-4.5-airx",
    "glm-4.5-flash",
    "glm-4-long",
    "glm-4-flashx-250414",
    "glm-4-flash-250414",
]

MODELS_ENDPOINT_PATH: Final = "/api/paas/v4/models"
MODELS_CACHE_KEY: Final = "available_models"

SUBENTRY_CONVERSATION: Final = "conversation"

MEMORY_KEY: Final = "memory"
