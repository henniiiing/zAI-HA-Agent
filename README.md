# zAI HA Agent

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)
[![GitHub release](https://img.shields.io/github/v/release/henniiiing/zAI-HA-Agent)](https://github.com/henniiiing/zAI-HA-Agent/releases)

A Home Assistant custom integration that uses the **z.ai Coding Plan API** to power a personal home assistant with native function calling, persistent memory, and automatic device context.

Built on the **OpenAI-compatible** z.ai PaaS v4 Chat Completions API with the **GLM-5.1** model.

## Features

### Core
- **GLM-5.1** — z.ai's latest flagship model via Coding Plan API
- **Device control** — Voice and text commands with native HA function calling
- **Conversation Agent** — Full integration with Home Assistant's Assist system

### Personal Assistant
- **Persistent memory** — Remembers your preferences, notes, and context across sessions
- **Configurable personality** — Choose between Formal, Friendly, or Concise
- **Device context** — The LLM automatically receives the real state of lights, sensors, thermostats, and covers grouped by area
- **Area filter** — Limit context to only the areas you care about
- **Custom prompt** — Extra instructions to customize the assistant's behavior

## API

This integration uses the **z.ai Coding Plan API** endpoint:

```
https://api.z.ai/api/coding/paas/v4
```

This is an OpenAI-compatible Chat Completions API. The `openai` Python SDK is used for communication.

## Installation

### HACS (Recommended)

1. Open **HACS** in Home Assistant
2. Go to **Integrations**
3. Click the three dots in the top right corner and select **Custom repositories**
4. Add: `https://github.com/henniiiing/zAI-HA-Agent`
5. Category: **Integration**
6. Click **Add**
7. Search for "zAI HA Agent" and install it
8. **Restart Home Assistant**

### Manual Installation

1. Copy the `custom_components/zai_ha_agent` folder to your Home Assistant `custom_components` directory
2. Restart Home Assistant

## Configuration

### Getting Your API Key

1. Go to [z.ai](https://z.ai) and subscribe to the **Coding Plan**
2. Navigate to [API Keys](https://z.ai/manage-apikey/apikey-list)
3. Generate a new API key

### Setting Up the Integration

1. **Settings** > **Devices & Services** > **+ Add Integration**
2. Search for **"zAI HA Agent"**
3. Enter your **API Key**
4. Click **Submit** — a connection test will be performed

### Configuration Options

After installation, click **Configure** on the integration to see the options menu:

- **Configure** — Adjust integration settings
- **View Memory** — Browse the assistant's stored preferences, notes, and context
- **Clear Memory** — Permanently delete all stored memory

#### Basic Options

| Option | Description | Default |
|--------|-------------|---------|
| **Personality** | Response style (Formal / Friendly / Concise) | Friendly |
| **Memory** | Enable persistent memory across sessions | Enabled |
| **Optimized prompt** | Use advanced prompt with device context | Enabled |
| **Extra instructions** | Additional template to customize behavior | — |
| **Control HA** | API for device control (`assist` / `intent` / `none`) | `assist` |
| **Recommended settings** | Use optimized parameters for the model | Enabled |

#### Advanced Options (disable "Recommended settings")

| Option | Description | Default | Range |
|--------|-------------|---------|-------|
| **Model** | Model to use | glm-5.1 | — |
| **Max tokens** | Maximum response length | 3000 | 1–8000 |
| **Temperature** | Response creativity | 0.7 | 0–1 |
| **Area filter** | Limit context to devices in specific areas | All | Multi-select |

#### Memory Viewer

The **View Memory** option shows a read-only summary of everything the assistant has stored:
- User preferences (e.g. "I prefer warm lights in the evening")
- Notes (e.g. "Call the plumber tomorrow")
- Context key-value pairs
- Interaction stats

Use **Clear Memory** to wipe all stored data. A confirmation checkbox is required to prevent accidental deletion.

## Usage

### Natural Commands

With "Control Home Assistant" set to `assist`:

```
"Turn on the living room lights"
"Set the thermostat to 22 degrees"
"What's the temperature in the bedroom?"
"Close all the blinds"
"Set the kitchen light to 50%"
"Turn off everything in the bedroom"
```

### Assistant Memory

The assistant remembers your preferences across sessions:

```
"Remember that I prefer warm lights in the evening"
"My ideal temperature is 21 degrees"
"Note that I need to call the plumber tomorrow"
```

## Architecture

```
custom_components/zai_ha_agent/
├── __init__.py            # Entry point, OpenAI client and memory setup
├── conversation.py        # Main entity, chat and API handling
├── config_flow.py         # Configuration flow UI
├── const.py               # Constants and defaults
├── entity.py              # Base entity
├── device_manager.py      # Device context builder by area
├── assistant_memory.py    # JSON persistent memory
├── prompt_templates.py    # Personality templates and instructions
├── manifest.json
├── strings.json
└── translations/
    └── en.json
```

## Requirements

- **Home Assistant** 2024.1.0 or later
- **Python** 3.12+ (provided by the HA installation)
- **Package** `openai` >= 1.0 (installed automatically)
- **z.ai Coding Plan** subscription with an active API key

## Credits

Based on [z.ai Conversation](https://github.com/iannuz92/zai-conversation-ha) by [@iannuz92](https://github.com/iannuz92), refactored to use the OpenAI-compatible Coding Plan API endpoint with German as the default language.

## License

MIT License — See the [LICENSE](LICENSE) file for details.
