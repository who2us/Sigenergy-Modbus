"""Config flow for SigenEnergy integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_USERNAME,
)
from homeassistant.data_entry_flow import FlowResult

from .cloud_api import CloudAuthError, SigenCloudAPI
from .const import CONF_CLOUD_PASSWORD, CONF_CLOUD_USERNAME, DEFAULT_WS_PORT, DOMAIN
from .gateway import GatewayError, SigenEnergyGateway

_LOGGER = logging.getLogger(__name__)


class SigenEnergyConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Two-step config flow: local gateway → cloud credentials."""

    VERSION = 1

    def __init__(self) -> None:
        self._local_data: dict[str, Any] = {}

    # ── Step 1: Local gateway ─────────────────────────────────────────────────

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 1 — local gateway connection details."""
        errors: dict[str, str] = {}

        if user_input is not None:
            gateway = SigenEnergyGateway(
                host=user_input[CONF_HOST],
                port=user_input.get(CONF_PORT, DEFAULT_WS_PORT),
                username=user_input.get(CONF_USERNAME, ""),
                password=user_input.get(CONF_PASSWORD, ""),
                serial=user_input.get("serial", ""),
            )
            try:
                await gateway.connect()
                await gateway.disconnect()
            except GatewayError as err:
                _LOGGER.error("Local gateway connection test failed: %s", err)
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error in step 1")
                errors["base"] = "unknown"
            else:
                self._local_data = user_input
                # Proceed to cloud credentials step
                return await self.async_step_cloud()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST): str,
                    vol.Optional(CONF_PORT, default=DEFAULT_WS_PORT): vol.All(
                        vol.Coerce(int), vol.Range(min=1, max=65535)
                    ),
                    vol.Optional(CONF_USERNAME, default="admin"): str,
                    vol.Optional(CONF_PASSWORD, default=""): str,
                    vol.Optional("serial", default=""): str,
                }
            ),
            errors=errors,
        )

    # ── Step 2: Cloud credentials ─────────────────────────────────────────────

    async def async_step_cloud(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """
        Step 2 — SigenEnergy cloud account credentials.

        Pre-fills with the local gateway credentials since they're often the same.
        The user can leave them blank to skip cloud features.
        """
        errors: dict[str, str] = {}

        if user_input is not None:
            cloud_user = user_input.get(CONF_CLOUD_USERNAME, "").strip()
            cloud_pass = user_input.get(CONF_CLOUD_PASSWORD, "").strip()

            if cloud_user and cloud_pass:
                # Validate cloud credentials
                api = SigenCloudAPI(cloud_user, cloud_pass)
                try:
                    await api.authenticate()
                    await api.get_station_id()
                except CloudAuthError as err:
                    _LOGGER.error("Cloud auth failed: %s", err)
                    errors["base"] = "invalid_auth"
                except Exception as err:
                    _LOGGER.error("Cloud connection failed: %s", err)
                    errors["base"] = "cannot_connect"
                finally:
                    await api.close()

            if not errors:
                combined = {**self._local_data}
                if cloud_user:
                    combined[CONF_CLOUD_USERNAME] = cloud_user
                    combined[CONF_CLOUD_PASSWORD] = cloud_pass

                await self.async_set_unique_id(
                    f"{self._local_data[CONF_HOST]}:{self._local_data.get(CONF_PORT, DEFAULT_WS_PORT)}"
                )
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=f"SigenEnergy @ {self._local_data[CONF_HOST]}",
                    data=combined,
                )

        # Pre-fill cloud fields with local credentials as a convenience
        return self.async_show_form(
            step_id="cloud",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_CLOUD_USERNAME,
                        default=self._local_data.get(CONF_USERNAME, ""),
                    ): str,
                    vol.Optional(
                        CONF_CLOUD_PASSWORD,
                        default=self._local_data.get(CONF_PASSWORD, ""),
                    ): str,
                }
            ),
            errors=errors,
            description_placeholders={
                "note": "Leave blank to skip cloud sensors and use local gateway only."
            },
        )
