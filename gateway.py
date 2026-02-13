"""
SigenEnergy Gateway WebSocket Client

Handles the low-level WebSocket communication with the SigenEnergy gateway.

Protocol notes (reverse-engineered from Flutter app main.dart.js):
───────────────────────────────────────────────────────────────────
The app opens a WebSocket connection to the gateway on port 8080.

Every message is a JSON object with this envelope:

  Outbound (app → gateway):
  {
    "msgType": <int>,
    "sn":      "<gateway serial number>",
    "token":   "<auth token after login>",
    "data":    { ... command-specific payload ... }
  }

  Inbound (gateway → app):
  {
    "msgType": <int>,
    "code":    <int>,    // 0 = success
    "msg":     "<str>",  // human-readable status
    "data":    { ... response payload ... }
  }

Authentication (MSG_TYPE_AUTH = 0):
  Send:    { "msgType": 0, "sn": "", "data": { "username": "...", "password": "..." } }
  Receive: { "msgType": 1, "code": 0, "data": { "token": "...", "sn": "..." } }

Modbus TCP query (MSG_TYPE_GET = 2):
  Send:    { "msgType": 2, "sn": "<sn>", "token": "<tok>",
             "data": { "service": "modbusTcpServer" } }
  Receive: { "msgType": 4, "code": 0,
             "data": { "modbusEnable": 0|1, "modbusPort": 502 } }

Modbus TCP enable (MSG_TYPE_SET = 3):
  Send:    { "msgType": 3, "sn": "<sn>", "token": "<tok>",
             "data": { "service": "modbusTcpServer",
                       "modbusEnable": 1, "modbusPort": 502 } }
  Receive: { "msgType": 4, "code": 0, "msg": "ok" }

If the exact service key doesn't match, try enabling debug logging:
  logger:
    logs:
      custom_components.sigenergy_modbus_tcp: debug

The raw WS frames will be logged so you can adjust KEY_* constants in const.py.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import aiohttp

from .const import (
    DEFAULT_WS_PORT,
    DEFAULT_MODBUS_PORT,
    KEY_MODBUS_ENABLE,
    KEY_MODBUS_PORT,
    MSG_TYPE_AUTH,
    MSG_TYPE_GET,
    MSG_TYPE_SET,
    MSG_TYPE_RESPONSE,
    SERVICE_MODBUS_TCP,
)

_LOGGER = logging.getLogger(__name__)

# Time to wait for a response before giving up (seconds)
RESPONSE_TIMEOUT = 10


class GatewayError(Exception):
    """Raised when the gateway returns an error or is unreachable."""


class SigenEnergyGateway:
    """Async WebSocket client for a SigenEnergy gateway."""

    def __init__(
        self,
        host: str,
        port: int = DEFAULT_WS_PORT,
        username: str = "",
        password: str = "",
        serial: str = "",
    ) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._serial = serial  # filled in after auth if empty

        self._ws_url = f"ws://{host}:{port}/ws"
        self._session: aiohttp.ClientSession | None = None
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._token: str = ""

        # Pending response futures keyed by msgType
        self._pending: dict[int, asyncio.Future] = {}
        self._listener_task: asyncio.Task | None = None

    # ------------------------------------------------------------------ #
    # Connection lifecycle                                                 #
    # ------------------------------------------------------------------ #

    async def connect(self) -> None:
        """Open the WebSocket connection and authenticate."""
        _LOGGER.debug("Connecting to SigenEnergy gateway at %s", self._ws_url)
        self._session = aiohttp.ClientSession()
        try:
            self._ws = await self._session.ws_connect(
                self._ws_url,
                heartbeat=20,
                timeout=aiohttp.ClientTimeout(total=15),
            )
        except Exception as err:
            await self._session.close()
            raise GatewayError(f"WebSocket connect failed: {err}") from err

        # Start the background listener
        self._listener_task = asyncio.create_task(self._listen())

        # Authenticate
        await self._authenticate()
        _LOGGER.info(
            "Connected and authenticated to SigenEnergy gateway (SN=%s)", self._serial
        )

    async def disconnect(self) -> None:
        """Close the WebSocket connection."""
        if self._listener_task:
            self._listener_task.cancel()
        if self._ws:
            await self._ws.close()
        if self._session:
            await self._session.close()
        _LOGGER.debug("Disconnected from SigenEnergy gateway")

    # ------------------------------------------------------------------ #
    # Authentication                                                       #
    # ------------------------------------------------------------------ #

    async def _authenticate(self) -> None:
        """Send login credentials and store the returned token."""
        payload = {
            "msgType": MSG_TYPE_AUTH,
            "sn": self._serial,
            "data": {
                "username": self._username,
                "password": self._password,
            },
        }
        response = await self._send_and_wait(MSG_TYPE_AUTH + 1, payload)
        self._token = response.get("data", {}).get("token", "")
        if not self._token:
            raise GatewayError("Authentication failed: no token in response")
        # Update serial if the gateway told us its SN
        sn = response.get("data", {}).get("sn", "")
        if sn and not self._serial:
            self._serial = sn

    # ------------------------------------------------------------------ #
    # Modbus TCP API                                                       #
    # ------------------------------------------------------------------ #

    async def get_modbus_tcp_status(self) -> dict[str, Any]:
        """
        Query the current Modbus TCP server settings from the gateway.

        Returns a dict like:
          { "modbusEnable": 0|1, "modbusPort": 502, ... }
        """
        payload = {
            "msgType": MSG_TYPE_GET,
            "sn": self._serial,
            "token": self._token,
            "data": {"service": SERVICE_MODBUS_TCP},
        }
        response = await self._send_and_wait(MSG_TYPE_RESPONSE, payload)
        _LOGGER.debug("Modbus TCP status response: %s", response)
        data = response.get("data", {})
        if not data:
            raise GatewayError("Empty data in Modbus TCP status response")
        return data

    async def set_modbus_tcp_enabled(self, enabled: bool) -> bool:
        """
        Enable or disable the Modbus TCP server on the gateway.

        Returns True if the command was acknowledged successfully.
        """
        # First get current port so we don't clobber it
        try:
            current = await self.get_modbus_tcp_status()
            port = current.get(KEY_MODBUS_PORT, DEFAULT_MODBUS_PORT)
        except GatewayError:
            port = DEFAULT_MODBUS_PORT

        payload = {
            "msgType": MSG_TYPE_SET,
            "sn": self._serial,
            "token": self._token,
            "data": {
                "service": SERVICE_MODBUS_TCP,
                KEY_MODBUS_ENABLE: 1 if enabled else 0,
                KEY_MODBUS_PORT: port,
            },
        }
        response = await self._send_and_wait(MSG_TYPE_RESPONSE, payload)
        code = response.get("code", -1)
        if code != 0:
            raise GatewayError(
                f"Gateway rejected Modbus TCP enable command (code={code}, "
                f"msg={response.get('msg', 'unknown')})"
            )
        _LOGGER.info("Modbus TCP %s (port %s)", "enabled" if enabled else "disabled", port)
        return True

    async def set_modbus_tcp_port(self, port: int) -> bool:
        """Change the Modbus TCP listening port on the gateway."""
        # Preserve current enable state
        try:
            current = await self.get_modbus_tcp_status()
            enabled = current.get(KEY_MODBUS_ENABLE, 0)
        except GatewayError:
            enabled = 0

        payload = {
            "msgType": MSG_TYPE_SET,
            "sn": self._serial,
            "token": self._token,
            "data": {
                "service": SERVICE_MODBUS_TCP,
                KEY_MODBUS_ENABLE: enabled,
                KEY_MODBUS_PORT: port,
            },
        }
        response = await self._send_and_wait(MSG_TYPE_RESPONSE, payload)
        code = response.get("code", -1)
        if code != 0:
            raise GatewayError(f"Failed to set Modbus TCP port (code={code})")
        _LOGGER.info("Modbus TCP port changed to %s", port)
        return True

    # ------------------------------------------------------------------ #
    # Internal WS helpers                                                  #
    # ------------------------------------------------------------------ #

    async def _send_and_wait(
        self,
        expected_msg_type: int,
        payload: dict,
        timeout: float = RESPONSE_TIMEOUT,
    ) -> dict:
        """Send a JSON payload and await the response with the given msgType."""
        if not self._ws or self._ws.closed:
            raise GatewayError("WebSocket is not connected")

        fut: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[expected_msg_type] = fut

        raw = json.dumps(payload)
        _LOGGER.debug("→ WS send: %s", raw)
        await self._ws.send_str(raw)

        try:
            return await asyncio.wait_for(fut, timeout=timeout)
        except asyncio.TimeoutError:
            self._pending.pop(expected_msg_type, None)
            raise GatewayError(
                f"Timeout waiting for msgType={expected_msg_type} from gateway"
            )

    async def _listen(self) -> None:
        """Background task: read incoming WS frames and resolve pending futures."""
        try:
            async for msg in self._ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    _LOGGER.debug("← WS recv: %s", msg.data)
                    try:
                        frame = json.loads(msg.data)
                    except json.JSONDecodeError:
                        _LOGGER.warning("Non-JSON WS frame received: %s", msg.data)
                        continue

                    msg_type = frame.get("msgType", -1)
                    fut = self._pending.pop(msg_type, None)
                    if fut and not fut.done():
                        fut.set_result(frame)

                elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                    _LOGGER.warning("WS connection closed/error: %s", msg)
                    break
        except asyncio.CancelledError:
            pass
        except Exception as err:
            _LOGGER.error("WS listener error: %s", err)
        finally:
            # Fail any still-pending futures
            for fut in self._pending.values():
                if not fut.done():
                    fut.set_exception(GatewayError("WebSocket connection lost"))
            self._pending.clear()
