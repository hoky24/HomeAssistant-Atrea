"""Config flow for the Atrea integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import (
    CONF_IP_ADDRESS,
    CONF_NAME,
    CONF_PASSWORD,
    CONF_PORT,
)
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from pyatrea import AtreaClient
from pyatrea.exceptions import AtreaAuthError, AtreaConnectionError

from .const import (
    ALL_PRESET_LIST,
    CONF_FAN_MODES,
    CONF_PRESETS,
    DEFAULT_FAN_MODE_LIST,
    DOMAIN,
    LOGGER,
)


class AtreaConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Atrea."""

    VERSION = 2

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> AtreaOptionsFlow:
        """Return the options flow for this handler."""
        return AtreaOptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial single-step user form."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_IP_ADDRESS]
            port = user_input[CONF_PORT]
            password = user_input.get(CONF_PASSWORD, "")
            name = user_input.get(CONF_NAME, "Atrea")

            await self.async_set_unique_id(host)
            self._abort_if_unique_id_configured()

            client = AtreaClient(
                host, port, password, async_get_clientsession(self.hass)
            )
            try:
                if not await client.is_atrea_unit():
                    errors["base"] = "not_atrea_unit"
                else:
                    await client.fetch_status()
            except AtreaAuthError:
                errors["base"] = "invalid_auth"
            except AtreaConnectionError:
                errors["base"] = "cannot_connect"
            else:
                if not errors:
                    return self.async_create_entry(
                        title=host,
                        data={
                            CONF_IP_ADDRESS: host,
                            CONF_PORT: port,
                            CONF_PASSWORD: password,
                            CONF_NAME: name,
                        },
                    )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_IP_ADDRESS): str,
                    vol.Required(CONF_PORT, default=80): int,
                    vol.Optional(CONF_PASSWORD, default=""): str,
                    vol.Optional(CONF_NAME, default="Atrea"): str,
                }
            ),
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> ConfigFlowResult:
        """Handle re-authentication on credential failure."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Re-prompt the password and validate it."""
        errors: dict[str, str] = {}
        reauth_entry = self._get_reauth_entry()
        host = reauth_entry.data[CONF_IP_ADDRESS]
        port = reauth_entry.data.get(CONF_PORT, 80)

        if user_input is not None:
            password = user_input.get(CONF_PASSWORD, "")
            client = AtreaClient(
                host, port, password, async_get_clientsession(self.hass)
            )
            try:
                await client.fetch_status()
            except AtreaAuthError:
                errors["base"] = "invalid_auth"
            except AtreaConnectionError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_update_reload_and_abort(
                    reauth_entry,
                    data={**reauth_entry.data, CONF_PASSWORD: password},
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Optional(CONF_PASSWORD, default=""): str}),
            errors=errors,
            description_placeholders={CONF_IP_ADDRESS: host},
        )


class AtreaOptionsFlow(OptionsFlow):
    """Handle Atrea options (fan modes + enabled presets)."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        data = {**self.config_entry.data, **self.config_entry.options}

        if user_input is not None:
            presets = {
                preset: bool(user_input.get(preset, True))
                for preset in ALL_PRESET_LIST
            }
            LOGGER.debug("Saving Atrea options for %s", data.get(CONF_IP_ADDRESS))
            return self.async_create_entry(
                title="",
                data={
                    CONF_FAN_MODES: user_input.get(
                        CONF_FAN_MODES, DEFAULT_FAN_MODE_LIST
                    ),
                    CONF_PRESETS: presets,
                },
            )

        fan_modes = data.get(CONF_FAN_MODES, DEFAULT_FAN_MODE_LIST)
        presets = data.get(CONF_PRESETS, {})

        spec: dict[Any, Any] = {
            vol.Optional(CONF_FAN_MODES, default=fan_modes): str,
        }
        for preset in ALL_PRESET_LIST:
            spec[vol.Required(preset, default=presets.get(preset, True))] = bool

        return self.async_show_form(
            step_id="init", data_schema=vol.Schema(spec)
        )
