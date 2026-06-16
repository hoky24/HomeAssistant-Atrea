"""Config flow for the Atrea integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import (
    CONF_IP_ADDRESS,
    CONF_NAME,
    CONF_PASSWORD,
    CONF_PORT,
)
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from pyatrea import HttpTransport, ModbusTransport
from pyatrea.exceptions import AtreaAuthError, AtreaConnectionError

from .const import (
    ALL_PRESET_LIST,
    CONF_FAN_MODES,
    CONF_PRESETS,
    CONF_SLAVE_ID,
    CONF_TRANSPORT,
    DEFAULT_FAN_MODE_LIST,
    DOMAIN,
    LOGGER,
    TRANSPORT_HTTP,
    TRANSPORT_MODBUS,
)


class AtreaConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Atrea."""

    VERSION = 2

    _transport: str

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> AtreaOptionsFlow:
        """Return the options flow for this handler."""
        return AtreaOptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask which transport to use, then branch to its step."""
        if user_input is not None:
            self._transport = user_input[CONF_TRANSPORT]
            if self._transport == TRANSPORT_MODBUS:
                return await self.async_step_modbus()
            return await self.async_step_http()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_TRANSPORT, default=TRANSPORT_HTTP
                    ): vol.In([TRANSPORT_HTTP, TRANSPORT_MODBUS]),
                }
            ),
        )

    async def async_step_http(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect and validate HTTP connection details."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_IP_ADDRESS]
            port = user_input[CONF_PORT]
            password = user_input.get(CONF_PASSWORD, "")
            name = user_input.get(CONF_NAME, "Atrea")

            await self.async_set_unique_id(host)
            self._abort_if_unique_id_configured()

            transport = HttpTransport(
                host, port, password, async_get_clientsession(self.hass)
            )
            try:
                if not await transport.is_atrea_unit():
                    errors["base"] = "not_atrea_unit"
                else:
                    await transport.read()
            except AtreaAuthError:
                errors["base"] = "invalid_auth"
            except AtreaConnectionError:
                errors["base"] = "cannot_connect"
            else:
                if not errors:
                    return self.async_create_entry(
                        title=host,
                        data={
                            CONF_TRANSPORT: TRANSPORT_HTTP,
                            CONF_IP_ADDRESS: host,
                            CONF_PORT: port,
                            CONF_PASSWORD: password,
                            CONF_NAME: name,
                        },
                    )

        return self.async_show_form(
            step_id="http",
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

    async def async_step_modbus(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect and validate Modbus TCP connection details."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_IP_ADDRESS]
            port = user_input[CONF_PORT]
            slave_id = user_input[CONF_SLAVE_ID]
            name = user_input.get(CONF_NAME, "Atrea")

            await self.async_set_unique_id(host)
            self._abort_if_unique_id_configured()

            transport = ModbusTransport(host, port, slave_id)
            try:
                await transport.connect()
                if not await transport.is_atrea_unit():
                    errors["base"] = "not_atrea_unit"
                else:
                    await transport.read()
            except AtreaConnectionError:
                errors["base"] = "cannot_connect"
            else:
                if not errors:
                    return self.async_create_entry(
                        title=host,
                        data={
                            CONF_TRANSPORT: TRANSPORT_MODBUS,
                            CONF_IP_ADDRESS: host,
                            CONF_PORT: port,
                            CONF_SLAVE_ID: slave_id,
                            CONF_NAME: name,
                        },
                    )
            finally:
                await transport.close()

        return self.async_show_form(
            step_id="modbus",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_IP_ADDRESS): str,
                    vol.Required(CONF_PORT, default=502): int,
                    vol.Required(CONF_SLAVE_ID, default=1): int,
                    vol.Optional(CONF_NAME, default="Atrea"): str,
                }
            ),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick the transport, then branch to its reconfigure sub-step.

        Unlike the initial setup, reconfigure allows switching the backend
        (HTTP <-> Modbus TCP) without removing and re-adding the integration.
        """
        reconfigure_entry = self._get_reconfigure_entry()
        current_transport = reconfigure_entry.data.get(
            CONF_TRANSPORT, TRANSPORT_HTTP
        )

        if user_input is not None:
            self._transport = user_input[CONF_TRANSPORT]
            if self._transport == TRANSPORT_MODBUS:
                return await self.async_step_reconfigure_modbus()
            return await self.async_step_reconfigure_http()

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_TRANSPORT, default=current_transport
                    ): vol.In([TRANSPORT_HTTP, TRANSPORT_MODBUS]),
                }
            ),
        )

    async def async_step_reconfigure_http(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect and validate HTTP details for a reconfigure."""
        errors: dict[str, str] = {}
        reconfigure_entry = self._get_reconfigure_entry()

        if user_input is not None:
            host = user_input[CONF_IP_ADDRESS]
            port = user_input[CONF_PORT]
            password = user_input.get(CONF_PASSWORD, "")
            name = user_input.get(CONF_NAME, "Atrea")

            await self.async_set_unique_id(host)
            self._abort_if_unique_id_mismatch()

            transport = HttpTransport(
                host, port, password, async_get_clientsession(self.hass)
            )
            try:
                if not await transport.is_atrea_unit():
                    errors["base"] = "not_atrea_unit"
                else:
                    await transport.read()
            except AtreaAuthError:
                errors["base"] = "invalid_auth"
            except AtreaConnectionError:
                errors["base"] = "cannot_connect"
            else:
                if not errors:
                    return self.async_update_reload_and_abort(
                        reconfigure_entry,
                        data={
                            CONF_TRANSPORT: TRANSPORT_HTTP,
                            CONF_IP_ADDRESS: host,
                            CONF_PORT: port,
                            CONF_PASSWORD: password,
                            CONF_NAME: name,
                        },
                    )

        data = reconfigure_entry.data
        return self.async_show_form(
            step_id="reconfigure_http",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_IP_ADDRESS, default=data.get(CONF_IP_ADDRESS)
                    ): str,
                    vol.Required(CONF_PORT, default=data.get(CONF_PORT, 80)): int,
                    vol.Optional(
                        CONF_PASSWORD, default=data.get(CONF_PASSWORD, "")
                    ): str,
                    vol.Optional(
                        CONF_NAME, default=data.get(CONF_NAME, "Atrea")
                    ): str,
                }
            ),
            errors=errors,
        )

    async def async_step_reconfigure_modbus(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect and validate Modbus TCP details for a reconfigure."""
        errors: dict[str, str] = {}
        reconfigure_entry = self._get_reconfigure_entry()

        if user_input is not None:
            host = user_input[CONF_IP_ADDRESS]
            port = user_input[CONF_PORT]
            slave_id = user_input[CONF_SLAVE_ID]
            name = user_input.get(CONF_NAME, "Atrea")

            await self.async_set_unique_id(host)
            self._abort_if_unique_id_mismatch()

            transport = ModbusTransport(host, port, slave_id)
            try:
                await transport.connect()
                if not await transport.is_atrea_unit():
                    errors["base"] = "not_atrea_unit"
                else:
                    await transport.read()
            except AtreaConnectionError:
                errors["base"] = "cannot_connect"
            else:
                if not errors:
                    return self.async_update_reload_and_abort(
                        reconfigure_entry,
                        data={
                            CONF_TRANSPORT: TRANSPORT_MODBUS,
                            CONF_IP_ADDRESS: host,
                            CONF_PORT: port,
                            CONF_SLAVE_ID: slave_id,
                            CONF_NAME: name,
                        },
                    )
            finally:
                await transport.close()

        data = reconfigure_entry.data
        return self.async_show_form(
            step_id="reconfigure_modbus",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_IP_ADDRESS, default=data.get(CONF_IP_ADDRESS)
                    ): str,
                    vol.Required(CONF_PORT, default=data.get(CONF_PORT, 502)): int,
                    vol.Required(
                        CONF_SLAVE_ID, default=data.get(CONF_SLAVE_ID, 1)
                    ): int,
                    vol.Optional(
                        CONF_NAME, default=data.get(CONF_NAME, "Atrea")
                    ): str,
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
            transport = HttpTransport(
                host, port, password, async_get_clientsession(self.hass)
            )
            try:
                await transport.read()
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


class AtreaOptionsFlow(OptionsFlowWithReload):
    """Handle Atrea options (fan modes + enabled presets).

    Subclassing ``OptionsFlowWithReload`` (HA 2024.11+) makes HA automatically
    reload the config entry when options are saved, so changes take effect.
    """

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
