from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, Literal  # noqa: F401

from discord import Interaction, app_commands, ui
from discord.ext import commands, tasks
from discord.utils import MISSING

from utils.checks import owner_only
from utils.errors import ValorantBotError
from utils.locale_v2 import ValorantTranslator
from utils.valorant import cache as Cache, useful, view as View
from utils.valorant.db import DATABASE
from utils.valorant.embed import Embed, GetEmbed
from utils.valorant.endpoint import API_ENDPOINT
from utils.valorant.local import ResponseLanguage
from utils.valorant.resources import setup_emoji

VLR_locale = ValorantTranslator()

if TYPE_CHECKING:
    from bot import ValorantBot


class ValorantCog(commands.Cog, name='Valorant'):
    """Valorant API Commands"""

    def __init__(self, bot: ValorantBot) -> None:
        self.bot: ValorantBot = bot
        self.endpoint: API_ENDPOINT = None
        self.db: DATABASE = None
        self.reload_cache.start()

    def cog_unload(self) -> None:
        self.reload_cache.cancel()

    def funtion_reload_cache(self, force=False) -> None:
        """Reload the cache"""
        with contextlib.suppress(Exception):
            cache = self.db.read_cache()
            valorant_version = Cache.get_valorant_version()
            if valorant_version != cache['valorant_version'] or force:
                Cache.get_cache()
                cache = self.db.read_cache()
                cache['valorant_version'] = valorant_version
                self.db.insert_cache(cache)
                print('Updated cache')

    @tasks.loop(minutes=30)
    async def reload_cache(self) -> None:
        """Reload the cache every 30 minutes"""
        self.funtion_reload_cache()

    @reload_cache.before_loop
    async def before_reload_cache(self) -> None:
        """Wait for the bot to be ready before reloading the cache"""
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        """When the bot is ready"""
        self.db = DATABASE()
        self.endpoint = API_ENDPOINT()

    async def get_endpoint(
        self, user_id: int, locale_code: str = None, username: str = None, password: str = None
    ) -> API_ENDPOINT:
        """Get the endpoint for the user"""
        if username is not None and password is not None:
            auth = self.db.auth
            auth.locale_code = locale_code
            data = await auth.temp_auth(username, password)
        elif username or password:
            raise ValorantBotError(f"Please provide both username and password!")
        else:
            data = await self.db.is_data(user_id, locale_code)
        data['locale_code'] = locale_code
        endpoint = self.endpoint
        endpoint.activate(data)
        return endpoint

    @app_commands.command(description='use this command to connect your riot account')
    @app_commands.describe(username='Input username', password='Input password')
    # @dynamic_cooldown(cooldown_5s)
    async def login(self, interaction: Interaction, username: str, password: str) -> None:

        response = ResponseLanguage(interaction.command.name, interaction.locale)

        user_id = interaction.user.id
        auth = self.db.auth
        auth.locale_code = interaction.locale
        authenticate = await auth.authenticate(username, password)

        if authenticate['auth'] == 'response':
            await interaction.response.defer(ephemeral=True)
            login = await self.db.login(user_id, authenticate, interaction.locale)

            if login['auth']:
                embed = Embed(f"{response.get('SUCCESS')}")
                return await interaction.followup.send(embed=embed, ephemeral=True)

            raise ValorantBotError(f"{response.get('FAILED')}")

        elif authenticate['auth'] == '2fa':
            cookies = authenticate['cookie']
            message = authenticate['message']
            label = authenticate['label']
            modal = View.TwoFA_UI(interaction, self.db, cookies, message, label, response)
            await interaction.response.send_modal(modal)

    @app_commands.command(description='removes your account from database')
    # @dynamic_cooldown(cooldown_5s)
    async def logout(self, interaction: Interaction) -> None:

        await interaction.response.defer(ephemeral=True)

        response = ResponseLanguage(interaction.command.name, interaction.locale)

        user_id = interaction.user.id
        if logout := self.db.logout(user_id, interaction.locale):
            if logout:
                embed = Embed(response.get('SUCCESS'))
                return await interaction.followup.send(embed=embed, ephemeral=True)
            raise ValorantBotError(response.get('FAILED'))

    @app_commands.command(description="shows your store in your account")
    @app_commands.guild_only()
    # @dynamic_cooldown(cooldown_5s)
    async def store(self, interaction: Interaction) -> None:

        # language
        response = ResponseLanguage(interaction.command.name, interaction.locale)

        # check if user is logged in
        await interaction.response.defer(ephemeral=False)

        # setup emoji
        await setup_emoji(self.bot, interaction.guild, interaction.locale)

        # get endpoint
        endpoint = await self.get_endpoint(interaction.user.id, interaction.locale)

        # fetch skin price
        skin_price = endpoint.store_fetch_offers()
        self.db.insert_skin_price(skin_price)

        # data
        data = endpoint.store_fetch_storefront()
        embeds = GetEmbed.store(endpoint.player, data, response, self.bot)
        await interaction.followup.send(
            embeds=embeds, view=MISSING
        )

async def setup(bot: ValorantBot) -> None:
    await bot.add_cog(ValorantCog(bot))
