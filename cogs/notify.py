from __future__ import annotations

import traceback
from datetime import datetime, time, timedelta
from difflib import get_close_matches
from typing import TYPE_CHECKING, Any, Literal, Tuple

# Standard
import discord
from discord import Forbidden, HTTPException, Interaction, app_commands
from discord.ext import commands, tasks

from utils.errors import ValorantBotError
from utils.locale_v2 import ValorantTranslator
from utils.valorant import view as View
from utils.valorant.cache import create_json
from utils.valorant.db import DATABASE
from utils.valorant.embed import Embed, GetEmbed
from utils.valorant.endpoint import API_ENDPOINT
from utils.valorant.local import ResponseLanguage
from utils.valorant.useful import JSON, GetEmoji, GetItems, format_relative

VLR_locale = ValorantTranslator()

if TYPE_CHECKING:
    from bot import ValorantBot


class Notify(commands.Cog):
    def __init__(self, bot: ValorantBot) -> None:
        self.bot: ValorantBot = bot
        self.endpoint: API_ENDPOINT = None
        self.db: DATABASE = None
        self.notifys.start()

    def cog_unload(self) -> None:
        self.notifys.cancel()

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        self.db = DATABASE()
        self.endpoint = API_ENDPOINT()

    async def get_endpoint_and_data(self, user_id: int) -> Tuple[API_ENDPOINT, Any]:
        data = await self.db.is_data(user_id, 'en-US')
        endpoint = self.endpoint
        endpoint.activate(data)
        return endpoint, data

    async def send_notify(self) -> None:
        notify_users = self.db.get_user_is_notify()
        notify_data = JSON.read('notifys')

        for user_id in notify_users:
            try:

                # endpoint
                endpoint, data = await self.get_endpoint_and_data(int(user_id))

                # offer
                offer = endpoint.store_fetch_storefront()
                skin_offer_list = offer["SkinsPanelLayout"]["SingleItemOffers"]
                duration = offer["SkinsPanelLayout"]["SingleItemOffersRemainingDurationInSeconds"]

                # author
                author = self.bot.get_user(int(user_id)) or await self.bot.fetch_user(int(user_id))
                channel_send = author if data['dm_message'] else self.bot.get_channel(int(data['notify_channel']))

                # get guild language
                guild_locale = 'en-US'
                get_guild_locale = [guild.preferred_locale for guild in self.bot.guilds if channel_send in guild.channels]
                if len(get_guild_locale) > 0:
                    guild_locale = guild_locale[0]

                response = ResponseLanguage('notify_send', guild_locale)

                user_skin_list = [skin for skin in notify_data if skin['id'] == str(user_id)]
                user_skin_list_uuid = [skin['uuid'] for skin in notify_data if skin['id'] == str(user_id)]

                if data['notify_mode'] == 'Specified':
                    skin_notify_list = list(set(skin_offer_list).intersection(set(user_skin_list_uuid)))
                    for noti in user_skin_list:
                        if noti['uuid'] in skin_notify_list:
                            uuid = noti['uuid']
                            skin = GetItems.get_skin(uuid)
                            name = skin['names'][guild_locale]
                            icon = skin['icon']
                            emoji = GetEmoji.tier_by_bot(uuid, self.bot)

                            notify_send: str = response.get('RESPONSE_SPECIFIED')
                            duration = format_relative(datetime.utcnow() + timedelta(seconds=duration))

                            embed = Embed(notify_send.format(emoji=emoji, name=name, duration=duration), color=0xFD4554)
                            embed.set_thumbnail(url=icon)
                            view = View.NotifyView(user_id, uuid, name, ResponseLanguage('notify_add', guild_locale))
                            view.message = await channel_send.send(content=f'||{author.mention}||', embed=embed, view=view)

                elif data['notify_mode'] == 'All':
                    embeds = GetEmbed.notify_all_send(endpoint.player, offer, response, self.bot)
                    await channel_send.send(content=f'||{author.mention}||', embeds=embeds)

            except (KeyError, FileNotFoundError):
                print(f'{user_id} is not in notify list')
            except Forbidden:
                print("Bot don't have perm send notification message.")
                continue
            except HTTPException:
                print("Bot Can't send notification message.")
                continue
            except Exception as e:
                print(e)
                traceback.print_exception(type(e), e, e.__traceback__)
                continue

async def setup(bot: ValorantBot) -> None:
    await bot.add_cog(Notify(bot))
