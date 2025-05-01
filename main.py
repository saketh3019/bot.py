"""
Enhanced Giveaway Bot

Supported Slash Commands are listed at the end of the file.
"""

import discord
from discord.ext import commands
import asyncio
import random
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

# ------------------------------
# Logging Setup
# ------------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("discord_bot")

# ------------------------------
# Bot Setup with Required Intents
# ------------------------------
intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix='/', intents=intents)

# ------------------------------
# Global Variables and Persistent Storage
# ------------------------------

# Global variable for public leaderboard channel.
leaderboard_channel_id: Optional[int] = None

data_file = "data.json"
try:
    with open(data_file, "r") as file:
        data = json.load(file)
        giveaways = data.get("giveaways", {})             # Active giveaways (by giveaway_id)
        ended_giveaways = data.get("ended_giveaways", {})   # Ended giveaways (for reroll)
        authorized_roles = set(data.get("authorized_roles", []))
        authorized_members = set(data.get("authorized_members", []))
        blacklist = {
            "roles": set(data.get("blacklisted_roles", [])),
            "members": set(data.get("blacklisted_members", []))
        }
        bonus_entries = data.get("bonus_entries", {})
except FileNotFoundError:
    giveaways = {}
    ended_giveaways = {}
    authorized_roles = set()
    authorized_members = set()
    blacklist = {"roles": set(), "members": set()}
    bonus_entries = {}

# Host (owner) ID – only the owner and allowed users/roles may use restricted commands.
owner_id = 823941482411065395  # sakethisnoob

def save_data():
    """Saves persistent data into data.json."""
    with open(data_file, "w") as file:
        json.dump({
            "giveaways": giveaways,
            "ended_giveaways": ended_giveaways,
            "authorized_roles": list(authorized_roles),
            "authorized_members": list(authorized_members),
            "blacklisted_roles": list(blacklist["roles"]),
            "blacklisted_members": list(blacklist["members"]),
            "bonus_entries": bonus_entries
        }, file)

# ------------------------------
# Helper Functions
# ------------------------------

def parse_duration(duration_str: str) -> int:
    """Parse a duration string like '1h30m' into total seconds."""
    time_units = {'d': 86400, 'h': 3600, 'm': 60, 's': 1}
    pattern = r'(\d+)([dhms])'
    matches = re.findall(pattern, duration_str)
    total_seconds = 0
    for value, unit in matches:
        total_seconds += int(value) * time_units[unit]
    return total_seconds

def create_embed(title: str, description: str, color=discord.Color.blue()) -> discord.Embed:
    """Creates an embed with the given title, description, and color."""
    return discord.Embed(title=title, description=description, color=color)

def is_owner(user_id: int) -> bool:
    """Check if a given user_id is the designated owner."""
    return user_id == owner_id

def is_blacklisted(user_id: int) -> bool:
    """Return True if the user is blacklisted."""
    return user_id in blacklist["members"]

# ------------------------------
# Leaderboard Update Function
# ------------------------------
async def update_leaderboard(giveaway_id: int):
    """
    Update the leaderboard embed. If a public leaderboard channel is set (and a corresponding message exists), update that message.
    Otherwise, update the DM leaderboard for the giveaway starter.
    """
    giveaway = giveaways.get(giveaway_id)
    if not giveaway:
        return
    leaderboard_text = ("No participants yet." if not giveaway["participants"]
                        else "\n".join([
                            f"{i+1}. <@{participant}>"
                            for i, participant in enumerate(giveaway["participants"])
                        ]))
    embed = create_embed(f"Leaderboard for Giveaway {giveaway_id}", leaderboard_text, color=discord.Color.green())
    if leaderboard_channel_id is not None and "public_lb_message_id" in giveaway:
        channel = bot.get_channel(leaderboard_channel_id)
        if channel:
            try:
                message = await channel.fetch_message(giveaway["public_lb_message_id"])
                await message.edit(embed=embed)
                return
            except Exception as e:
                logger.error(f"Error updating public leaderboard for giveaway {giveaway_id}: {e}")
    # Fallback: update DM leaderboard for the giveaway starter.
    starter_id = giveaway.get("starter_id")
    lb_message_id = giveaway.get("lb_message_id")
    if not starter_id or not lb_message_id:
        return
    user = bot.get_user(starter_id) or await bot.fetch_user(starter_id)
    dm_channel = user.dm_channel or await user.create_dm()
    try:
        message = await dm_channel.fetch_message(lb_message_id)
        await message.edit(embed=embed)
    except Exception as e:
        logger.error(f"Error updating DM leaderboard for giveaway {giveaway_id}: {e}")

# ------------------------------
# Modal for /gselect in DMs
# ------------------------------
class GiveawayIDModal(discord.ui.Modal, title="Enter Giveaway ID"):
    giveaway_id_input = discord.ui.TextInput(label="Giveaway ID", style=discord.TextStyle.short)
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.send_message("Giveaway ID received.", ephemeral=True)

# ------------------------------
# Giveaway Participation View (Buttons)
# ------------------------------
class GiveawayView(discord.ui.View):
    def __init__(self, giveaway_id: int):
        super().__init__(timeout=None)
        self.giveaway_id = giveaway_id

    @discord.ui.button(label="Enter Giveaway", style=discord.ButtonStyle.primary, custom_id="enter_giveaway")
    async def enter_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.giveaway_id not in giveaways:
            await interaction.response.send_message("This giveaway doesn't exist or has ended.", ephemeral=True)
            return
        giveaway = giveaways[self.giveaway_id]
        if interaction.user.id in giveaway["participants"]:
            await interaction.response.send_message("You have already entered the giveaway.", ephemeral=True)
            return
        giveaway["participants"].append(interaction.user.id)
        save_data()
        await interaction.response.send_message("You have entered the giveaway.", ephemeral=True)
        await update_leaderboard(self.giveaway_id)

    @discord.ui.button(label="Leave Giveaway", style=discord.ButtonStyle.secondary, custom_id="leave_giveaway")
    async def leave_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.giveaway_id not in giveaways:
            await interaction.response.send_message("This giveaway doesn't exist or has ended.", ephemeral=True)
            return
        giveaway = giveaways[self.giveaway_id]
        if interaction.user.id not in giveaway["participants"]:
            await interaction.response.send_message("You are not participating in this giveaway.", ephemeral=True)
            return
        giveaway["participants"].remove(interaction.user.id)
        if "selected_winners" in giveaway and interaction.user.id in giveaway["selected_winners"]:
            giveaway["selected_winners"].remove(interaction.user.id)
        save_data()
        await interaction.response.send_message("You have left the giveaway.", ephemeral=True)
        await update_leaderboard(self.giveaway_id)

# ------------------------------
# Giveaway Ending Functions
# ------------------------------
async def end_giveaway(giveaway_id: int):
    """
    End a giveaway by determining the winners (using manual selection if available, otherwise random),
    updating the announcement messages, and moving the giveaway to ended_giveaways for possible reroll.
    """
    if giveaway_id not in giveaways:
        return
    giveaway = giveaways[giveaway_id]
    if giveaway["method"] == "manual" and giveaway.get("selected_winners"):
        final_winners = giveaway["selected_winners"]
    elif giveaway["method"] == "automatic":
        if giveaway["participants"]:
            final_winners = random.sample(giveaway["participants"], min(giveaway["winners_count"], len(giveaway["participants"])))
        else:
            final_winners = []
    else:
        final_winners = []
    channel = bot.get_channel(giveaway.get("announcement_channel_id"))
    if channel:
        try:
            ann_message = await channel.fetch_message(giveaway.get("announcement_message_id"))
            ann_embed = create_embed("🎉 Giveaway Ended!",
                                     f"Prize: {giveaway['prize']}\nGiveaway has ended.",
                                     color=discord.Color.red())
            await ann_message.edit(embed=ann_embed, view=None)
        except Exception as e:
            logger.error(f"Error updating announcement for giveaway {giveaway_id}: {e}")
    if final_winners:
        result_embed = create_embed(
            f"🎉 Giveaway {giveaway_id} Ended",
            f"Winners: {', '.join([f'<@{w}>' for w in final_winners])}\nPrize: {giveaway['prize']}",
            color=discord.Color.green()
        )
        if channel:
            await channel.send(embed=result_embed)
        else:
            host = bot.get_user(giveaway["starter_id"]) or await bot.fetch_user(giveaway["starter_id"])
            dm_channel = host.dm_channel or await host.create_dm()
            await dm_channel.send(embed=result_embed)
    else:
        if channel:
            await channel.send(f"Giveaway {giveaway_id} ended with no participants.")
    starter = bot.get_user(giveaway["starter_id"]) or await bot.fetch_user(giveaway["starter_id"])
    dm_channel = starter.dm_channel or await starter.create_dm()
    try:
        lb_message = await dm_channel.fetch_message(giveaway["lb_message_id"])
        leaderboard = "\n".join([f"{i+1}. <@{p}>" for i, p in enumerate(giveaway["participants"])])
        lb_embed = create_embed(f"Leaderboard for Giveaway {giveaway_id}", leaderboard if leaderboard else "No participants.", color=discord.Color.green())
        await lb_message.edit(embed=lb_embed)
    except Exception as e:
        logger.error(f"Error updating final leaderboard for giveaway {giveaway_id}: {e}")
    ended_giveaways[giveaway_id] = giveaway
    del giveaways[giveaway_id]
    save_data()

async def end_giveaway_task(giveaway_id: int, delay: int):
    await asyncio.sleep(delay)
    await end_giveaway(giveaway_id)

# ------------------------------
# on_ready Event for Server-Agnostic Sync
# ------------------------------
@bot.event
async def on_ready():
    # Sync commands for every guild the bot is in
    for guild in bot.guilds:
        try:
            await bot.tree.sync(guild=guild)
        except Exception as e:
            logger.error(f"Error syncing for guild {guild.id}: {e}")
    await bot.tree.sync()  # Global sync
    logger.info(f"Bot logged in as {bot.user}")
    print(f"{bot.user} is now online and ready to use!")

# ------------------------------
# Giveaway Commands
# ------------------------------

@bot.tree.command(name="gstart", description="Start a giveaway. (Restricted access)")
@discord.app_commands.describe(
    duration="Duration (e.g., '1h30m', '50s', '2d5h')",
    winners="Number of winners",
    prize="Prize for the giveaway",
    method="Selection method: 'automatic' or 'manual'"
)
async def gstart(interaction: discord.Interaction, duration: str, winners: int, prize: str, method: str):
    if not (is_owner(interaction.user.id) or interaction.user.id in authorized_members or any(role.id in authorized_roles for role in interaction.user.roles)):
        await interaction.response.send_message("You are not allowed to use /gstart.", ephemeral=True)
        return
    if is_blacklisted(interaction.user.id):
        await interaction.response.send_message("You are blacklisted and cannot start giveaways.", ephemeral=True)
        return
    try:
        duration_sec = parse_duration(duration)
        method = method.lower()
        if method not in ["automatic", "manual"]:
            raise ValueError("Invalid method! Use 'automatic' or 'manual'.")
        end_time = datetime.now(timezone.utc) + timedelta(seconds=duration_sec)
        end_timestamp = int(end_time.timestamp())
        giveaway_id = random.randint(1000, 9999)
        giveaways[giveaway_id] = {
            "prize": prize,
            "duration": duration_sec,
            "winners_count": winners,
            "method": method,
            "participants": [],
            "starter_id": interaction.user.id,
            "selected_winners": []
        }
        embed = create_embed("🎉 Giveaway Started!",
                             f"Prize: {prize}\nWinners: {winners}\nEnds: <t:{end_timestamp}:R>",
                             color=discord.Color.blurple())
        view = GiveawayView(giveaway_id)
        await interaction.response.send_message(embed=embed, view=view)
        announcement_message = await interaction.original_response()
        giveaways[giveaway_id]["announcement_message_id"] = announcement_message.id
        giveaways[giveaway_id]["announcement_channel_id"] = interaction.channel.id
        # Public leaderboard: if a channel is set, put the leaderboard there.
        if leaderboard_channel_id is not None:
            channel = bot.get_channel(leaderboard_channel_id)
            if channel:
                lb_embed = create_embed(f"Leaderboard for Giveaway {giveaway_id}", "No participants yet.", color=discord.Color.green())
                public_lb_message = await channel.send(embed=lb_embed)
                giveaways[giveaway_id]["public_lb_message_id"] = public_lb_message.id
        else:
            lb_embed = create_embed(f"Leaderboard for Giveaway {giveaway_id}", "No participants yet.", color=discord.Color.green())
            dm_channel = interaction.user.dm_channel or await interaction.user.create_dm()
            lb_message = await dm_channel.send(embed=lb_embed)
            giveaways[giveaway_id]["lb_message_id"] = lb_message.id
        save_data()
        bot.loop.create_task(end_giveaway_task(giveaway_id, duration_sec))
    except ValueError as ve:
        await interaction.response.send_message(f"Error: {ve}", ephemeral=True)
    except Exception as e:
        logger.error(f"Error in /gstart: {e}")
        await interaction.response.send_message("An unexpected error occurred.", ephemeral=True)

@bot.tree.command(name="gend", description="End a giveaway.")
async def gend(interaction: discord.Interaction, giveaway_id: int):
    if giveaway_id not in giveaways:
        await interaction.response.send_message("Invalid giveaway ID.", ephemeral=True)
        return
    await end_giveaway(giveaway_id)
    await interaction.response.send_message("Giveaway ended.", ephemeral=True)

@bot.tree.command(name="gcancle", description="Cancel an active giveaway.")
async def gcancle(interaction: discord.Interaction, giveaway_id: int):
    if not is_owner(interaction.user.id):
        await interaction.response.send_message("Only host can use /gcancle.", ephemeral=True)
        return
    if giveaway_id not in giveaways:
        await interaction.response.send_message("Invalid giveaway ID.", ephemeral=True)
        return
    del giveaways[giveaway_id]
    save_data()
    await interaction.response.send_message(f"Giveaway {giveaway_id} has been cancelled.", ephemeral=True)

@bot.tree.command(name="gswitch", description="Switch the giveaway mode.")
@discord.app_commands.describe(
    giveaway_id="Giveaway ID",
    new_mode="New mode: 'automatic' or 'manual'"
)
async def gswitch(interaction: discord.Interaction, giveaway_id: int, new_mode: str):
    if not is_owner(interaction.user.id):
        await interaction.response.send_message("Only host can use /gswitch.", ephemeral=True)
        return
    new_mode = new_mode.lower()
    if new_mode not in ["automatic", "manual"]:
        await interaction.response.send_message("Invalid mode; use 'automatic' or 'manual'.", ephemeral=True)
        return
    if giveaway_id not in giveaways:
        await interaction.response.send_message("Invalid giveaway ID.", ephemeral=True)
        return
    giveaways[giveaway_id]["method"] = new_mode
    save_data()
    await interaction.response.send_message(f"Giveaway {giveaway_id} mode switched to {new_mode}.", ephemeral=True)

@bot.tree.command(name="gselect", description="Manually select winner(s) for a manual giveaway.")
@discord.app_commands.describe(
    giveaway_id="(Optional in DMs) Giveaway ID",
    friend_ids="Comma-separated numeric user IDs (e.g., '123456789012345678,987654321098765432')"
)
async def gselect(interaction: discord.Interaction, friend_ids: str, giveaway_id: Optional[int] = None):
    if not (is_owner(interaction.user.id) or interaction.user.id in authorized_members or any(role.id in authorized_roles for role in interaction.user.roles)):
        await interaction.response.send_message("You are not allowed to use /gselect.", ephemeral=True)
        return
    if interaction.guild is None and giveaway_id is None:
        modal = GiveawayIDModal()
        modal.custom_id = "giveawayid_modal"
        await interaction.response.send_modal(modal)
        try:
            result = await bot.wait_for("modal_submit", timeout=60.0, check=lambda i: i.user.id == interaction.user.id and i.custom_id == "giveawayid_modal")
        except asyncio.TimeoutError:
            await interaction.followup.send("Timed out waiting for Giveaway ID.", ephemeral=True)
            return
        try:
            giveaway_id = int(result.children[0].value)
        except ValueError:
            await interaction.followup.send("Invalid giveaway ID provided.", ephemeral=True)
            return
    if giveaway_id is None:
        await interaction.response.send_message("Giveaway ID is required.", ephemeral=True)
        return
    if giveaway_id not in giveaways:
        await interaction.response.send_message("Invalid giveaway ID.", ephemeral=True)
        return
    giveaway = giveaways[giveaway_id]
    if giveaway["method"] != "manual":
        await interaction.response.send_message("This giveaway is not set to manual mode.", ephemeral=True)
        return
    friend_id_list = [s.strip() for s in friend_ids.split(",") if s.strip()]
    try:
        friend_ids_int = [int(uid) for uid in friend_id_list]
    except ValueError:
        await interaction.response.send_message("Please provide valid numeric user IDs.", ephemeral=True)
        return
    if len(friend_ids_int) != giveaway["winners_count"]:
        await interaction.response.send_message(f"Number of winners must equal {giveaway['winners_count']}.", ephemeral=True)
        return
    missing = [str(uid) for uid in friend_ids_int if uid not in giveaway["participants"]]
    if missing:
        await interaction.response.send_message("The following user IDs are not participating: " + ", ".join(missing), ephemeral=True)
        return
    giveaway["selected_winners"] = friend_ids_int
    save_data()
    await interaction.response.send_message("Winner selection saved. The specified winner(s) will be announced when the giveaway ends.", ephemeral=True)

@bot.tree.command(name="reroll", description="Reroll winners for an ended giveaway. (Restricted access)")
@discord.app_commands.describe(
    giveaway_id="Giveaway ID"
)
async def reroll(interaction: discord.Interaction, giveaway_id: int):
    if not (is_owner(interaction.user.id) or interaction.user.id in authorized_members or any(role.id in authorized_roles for role in interaction.user.roles)):
        await interaction.response.send_message("You are not allowed to use /reroll.", ephemeral=True)
        return
    if giveaway_id not in ended_giveaways:
        await interaction.response.send_message("Giveaway ID not found in ended giveaways. It may not have ended or does not exist.", ephemeral=True)
        return
    ended_giveaway = ended_giveaways[giveaway_id]
    if not ended_giveaway["participants"]:
        await interaction.response.send_message("No participants available for reroll.", ephemeral=True)
        return
    new_winners = random.sample(ended_giveaway["participants"], min(ended_giveaway["winners_count"], len(ended_giveaway["participants"])))
    ended_giveaway["selected_winners"] = new_winners
    save_data()
    channel = bot.get_channel(ended_giveaway.get("announcement_channel_id"))
    new_embed = create_embed(f"🔄 Giveaway {giveaway_id} Rerolled",
                             f"New Winners: {', '.join([f'<@{w}>' for w in new_winners])}\nPrize: {ended_giveaway['prize']}",
                             color=discord.Color.blurple())
    if channel:
        await channel.send(embed=new_embed)
    await interaction.response.send_message("Reroll complete.", ephemeral=True)

# ------------------------------
# Administration Commands
# ------------------------------

@bot.tree.command(name="setleaderboardchannel", description="Set the channel for public leaderboard updates. (Owner only)")
async def setleaderboardchannel(interaction: discord.Interaction, channel: discord.TextChannel):
    global leaderboard_channel_id
    if not is_owner(interaction.user.id):
        await interaction.response.send_message("Only host can set the leaderboard channel.", ephemeral=True)
        return
    leaderboard_channel_id = channel.id
    await interaction.response.send_message(f"Leaderboard channel set to {channel.mention}.", ephemeral=True)

@bot.tree.command(name="gallow", description="Allow a member or role privileged access. (Owner only)")
async def gallow(interaction: discord.Interaction, member: discord.Member = None, role: discord.Role = None):
    if not is_owner(interaction.user.id):
        await interaction.response.send_message("Only host can use /gallow.", ephemeral=True)
        return
    if member is None and role is None:
        await interaction.response.send_message("Please specify a member or role.", ephemeral=True)
        return
    message = ""
    if member:
        authorized_members.add(member.id)
        message += f"Allowed member {member.mention}.\n"
    if role:
        authorized_roles.add(role.id)
        message += f"Allowed role {role.mention}.\n"
    save_data()
    await interaction.response.send_message(message, ephemeral=True)

@bot.tree.command(name="gnotallow", description="Revoke allowed status from a member or role. (Owner only)")
async def gnotallow(interaction: discord.Interaction, member: discord.Member = None, role: discord.Role = None):
    if not is_owner(interaction.user.id):
        await interaction.response.send_message("Only host can use /gnotallow.", ephemeral=True)
        return
    if member is None and role is None:
        await interaction.response.send_message("Please specify a member or role.", ephemeral=True)
        return
    message = ""
    if member:
        if member.id in authorized_members:
            authorized_members.remove(member.id)
            message += f"Removed allowed status for member {member.mention}.\n"
        else:
            message += f"Member {member.mention} is not allowed.\n"
    if role:
        if role.id in authorized_roles:
            authorized_roles.remove(role.id)
            message += f"Removed allowed status for role {role.mention}.\n"
        else:
            message += f"Role {role.mention} is not allowed.\n"
    save_data()
    await interaction.response.send_message(message, ephemeral=True)

@bot.tree.command(name="gallowlist", description="List all allowed members and roles. (Owner only)")
async def gallowlist(interaction: discord.Interaction):
    if not is_owner(interaction.user.id):
        await interaction.response.send_message("Only host can use /gallowlist.", ephemeral=True)
        return
    member_list = []
    for mem_id in authorized_members:
        member = bot.get_user(mem_id) or await bot.fetch_user(mem_id)
        member_list.append(member.mention if member else str(mem_id))
    role_list = [f"<@&{role_id}>" for role_id in authorized_roles]
    msg = (f"Allowed Members: {', '.join(member_list) if member_list else 'None'}\n"
           f"Allowed Roles: {', '.join(role_list) if role_list else 'None'}")
    await interaction.response.send_message(msg, ephemeral=True)

@bot.tree.command(name="gblacklist", description="Blacklist a member or role from using bot commands. (Owner only)")
async def gblacklist(interaction: discord.Interaction, member: discord.Member = None, role: discord.Role = None):
    if not is_owner(interaction.user.id):
        await interaction.response.send_message("Only host can use /gblacklist.", ephemeral=True)
        return
    if member is None and role is None:
        await interaction.response.send_message("Specify a member or role to blacklist.", ephemeral=True)
        return
    message = ""
    if member:
        blacklist["members"].add(member.id)
        message += f"Blacklisted member {member.mention}.\n"
    if role:
        blacklist["roles"].add(role.id)
        message += f"Blacklisted role {role.mention}.\n"
    save_data()
    await interaction.response.send_message(message, ephemeral=True)

@bot.tree.command(name="gremoveblacklist", description="Remove a member or role from the blacklist. (Owner only)")
async def gremoveblacklist(interaction: discord.Interaction, member: discord.Member = None, role: discord.Role = None):
    if not is_owner(interaction.user.id):
        await interaction.response.send_message("Only host can use /gremoveblacklist.", ephemeral=True)
        return
    if member is None and role is None:
        await interaction.response.send_message("Specify a member or role to remove from blacklist.", ephemeral=True)
        return
    message = ""
    if member:
        if member.id in blacklist["members"]:
            blacklist["members"].remove(member.id)
            message += f"Removed {member.mention} from blacklist.\n"
        else:
            message += f"Member {member.mention} is not blacklisted.\n"
    if role:
        if role.id in blacklist["roles"]:
            blacklist["roles"].remove(role.id)
            message += f"Removed {role.mention} from blacklist.\n"
        else:
            message += f"Role {role.mention} is not blacklisted.\n"
    save_data()
    await interaction.response.send_message(message, ephemeral=True)

@bot.tree.command(name="gblacklistlist", description="List all blacklisted members and roles. (Owner only)")
async def gblacklistlist(interaction: discord.Interaction):
    if not is_owner(interaction.user.id):
        await interaction.response.send_message("Only host can use /gblacklistlist.", ephemeral=True)
        return
    member_list = []
    for mem_id in blacklist["members"]:
        member = bot.get_user(mem_id) or await bot.fetch_user(mem_id)
        member_list.append(member.mention if member else str(mem_id))
    role_list = [f"<@&{role_id}>" for role_id in blacklist["roles"]]
    msg = (f"Blacklisted Members: {', '.join(member_list) if member_list else 'None'}\n"
           f"Blacklisted Roles: {', '.join(role_list) if role_list else 'None'}")
    await interaction.response.send_message(msg, ephemeral=True)

@bot.tree.command(name="bonusentries", description="Add bonus entries for a member or role. (Owner only)")
async def bonusentries(interaction: discord.Interaction, member: discord.Member = None, role: discord.Role = None, entries: int = 1):
    if not is_owner(interaction.user.id):
        await interaction.response.send_message("Only host can use /bonusentries.", ephemeral=True)
        return
    if member is None and role is None:
        await interaction.response.send_message("Specify a member or role.", ephemeral=True)
        return
    message = ""
    if member:
        key = f"member_{member.id}"
        bonus_entries[key] = bonus_entries.get(key, 0) + entries
        message += f"Added {entries} bonus entries for member {member.mention}.\n"
    if role:
        key = f"role_{role.id}"
        bonus_entries[key] = bonus_entries.get(key, 0) + entries
        message += f"Added {entries} bonus entries for role {role.mention}.\n"
    save_data()
    await interaction.response.send_message(message, ephemeral=True)

@bot.tree.command(name="bonusentriesremove", description="Remove bonus entries for a member or role. (Owner only)")
async def bonusentriesremove(interaction: discord.Interaction, member: discord.Member = None, role: discord.Role = None, entries: int = 1):
    """
    Modified to include an 'entries' parameter so you can remove a specific number of bonus entries.
    If the removal amount equals or exceeds the current bonus entries, the bonus entry is removed.
    """
    if not is_owner(interaction.user.id):
        await interaction.response.send_message("Only host can use /bonusentriesremove.", ephemeral=True)
        return
    if member is None and role is None:
        await interaction.response.send_message("Specify a member or role.", ephemeral=True)
        return
    message = ""
    if member:
        key = f"member_{member.id}"
        current = bonus_entries.get(key, 0)
        if current:
            if entries >= current:
                del bonus_entries[key]
                message += f"Removed all bonus entries for member {member.mention} (was {current}).\n"
            else:
                bonus_entries[key] = current - entries
                message += f"Removed {entries} bonus entries for member {member.mention}. Remaining: {bonus_entries[key]}.\n"
        else:
            message += f"No bonus entries for member {member.mention}.\n"
    if role:
        key = f"role_{role.id}"
        current = bonus_entries.get(key, 0)
        if current:
            if entries >= current:
                del bonus_entries[key]
                message += f"Removed all bonus entries for role {role.mention} (was {current}).\n"
            else:
                bonus_entries[key] = current - entries
                message += f"Removed {entries} bonus entries for role {role.mention}. Remaining: {bonus_entries[key]}.\n"
        else:
            message += f"No bonus entries for role {role.mention}.\n"
    save_data()
    await interaction.response.send_message(message, ephemeral=True)

@bot.tree.command(name="bonusentrieslist", description="List all bonus entries for members and roles. (Owner only)")
async def bonusentrieslist(interaction: discord.Interaction):
    if not is_owner(interaction.user.id):
        await interaction.response.send_message("Only host can use /bonusentrieslist.", ephemeral=True)
        return
    if not bonus_entries:
        await interaction.response.send_message("No bonus entries found.", ephemeral=True)
        return
    msg_lines = []
    for key, value in bonus_entries.items():
        if key.startswith("member_"):
            member_id = int(key.split("_")[1])
            member = bot.get_user(member_id) or await bot.fetch_user(member_id)
            msg_lines.append(f"Member {member.mention if member else member_id}: {value} bonus entries")
        elif key.startswith("role_"):
            role_id = int(key.split("_")[1])
            role = None
            for guild in bot.guilds:
                role = guild.get_role(role_id)
                if role:
                    break
            msg_lines.append(f"Role {role.mention if role else role_id}: {value} bonus entries")
        else:
            msg_lines.append(f"{key}: {value}")
    final_msg = "\n".join(msg_lines)
    await interaction.response.send_message(final_msg, ephemeral=True)

# ------------------------------
# Run the Bot
# ------------------------------
bot.run("TOKEN")
