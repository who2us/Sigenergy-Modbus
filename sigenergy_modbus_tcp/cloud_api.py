"""
SigenEnergy Cloud API Client

Async implementation of the confirmed-working MySigen prototype.

Authentication flow (OAuth2 password grant):
  POST https://api-aus.sigencloud.com/auth/oauth/token
    Authorization: Basic c2lnZW46c2lnZW4=   (base64 of "sigen:sigen")
    Content-Type: application/x-www-form-urlencoded
    Body: grant_type=password&scope=server&username=...&password=...&userDeviceId=<timestamp_ms>

  Response: { "code": 0, "data": { "access_token": "...", ... } }

Data endpoints (Bearer token auth):
  GET /device/owner/station/home               → stationId
  GET /device/sigen/station/energyflow/async   → live power/SoC
  GET /data-process/sigen/station/statistics/gains → generation totals

Confirmed field names from prototype:
  energy_flow: batterySoc, batteryPower, pvPower, buySellPower, loadPower
  statistics:  dayGeneration, monthGeneration, yearGeneration, lifetimeGeneration
"""

from __future__ import annotations

import logging
import time
from typing import Any

import aiohttp

from .const import (
    CLOUD_AUTH_URL,
    CLOUD_CLIENT_BASIC,
    CLOUD_COMMON_HEADERS,
    CLOUD_ENERGY_URL,
    CLOUD_STATION_URL,
    CLOUD_STATS_URL,
)

_LOGGER = logging.getLogger(__name__)

# How old a token can be before we proactively refresh (seconds)
TOKEN_REFRESH_MARGIN = 300


class CloudAuthError(Exception):
    """Raised when cloud authentication fails."""


class CloudAPIError(Exception):
    """Raised when a cloud API call fails."""


class SigenCloudAPI:
    """Async client for the SigenEnergy cloud API."""

    def __init__(self, username: str, password: str) -> None:
        self._username = username
        self._password = password
        self._access_token: str = ""
        self._token_expiry: float = 0.0
        self._station_id: str = ""
        self._session: aiohttp.ClientSession | None = None

    # ------------------------------------------------------------------ #
    # Session lifecycle                                                    #
    # ------------------------------------------------------------------ #

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(headers=CLOUD_COMMON_HEADERS)
        return self._session

    async def close(self) -> None:
        """Close the underlying HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()

    # ------------------------------------------------------------------ #
    # Authentication                                                       #
    # ------------------------------------------------------------------ #

    async def authenticate(self) -> None:
        """
        Obtain an OAuth2 access token from the SigenEnergy cloud.

        Uses the confirmed Basic-auth + password-grant flow from the
        working MySigen prototype.
        """
        session = await self._get_session()
        device_id = str(int(time.time() * 1000))
        ts = str(int(time.time() * 1000))

        headers = {
            "Content-Type":   "application/x-www-form-urlencoded",
            "Authorization":  f"Basic {CLOUD_CLIENT_BASIC}",
            "Auth-Client-Id": "sigen",
            "Sg-V":           "3.4.0",
            "Sg-Ts":          ts,
        }
        body = {
            "scope":        "server",
            "grant_type":   "password",
            "userDeviceId": device_id,
            "username":     self._username,
            "password":     self._password,
        }

        _LOGGER.debug("Authenticating to SigenEnergy cloud as %s", self._username)
        try:
            async with session.post(
                CLOUD_AUTH_URL, data=body, headers=headers, timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                raw = await resp.json(content_type=None)
        except Exception as err:
            raise CloudAuthError(f"Auth request failed: {err}") from err

        if raw.get("code") != 0:
            raise CloudAuthError(
                f"Auth rejected by server (code={raw.get('code')}, msg={raw.get('msg')})"
            )

        data = raw.get("data", {})
        token = data.get("access_token", "")
        if not token:
            raise CloudAuthError("No access_token in auth response")

        self._access_token = token
        # expires_in is in seconds; store absolute expiry time
        expires_in = data.get("expires_in", 3600)
        self._token_expiry = time.time() + expires_in
        _LOGGER.info("SigenEnergy cloud: authenticated successfully")

    async def _ensure_authenticated(self) -> None:
        """Re-authenticate if the token is absent or near expiry."""
        if not self._access_token or time.time() > (self._token_expiry - TOKEN_REFRESH_MARGIN):
            await self.authenticate()

    def _bearer_headers(self) -> dict[str, str]:
        ts = str(int(time.time() * 1000))
        return {
            "Authorization":  f"Bearer {self._access_token}",
            "TENANT-ID":      "1",
            "Auth-Client-Id": "sigen",
            "Sg-V":           "3.4.0",
            "Sg-Ts":          ts,
        }

    # ------------------------------------------------------------------ #
    # Station discovery                                                    #
    # ------------------------------------------------------------------ #

    async def get_station_id(self) -> str:
        """
        Fetch the station ID for this account.

        The station ID is needed as a parameter for all energy/stats queries.
        Cached after the first successful call.
        """
        if self._station_id:
            return self._station_id

        await self._ensure_authenticated()
        session = await self._get_session()

        try:
            async with session.get(
                CLOUD_STATION_URL,
                headers=self._bearer_headers(),
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                raw = await resp.json(content_type=None)
        except Exception as err:
            raise CloudAPIError(f"Station lookup failed: {err}") from err

        if raw.get("code") != 0:
            raise CloudAPIError(f"Station lookup error (code={raw.get('code')})")

        station_id = str(raw.get("data", {}).get("stationId", ""))
        if not station_id:
            raise CloudAPIError("No stationId in response")

        self._station_id = station_id
        _LOGGER.debug("SigenEnergy cloud: station ID = %s", station_id)
        return station_id

    # ------------------------------------------------------------------ #
    # Data fetching                                                        #
    # ------------------------------------------------------------------ #

    async def get_energy_flow(self) -> dict[str, Any]:
        """
        Fetch live energy flow data.

        Confirmed fields:
          batterySoc    (%)
          batteryPower  (W — divide by 1000 for kW)
          pvPower       (W — divide by 1000 for kW)
          buySellPower  (W — positive = buying, negative = selling)
          loadPower     (W)
        """
        await self._ensure_authenticated()
        station_id = await self.get_station_id()
        session = await self._get_session()

        params = {"id": station_id, "refreshFlag": "true"}
        try:
            async with session.get(
                CLOUD_ENERGY_URL,
                headers=self._bearer_headers(),
                params=params,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                raw = await resp.json(content_type=None)
        except Exception as err:
            raise CloudAPIError(f"Energy flow request failed: {err}") from err

        if raw.get("code") != 0:
            # 401-style: token expired mid-session → clear and let coordinator retry
            if raw.get("code") in (401, 40100, 40101):
                self._access_token = ""
            raise CloudAPIError(
                f"Energy flow error (code={raw.get('code')}, msg={raw.get('msg')})"
            )

        return raw.get("data", {})

    async def get_statistics(self) -> dict[str, Any]:
        """
        Fetch generation statistics.

        Confirmed fields:
          dayGeneration       (kWh)
          monthGeneration     (kWh)
          yearGeneration      (kWh)
          lifetimeGeneration  (kWh)
        """
        await self._ensure_authenticated()
        station_id = await self.get_station_id()
        session = await self._get_session()

        params = {"stationId": station_id}
        try:
            async with session.get(
                CLOUD_STATS_URL,
                headers=self._bearer_headers(),
                params=params,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                raw = await resp.json(content_type=None)
        except Exception as err:
            raise CloudAPIError(f"Statistics request failed: {err}") from err

        if raw.get("code") != 0:
            if raw.get("code") in (401, 40100, 40101):
                self._access_token = ""
            raise CloudAPIError(
                f"Statistics error (code={raw.get('code')}, msg={raw.get('msg')})"
            )

        return raw.get("data", {})

    async def fetch_all(self) -> dict[str, Any]:
        """
        Fetch both energy flow and statistics in one coordinator update.

        Returns:
          {
            "energy_flow": { batterySoc, batteryPower, pvPower, buySellPower, loadPower, ... },
            "statistics":  { dayGeneration, monthGeneration, yearGeneration, lifetimeGeneration, ... },
          }
        """
        energy_flow = await self.get_energy_flow()
        statistics = await self.get_statistics()
        return {"energy_flow": energy_flow, "statistics": statistics}
