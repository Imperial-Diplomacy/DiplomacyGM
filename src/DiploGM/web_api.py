"""HTTP API for the separately hosted DiplomacyGM web client."""

from __future__ import annotations

import logging
import os
import secrets
import time
from dataclasses import dataclass
from datetime import timedelta
from urllib.parse import urlencode, urlsplit

import aiohttp
import discord
from aiohttp import web
from discord.ext import commands

from DiploGM import config
from DiploGM.db.database import get_connection
from DiploGM.errors import MapRenderError, NoGameError
from DiploGM.manager import Manager
from DiploGM.models.board import Board
from DiploGM.models.order import Build, Disband

logger = logging.getLogger(__name__)

DISCORD_API = "https://discord.com/api/v10"
SESSION_COOKIE = "diplogm_session"
OAUTH_STATE_COOKIE = "diplogm_oauth_state"
SESSION_LIFETIME = 60 * 60 * 8
OAUTH_STATE_LIFETIME = 60 * 10


@dataclass(frozen=True)
class WebSession:
    user_id: int
    username: str
    expires_at: float


class WebAPI:
    """Runs the web API alongside the bot so it uses the bot's live game state."""

    def __init__(
        self,
        bot: commands.Bot,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        frontend_origin: str,
        host: str,
        port: int,
        cookie_secure: bool,
        cookie_samesite: str,
    ) -> None:
        self.bot = bot
        self.manager = Manager()
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.frontend_origin = frontend_origin.rstrip("/")
        self.host = host
        self.port = port
        self.cookie_secure = cookie_secure
        self.cookie_samesite = cookie_samesite
        self.sessions: dict[str, WebSession] = {}
        self.oauth_states: dict[str, float] = {}
        self.client: aiohttp.ClientSession | None = None
        self.runner: web.AppRunner | None = None

        app = web.Application(middlewares=[self._cors_and_csrf])
        app.add_routes(
            [
                web.get("/auth/login", self.login),
                web.get("/auth/callback", self.callback),
                web.get("/api/me", self.me),
                web.get("/api/servers", self.servers),
                web.get(r"/api/servers/{guild_id:\d+}/status", self.server_status),
                web.get(r"/api/servers/{guild_id:\d+}/map.svg", self.server_map),
                web.put(r"/api/servers/{guild_id:\d+}/deadline", self.set_deadline),
                web.post(
                    r"/api/servers/{guild_id:\d+}/adjudicate",
                    self.adjudicate,
                ),
                web.post("/api/logout", self.logout),
            ]
        )
        self.app = app
        self.app.on_response_prepare.append(self._add_cors_headers)

    @classmethod
    def from_environment(cls, bot: commands.Bot) -> WebAPI | None:
        enabled = os.getenv("WEB_API_ENABLED", "").lower() in {"1", "true", "yes"}
        if not enabled:
            return None

        required = (
            "WEB_API_CLIENT_ID",
            "WEB_API_CLIENT_SECRET",
            "WEB_API_REDIRECT_URI",
            "WEB_API_FRONTEND_ORIGIN",
        )
        missing = [key for key in required if not os.getenv(key)]
        if missing:
            raise RuntimeError("WEB_API_ENABLED requires " + ", ".join(missing))

        frontend_origin = os.environ["WEB_API_FRONTEND_ORIGIN"].rstrip("/")
        parsed_origin = urlsplit(frontend_origin)
        origin_is_local = parsed_origin.hostname in {"localhost", "127.0.0.1", "::1"}
        if (
            parsed_origin.scheme not in {"http", "https"}
            or not parsed_origin.netloc
            or parsed_origin.path
            or parsed_origin.query
            or parsed_origin.fragment
            or (parsed_origin.scheme != "https" and not origin_is_local)
        ):
            raise RuntimeError(
                "WEB_API_FRONTEND_ORIGIN must be an HTTPS or localhost origin"
            )
        redirect_uri = os.environ["WEB_API_REDIRECT_URI"]
        parsed_redirect = urlsplit(redirect_uri)
        redirect_is_local = parsed_redirect.hostname in {
            "localhost",
            "127.0.0.1",
            "::1",
        }
        if (
            parsed_redirect.scheme not in {"http", "https"}
            or not parsed_redirect.netloc
            or (parsed_redirect.scheme != "https" and not redirect_is_local)
        ):
            raise RuntimeError(
                "WEB_API_REDIRECT_URI must use HTTPS except for localhost development"
            )

        same_site = os.getenv("WEB_API_COOKIE_SAMESITE", "None")
        if same_site not in {"Lax", "Strict", "None"}:
            raise RuntimeError("WEB_API_COOKIE_SAMESITE must be Lax, Strict, or None")
        cookie_secure = os.getenv("WEB_API_COOKIE_SECURE", "true").lower() not in {
            "0",
            "false",
            "no",
        }
        if same_site == "None" and not cookie_secure:
            raise RuntimeError(
                "WEB_API_COOKIE_SECURE must be true when SameSite is None"
            )

        return cls(
            bot=bot,
            client_id=os.environ["WEB_API_CLIENT_ID"],
            client_secret=os.environ["WEB_API_CLIENT_SECRET"],
            redirect_uri=redirect_uri,
            frontend_origin=frontend_origin,
            host=os.getenv("WEB_API_HOST", "127.0.0.1"),
            port=int(os.getenv("WEB_API_PORT", "8000")),
            cookie_secure=cookie_secure,
            cookie_samesite=same_site,
        )

    async def start(self) -> None:
        self.client = aiohttp.ClientSession()
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, self.host, self.port)
        await site.start()
        logger.info("Web API listening on %s:%s", self.host, self.port)

    async def close(self) -> None:
        if self.runner is not None:
            await self.runner.cleanup()
            self.runner = None
        if self.client is not None:
            await self.client.close()
            self.client = None

    @web.middleware
    async def _cors_and_csrf(self, request: web.Request, handler) -> web.StreamResponse:
        origin = request.headers.get("Origin")
        if request.method == "OPTIONS" and request.path.startswith("/api/"):
            if origin != self.frontend_origin:
                raise web.HTTPForbidden(text="Origin not allowed")
            return web.Response(status=204)
        if (
            request.path.startswith("/api/")
            and request.method in {"POST", "PUT", "PATCH", "DELETE"}
            and origin != self.frontend_origin
        ):
            raise web.HTTPForbidden(text="Origin not allowed")
        return await handler(request)

    async def _add_cors_headers(
        self, request: web.Request, response: web.StreamResponse
    ) -> None:
        origin = request.headers.get("Origin")
        if origin == self.frontend_origin:
            response.headers["Access-Control-Allow-Origin"] = self.frontend_origin
            response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, OPTIONS"
            response.headers["Vary"] = "Origin"

    async def login(self, request: web.Request) -> web.Response:
        self._prune_expired()
        state = secrets.token_urlsafe(32)
        self.oauth_states[state] = time.time() + OAUTH_STATE_LIFETIME
        query = urlencode(
            {
                "client_id": self.client_id,
                "redirect_uri": self.redirect_uri,
                "response_type": "code",
                "scope": "identify",
                "state": state,
            }
        )
        response = web.HTTPFound(f"https://discord.com/oauth2/authorize?{query}")
        response.set_cookie(
            OAUTH_STATE_COOKIE,
            state,
            max_age=OAUTH_STATE_LIFETIME,
            httponly=True,
            secure=self.cookie_secure,
            samesite=self.cookie_samesite,
            path="/",
        )
        raise response

    async def callback(self, request: web.Request) -> web.Response:
        state = request.query.get("state", "")
        cookie_state = request.cookies.get(OAUTH_STATE_COOKIE, "")
        expires_at = self.oauth_states.get(state)
        if (
            not cookie_state
            or not secrets.compare_digest(state, cookie_state)
            or expires_at is None
            or expires_at < time.time()
        ):
            raise web.HTTPBadRequest(text="Invalid or expired OAuth state")
        self.oauth_states.pop(state, None)
        if request.query.get("error"):
            raise web.HTTPBadRequest(text="Discord authorization was not completed")
        code = request.query.get("code")
        if not code:
            raise web.HTTPBadRequest(text="Missing authorization code")
        if self.client is None:
            raise web.HTTPServiceUnavailable(text="OAuth client is not available")

        async with self.client.post(
            f"{DISCORD_API}/oauth2/token",
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": self.redirect_uri,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        ) as response:
            token_data = await response.json(content_type=None)
            if response.status != 200:
                logger.warning(
                    "Discord OAuth token exchange failed: %s", response.status
                )
                raise web.HTTPBadGateway(text="Discord authentication failed")

        async with self.client.get(
            f"{DISCORD_API}/users/@me",
            headers={"Authorization": f"Bearer {token_data['access_token']}"},
        ) as response:
            user_data = await response.json(content_type=None)
            if response.status != 200:
                logger.warning("Discord user lookup failed: %s", response.status)
                raise web.HTTPBadGateway(text="Could not retrieve Discord user")

        session_id = secrets.token_urlsafe(32)
        self.sessions[session_id] = WebSession(
            user_id=int(user_data["id"]),
            username=user_data["username"],
            expires_at=time.time() + SESSION_LIFETIME,
        )
        response = web.HTTPFound(self.frontend_origin + "/")
        response.set_cookie(
            SESSION_COOKIE,
            session_id,
            max_age=SESSION_LIFETIME,
            httponly=True,
            secure=self.cookie_secure,
            samesite=self.cookie_samesite,
            path="/",
        )
        response.del_cookie(
            OAUTH_STATE_COOKIE,
            path="/",
            secure=self.cookie_secure,
            httponly=True,
            samesite=self.cookie_samesite,
        )
        raise response

    async def me(self, request: web.Request) -> web.Response:
        session = self._get_session(request)
        if session is None:
            raise web.HTTPUnauthorized(text="Login required")
        return web.json_response(
            {"id": str(session.user_id), "username": session.username}
        )

    async def servers(self, request: web.Request) -> web.Response:
        session = self._get_session(request)
        if session is None:
            raise web.HTTPUnauthorized(text="Login required")
        if not self.bot.is_ready():
            raise web.HTTPServiceUnavailable(text="Discord bot is still connecting")

        result = []
        for guild_id in self.manager.list_servers():
            guild = self.bot.get_guild(guild_id)
            if guild is None:
                continue
            try:
                await self.manager.ensure_board_loaded(guild_id)
                self.manager.get_board(guild_id)
                member = await guild.fetch_member(session.user_id)
            except discord.NotFound:
                continue
            except NoGameError:
                continue
            except discord.HTTPException as error:
                logger.warning(
                    "Could not check web access for guild %s: %s",
                    guild_id,
                    error,
                )
                raise web.HTTPBadGateway(
                    text="Could not verify Discord server membership"
                ) from error
            if any(config.is_gm_role(role) for role in member.roles):
                result.append({"id": str(guild.id), "name": guild.name})

        return web.json_response(result)

    async def server_status(self, request: web.Request) -> web.Response:
        _, board = await self._authorized_board(request)
        raw_deadline = board.data.get("deadline")
        try:
            deadline = int(raw_deadline) if raw_deadline is not None else None
        except (TypeError, ValueError) as error:
            logger.exception("Invalid deadline stored for board %s", board.board_id)
            raise web.HTTPInternalServerError(
                text="Invalid deadline stored for this game"
            ) from error
        players = []
        for player in board.get_players():
            units = []
            missing_count = 0
            for unit in player.units:
                missing = False
                if board.turn.is_moves():
                    missing = unit.order is None
                elif board.turn.is_retreats():
                    missing = (
                        unit == unit.province.dislodged_unit
                        and bool(unit.retreat_options)
                        and unit.order is None
                    )
                if missing:
                    missing_count += 1
                units.append(
                    {
                        "name": str(unit),
                        "order": str(unit.order) if unit.order is not None else None,
                        "missing": missing,
                    }
                )

            build_orders = [str(order) for order in player.build_orders]
            if board.turn.is_builds():
                difference = len(player.centers) - len(player.units)
                current = player.waived_orders
                for order in player.build_orders:
                    if isinstance(order, Build):
                        current += 1
                    elif isinstance(order, Disband):
                        current -= 1
                missing_count += abs(current - difference)

            players.append(
                {
                    "name": player.get_name(),
                    "units": units,
                    "build_orders": build_orders,
                    "missing_order_count": missing_count,
                    "centers": [str(center) for center in player.centers],
                }
            )

        return web.json_response(
            {
                "game_name": board.data.get("game_name", board.data.get("name")),
                "turn": str(board.turn),
                "deadline": deadline,
                "orders_enabled": board.orders_enabled,
                "players": players,
                "missing_orders": any(
                    player["missing_order_count"] > 0 for player in players
                ),
            }
        )

    async def server_map(self, request: web.Request) -> web.Response:
        guild_id, _ = await self._authorized_board(request)
        try:
            svg, _ = self.manager.draw_map(guild_id)
        except MapRenderError as error:
            logger.exception("Could not render web map for guild %s", guild_id)
            raise web.HTTPBadGateway(text="Could not render game map") from error
        return web.Response(body=svg, content_type="image/svg+xml")

    async def set_deadline(self, request: web.Request) -> web.Response:
        guild_id, board = await self._authorized_board(request)
        try:
            payload = await request.json()
        except (ValueError, web.HTTPBadRequest) as error:
            raise web.HTTPBadRequest(text="Expected a JSON request body") from error

        if not isinstance(payload, dict) or "deadline" not in payload:
            raise web.HTTPBadRequest(text="Provide deadline as a timestamp or null")
        new_deadline = payload["deadline"]
        if new_deadline is not None and (
            isinstance(new_deadline, bool)
            or not isinstance(new_deadline, int)
            or new_deadline < 1
        ):
            raise web.HTTPBadRequest(text="Deadline must be a positive Unix timestamp")

        if new_deadline is None:
            board.custom_data.pop("deadline", None)
            board.data.pop("deadline", None)
            get_connection().execute_arbitrary_sql(
                "DELETE FROM board_parameters WHERE board_id = ? AND parameter_key = ?",
                (board.board_id, "deadline"),
            )
        else:
            old_deadline = int(board.data.get("deadline", time.time()))
            schedule_cog = self.bot.get_cog("ScheduleCog")
            if schedule_cog is not None:
                await schedule_cog.adjust_repeated_tasks(
                    board, timedelta(seconds=new_deadline - old_deadline)
                )
            board.set_data("deadline", new_deadline)
            get_connection().execute_arbitrary_sql(
                "INSERT OR REPLACE INTO board_parameters "
                "(board_id, parameter_key, parameter_value) VALUES (?, ?, ?)",
                (board.board_id, "deadline", new_deadline),
            )

        logger.info("Web user changed deadline for guild %s", guild_id)
        return web.json_response({"deadline": new_deadline})

    async def adjudicate(self, request: web.Request) -> web.Response:
        guild_id, board = await self._authorized_board(request)
        try:
            payload = await request.json()
        except (ValueError, web.HTTPBadRequest) as error:
            raise web.HTTPBadRequest(text="Expected a JSON request body") from error
        if not isinstance(payload, dict):
            raise web.HTTPBadRequest(text="Expected a JSON object")
        force = payload.get("force", False)
        test = payload.get("test", False)
        if not isinstance(force, bool) or not isinstance(test, bool):
            raise web.HTTPBadRequest(text="force and test must be booleans")

        missing = self._missing_order_count(board)
        if missing and not force and not test:
            return web.json_response(
                {
                    "error": "Orders are missing. Confirm force adjudication to continue.",
                    "missing_order_count": missing,
                },
                status=409,
            )
        message, new_board = self.manager.adjudicate(guild_id, test=test)
        logger.info(
            "Web user requested %s adjudication for guild %s",
            "test" if test else "live",
            guild_id,
        )
        return web.json_response(
            {
                "turn": str(new_board.turn),
                "test": test,
                "message": message,
            }
        )

    async def logout(self, request: web.Request) -> web.Response:
        session_id = request.cookies.get(SESSION_COOKIE)
        if session_id:
            self.sessions.pop(session_id, None)
        response = web.json_response({"ok": True})
        response.del_cookie(
            SESSION_COOKIE,
            path="/",
            secure=self.cookie_secure,
            httponly=True,
            samesite=self.cookie_samesite,
        )
        return response

    async def _authorized_board(self, request: web.Request) -> tuple[int, Board]:
        session = self._get_session(request)
        if session is None:
            raise web.HTTPUnauthorized(text="Login required")
        if not self.bot.is_ready():
            raise web.HTTPServiceUnavailable(text="Discord bot is still connecting")
        guild_id = int(request.match_info["guild_id"])
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            raise web.HTTPNotFound(text="Server not found")
        try:
            member = await guild.fetch_member(session.user_id)
        except discord.NotFound as error:
            raise web.HTTPForbidden(text="GM role required") from error
        except discord.HTTPException as error:
            logger.warning(
                "Could not check web access for guild %s: %s", guild_id, error
            )
            raise web.HTTPBadGateway(
                text="Could not verify Discord server membership"
            ) from error
        if not any(config.is_gm_role(role) for role in member.roles):
            raise web.HTTPForbidden(text="GM role required")

        try:
            await self.manager.ensure_board_loaded(guild_id)
            board = self.manager.get_board(guild_id)
        except NoGameError as error:
            raise web.HTTPNotFound(text="Game not found") from error
        return guild_id, board

    def _get_session(self, request: web.Request) -> WebSession | None:
        session_id = request.cookies.get(SESSION_COOKIE)
        session = self.sessions.get(session_id or "")
        if session is None:
            return None
        if session.expires_at <= time.time():
            self.sessions.pop(session_id or "", None)
            return None
        return session

    def _prune_expired(self) -> None:
        now = time.time()
        self.sessions = {
            key: value for key, value in self.sessions.items() if value.expires_at > now
        }
        self.oauth_states = {
            key: value for key, value in self.oauth_states.items() if value > now
        }

    @staticmethod
    def _missing_order_count(board: Board) -> int:
        if board.turn.is_moves():
            return sum(unit.order is None for unit in board.units)
        if board.turn.is_retreats():
            return sum(
                unit == unit.province.dislodged_unit
                and bool(unit.retreat_options)
                and unit.order is None
                for unit in board.units
            )
        if board.turn.is_builds():
            missing = 0
            for player in board.get_players():
                count = len(player.centers) - len(player.units)
                current = player.waived_orders
                for order in player.build_orders:
                    if isinstance(order, Build):
                        current += 1
                    elif isinstance(order, Disband):
                        current -= 1
                missing += abs(current - count)
            return missing
        return 0
