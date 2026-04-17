"""Conversation entity for zAI HA Agent integration."""

from __future__ import annotations

from collections.abc import Iterable
import json
import logging
import re
from typing import Any, Literal

import openai
import voluptuous_openapi

from homeassistant.components import conversation
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import llm
from homeassistant.helpers.entity_platform import AddEntitiesCallback

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
    DOMAIN,
    MEMORY_KEY,
)
from .device_manager import DeviceContextBuilder
from .prompt_templates import build_system_prompt

_LOGGER = logging.getLogger(__name__)

MAX_TOOL_ITERATIONS = 10


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up conversation entities."""
    memory = None
    if hass.data.get(DOMAIN) and hass.data[DOMAIN].get(config_entry.entry_id):
        memory = hass.data[DOMAIN][config_entry.entry_id].get(MEMORY_KEY)

    async_add_entities([ZaiConversationEntity(config_entry, hass, memory)])


def _format_tool(
    tool: llm.Tool, custom_serializer: Any | None = None
) -> dict[str, Any]:
    """Format tool for OpenAI-compatible z.ai API."""
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description or "",
            "parameters": voluptuous_openapi.convert(
                tool.parameters, custom_serializer=custom_serializer
            ),
        },
    }


def _convert_content(
    chat_content: Iterable[conversation.Content],
) -> list[dict[str, Any]]:
    """Transform HA chat_log content into OpenAI-compatible message format.

    SystemContent is extracted separately and injected as a system message.
    """
    messages: list[dict[str, Any]] = []

    for content in chat_content:
        if isinstance(content, conversation.SystemContent):
            continue

        if isinstance(content, conversation.UserContent):
            if not messages or messages[-1]["role"] != "user":
                messages.append({
                    "role": "user",
                    "content": content.content or "",
                })
            else:
                existing = messages[-1]["content"]
                if isinstance(existing, str):
                    messages[-1]["content"] = existing + "\n" + (content.content or "")
                else:
                    messages[-1]["content"] = str(existing) + "\n" + (content.content or "")

        elif isinstance(content, conversation.AssistantContent):
            if not messages or messages[-1]["role"] != "assistant":
                msg: dict[str, Any] = {"role": "assistant", "content": content.content or ""}
                messages.append(msg)
            else:
                existing = messages[-1].get("content") or ""
                messages[-1]["content"] = existing + (content.content or "")

            if content.tool_calls:
                tool_calls_list = []
                for tool_call in content.tool_calls:
                    tool_name = getattr(tool_call, "tool_name", None) or getattr(tool_call, "name", "unknown")
                    tool_args = getattr(tool_call, "tool_args", None) or getattr(tool_call, "args", {})
                    tool_id = getattr(tool_call, "id", "unknown")
                    tool_calls_list.append({
                        "id": tool_id,
                        "type": "function",
                        "function": {
                            "name": tool_name,
                            "arguments": json.dumps(tool_args) if isinstance(tool_args, dict) else str(tool_args),
                        },
                    })
                if tool_calls_list:
                    messages[-1]["tool_calls"] = tool_calls_list
                    if not messages[-1].get("content"):
                        messages[-1]["content"] = None

        elif isinstance(content, conversation.ToolResultContent):
            tool_result = content.tool_result if content.tool_result else ""
            if isinstance(tool_result, dict):
                tool_result = json.dumps(tool_result)
            elif not isinstance(tool_result, str):
                tool_result = str(tool_result)

            messages.append({
                "role": "tool",
                "content": tool_result,
                "tool_call_id": content.tool_call_id,
            })

    return messages


async def _process_message(
    chat_log: conversation.ChatLog,
    response_message: Any,
    agent_id: str,
) -> None:
    """Transform an OpenAI response message into HA conversation content."""
    content_text = response_message.content or ""
    tool_calls = response_message.tool_calls

    if tool_calls:
        tool_inputs = []
        for tc in tool_calls:
            try:
                args = json.loads(tc.function.arguments) if isinstance(tc.function.arguments, str) else tc.function.arguments
            except (json.JSONDecodeError, TypeError):
                args = {}
            tool_inputs.append(
                llm.ToolInput(
                    tool_name=tc.function.name,
                    tool_args=args,
                    id=tc.id,
                )
            )
        async for _ in chat_log.async_add_assistant_content(
            conversation.AssistantContent(
                agent_id=agent_id,
                tool_calls=tool_inputs,
            )
        ):
            pass

    if content_text:
        chat_log.async_add_assistant_content_without_tools(
            conversation.AssistantContent(content=content_text, agent_id=agent_id)
        )

    if not content_text and not tool_calls:
        chat_log.async_add_assistant_content_without_tools(
            conversation.AssistantContent(
                content="Sorry, I couldn't get a response from the model.",
                agent_id=agent_id,
            )
        )


_MEMORY_PREFERENCE_PATTERNS = re.compile(
    r"(?:ricorda(?:ti)?|remember|nota(?:ti)?|note|salva|save|annota|preferisco|i prefer|mi piace|i like|"
    r"non mi piace|i don'?t like|la mia .+ (?:preferit[ao]|ideale|favorit[ae])|my (?:favorite|preferred|ideal))",
    re.IGNORECASE,
)

_MEMORY_NOTE_PATTERNS = re.compile(
    r"(?:ricordami|remind me|annotati|note to self|da ricordare|don'?t forget|non dimenticare|segna(?:ti)?)",
    re.IGNORECASE,
)


async def _extract_and_save_memory(
    memory: AssistantMemory,
    user_text: str,
) -> None:
    """Detect memory-related intents in user text and save to memory."""
    text = user_text.strip()
    if len(text) < 5:
        return

    try:
        if _MEMORY_NOTE_PATTERNS.search(text):
            await memory.add_note(text)
            _LOGGER.debug("Saved note from user: %s", text[:80])
        elif _MEMORY_PREFERENCE_PATTERNS.search(text):
            await memory.add_preference(text)
            _LOGGER.debug("Saved preference from user: %s", text[:80])
    except Exception:
        _LOGGER.debug("Failed to extract memory from user input", exc_info=True)


class ZaiConversationEntity(
    conversation.ConversationEntity,
    conversation.AbstractConversationAgent,
):
    """z.ai conversation agent."""

    _attr_supports_streaming = True
    _attr_has_entity_name = True
    _attr_name = "z.ai"

    def __init__(
        self,
        entry: ConfigEntry,
        hass: HomeAssistant,
        memory: AssistantMemory | None = None,
    ) -> None:
        """Initialize the conversation entity."""
        self.entry = entry
        self._attr_unique_id = entry.entry_id
        self._hass = hass
        self._memory = memory
        self._device_builder = DeviceContextBuilder(hass)

    @property
    def supported_languages(self) -> list[str] | Literal["*"]:
        """Return supported languages."""
        return "*"

    async def _async_handle_message(
        self,
        user_input: conversation.ConversationInput,
        chat_log: conversation.ChatLog,
    ) -> conversation.ConversationResult:
        """Handle a conversation message."""
        options = self.entry.options
        memory_enabled = options.get(CONF_MEMORY_ENABLED, DEFAULT[CONF_MEMORY_ENABLED])

        try:
            if self._memory and memory_enabled:
                await self._memory.record_interaction(user_input.text)
                await _extract_and_save_memory(self._memory, user_input.text)
        except Exception:
            _LOGGER.debug("Failed to process memory", exc_info=True)

        try:
            await chat_log.async_provide_llm_data(
                user_input.as_llm_context(DOMAIN),
                options.get(CONF_LLM_HASS_API),
                options.get(CONF_PROMPT),
                user_input.extra_system_prompt,
            )
        except conversation.ConverseError as err:
            return err.as_conversation_result()

        await self._async_handle_chat_log(chat_log)

        return conversation.async_get_result_from_chat_log(user_input, chat_log)

    async def _async_handle_chat_log(
        self,
        chat_log: conversation.ChatLog,
    ) -> None:
        """Process chat log with z.ai OpenAI-compatible API."""
        client: openai.AsyncOpenAI = self.entry.runtime_data
        options = self.entry.options

        if options.get(CONF_RECOMMENDED, True):
            model = DEFAULT[CONF_CHAT_MODEL]
            max_tokens = DEFAULT[CONF_MAX_TOKENS]
            temperature = DEFAULT[CONF_TEMPERATURE]
        else:
            model = options.get(CONF_CHAT_MODEL, DEFAULT[CONF_CHAT_MODEL])
            max_tokens = options.get(CONF_MAX_TOKENS, DEFAULT[CONF_MAX_TOKENS])
            temperature = options.get(CONF_TEMPERATURE, DEFAULT[CONF_TEMPERATURE])

        system_text = ""
        try:
            use_custom_prompt = options.get(CONF_USE_CUSTOM_PROMPT, DEFAULT[CONF_USE_CUSTOM_PROMPT])

            ha_system_text = ""
            if chat_log.content and isinstance(chat_log.content[0], conversation.SystemContent):
                ha_system_text = chat_log.content[0].content or ""

            if use_custom_prompt:
                personality = options.get(CONF_PERSONALITY, DEFAULT[CONF_PERSONALITY])

                area_filter = options.get(CONF_AREA_FILTER, DEFAULT[CONF_AREA_FILTER])
                devices_context = await self._device_builder.build_context(
                    area_filter=area_filter if area_filter else None,
                )

                memory_context = ""
                try:
                    if self._memory and options.get(CONF_MEMORY_ENABLED, DEFAULT[CONF_MEMORY_ENABLED]):
                        await self._memory.async_load()
                        memory_context = self._memory.build_memory_prompt()
                except Exception:
                    _LOGGER.debug("Failed to build memory context", exc_info=True)

                extra_instructions = options.get(CONF_PROMPT, "")

                custom_prompt = build_system_prompt(
                    personality=personality,
                    devices_context=devices_context,
                    memory_context=memory_context,
                    extra_instructions=extra_instructions,
                )

                if ha_system_text:
                    system_text = custom_prompt + "\n\n" + ha_system_text
                else:
                    system_text = custom_prompt
            else:
                system_text = ha_system_text
        except Exception:
            _LOGGER.warning("Failed to build custom system prompt, using fallback", exc_info=True)
            try:
                if chat_log.content and isinstance(chat_log.content[0], conversation.SystemContent):
                    system_text = chat_log.content[0].content or ""
            except Exception:
                _LOGGER.warning("Failed to get any system prompt", exc_info=True)

        api_messages: list[dict[str, Any]] = []

        if system_text:
            api_messages.append({"role": "system", "content": system_text})

        conversation_messages = _convert_content(chat_log.content[1:])

        if not conversation_messages:
            conversation_messages = [{"role": "user", "content": "Hello"}]

        api_messages.extend(conversation_messages)

        tools: list[dict[str, Any]] = []
        if chat_log.llm_api:
            tools = [
                _format_tool(tool, chat_log.llm_api.custom_serializer)
                for tool in chat_log.llm_api.tools
            ]

        model_args: dict[str, Any] = {
            "model": model,
            "messages": api_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        if tools:
            model_args["tools"] = tools
            model_args["tool_choice"] = "auto"

        for _iteration in range(MAX_TOOL_ITERATIONS):
            try:
                response = await client.chat.completions.create(**model_args)
                message = response.choices[0].message

                await _process_message(chat_log, message, self.entity_id)

            except openai.APIStatusError as err:
                raise HomeAssistantError(
                    f"Sorry, I had a problem talking to z.ai: {err}"
                ) from err
            except openai.APIConnectionError as err:
                raise HomeAssistantError(
                    f"Sorry, I couldn't connect to z.ai: {err}"
                ) from err
            except openai.APITimeoutError as err:
                raise HomeAssistantError(
                    f"Sorry, z.ai request timed out: {err}"
                ) from err

            if not chat_log.unresponded_tool_results:
                break

            api_messages = []
            if system_text:
                api_messages.append({"role": "system", "content": system_text})
            api_messages.extend(_convert_content(chat_log.content[1:]))
            model_args["messages"] = api_messages
