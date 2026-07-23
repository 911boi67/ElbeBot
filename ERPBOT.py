import discord
from discord import app_commands
from discord.ext import commands
from datetime import timedelta
import json
import os
import asyncio
import asyncpg

TOKEN = os.getenv("TOKEN")
if not TOKEN:
    raise ValueError("Umgebungsvariable TOKEN ist nicht gesetzt!")

DATABASE_URL = os.getenv("DATABASE_PUBLIC_URL") or os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("Umgebungsvariable DATABASE_URL ist nicht gesetzt!")

RP_SETUP_CHANNEL = 1497987421424582857
RP_STATUS_CHANNEL = 1497669225513222164
RP_STAFF_ROLE = 1497664906298785792
RP_PING_ROLE = 1497884586992996502

SERVER_CODES = {1: "nregrnfe", 2: "m523ab1s"}

LOG_CHANNEL = 1497664768851447878

WARN_ROLE_1 = 1529802970475270174
WARN_ROLE_2 = 1529803196602781716
WARN_ROLE_3 = 1529803187844943872

async def get_warns(guild_id, user_id=None):
    async with bot.db_pool.acquire() as conn:
        if user_id:
            rows = await conn.fetch("SELECT reason, datum, von FROM warns WHERE guild_id = $1 AND user_id = $2 ORDER BY id", guild_id, user_id)
            return [{"grund": r["reason"], "datum": r["datum"], "von": r["von"]} for r in rows]
        rows = await conn.fetch("SELECT DISTINCT user_id FROM warns WHERE guild_id = $1", guild_id)
        result = {}
        for r in rows:
            warns = await conn.fetch("SELECT reason, datum, von FROM warns WHERE guild_id = $1 AND user_id = $2 ORDER BY id", guild_id, r["user_id"])
            result[r["user_id"]] = [{"grund": w["reason"], "datum": w["datum"], "von": w["von"]} for w in warns]
        return result

async def add_warn(guild_id, user_id, reason, datum, von):
    async with bot.db_pool.acquire() as conn:
        await conn.execute("INSERT INTO warns (guild_id, user_id, reason, datum, von) VALUES ($1, $2, $3, $4, $5)", guild_id, user_id, reason, datum, von)

async def remove_last_warn(guild_id, user_id):
    async with bot.db_pool.acquire() as conn:
        sub = await conn.fetchval("SELECT id FROM warns WHERE guild_id = $1 AND user_id = $2 ORDER BY id DESC LIMIT 1", guild_id, user_id)
        if sub:
            await conn.execute("DELETE FROM warns WHERE id = $1", sub)
        return sub is not None

async def warn_count(guild_id, user_id):
    async with bot.db_pool.acquire() as conn:
        return await conn.fetchval("SELECT COUNT(*) FROM warns WHERE guild_id = $1 AND user_id = $2", guild_id, user_id)

async def get_notizen(guild_id):
    async with bot.db_pool.acquire() as conn:
        rows = await conn.fetch("SELECT user_id, text, von, datum FROM notizen WHERE guild_id = $1 ORDER BY id", guild_id)
        result = {}
        for r in rows:
            uid = r["user_id"]
            if uid not in result:
                result[uid] = []
            result[uid].append({"text": r["text"], "von": r["von"], "datum": r["datum"]})
        return result

async def add_notiz(guild_id, user_id, text, von, datum):
    async with bot.db_pool.acquire() as conn:
        await conn.execute("INSERT INTO notizen (guild_id, user_id, text, von, datum) VALUES ($1, $2, $3, $4, $5)", guild_id, user_id, text, von, datum)

async def send_mod_dm(member, action, grund, dauer=None):
    try:
        embed = discord.Embed(title=f"⚡ Du wurdest {action}", color=discord.Color.red())
        embed.add_field(name="Grund", value=grund, inline=False)
        embed.add_field(name="Server", value=member.guild.name, inline=False)
        if dauer:
            embed.add_field(name="Dauer", value=dauer, inline=False)
        await member.send(embed=embed)
    except:
        pass

async def send_log(guild, command, moderator, target, details, farbe=discord.Color.red()):
    channel = guild.get_channel(LOG_CHANNEL)
    if not channel:
        return
    embed = discord.Embed(title=f"📋 Log – {command}", color=farbe)
    embed.add_field(name="Moderator", value=moderator.mention, inline=True)
    if target:
        embed.add_field(name="Ziel", value=target.mention if hasattr(target, 'mention') else target, inline=True)
    embed.add_field(name="Details", value=details, inline=False)
    embed.set_footer(text=discord.utils.utcnow().strftime("%d.%m.%Y %H:%M:%S"))
    await channel.send(embed=embed)

class GiveawayView(discord.ui.View):
    def __init__(self, robux, bis, host):
        super().__init__(timeout=None)
        self.robux = robux
        self.bis = bis
        self.host = host
        self.teilnehmer = []

    @discord.ui.button(label="🎉 Teilnehmen", style=discord.ButtonStyle.blurple, custom_id="giveaway_join")
    async def join_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id in self.teilnehmer:
            await interaction.response.send_message("Du nimmst bereits teil!", ephemeral=True)
            return
        self.teilnehmer.append(interaction.user.id)
        await interaction.response.send_message(f"✅ Du nimmst am Giveaway ({self.robux} Robux) teil!", ephemeral=True)

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

class RPView(discord.ui.View):
    def __init__(self, server):
        super().__init__(timeout=None)
        self.server = server

    @discord.ui.button(label="ServerStart", style=discord.ButtonStyle.green, custom_id="rp_start")
    async def start_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.get_role(RP_STAFF_ROLE):
            await interaction.response.send_message("Du hast keine Berechtigung dafür!", ephemeral=True)
            return
        channel = interaction.guild.get_channel(RP_STATUS_CHANNEL)
        if not channel:
            await interaction.response.send_message("Status-Channel nicht gefunden!", ephemeral=True)
            return
        label = f"SERVER {self.server} GEÖFFNET {'21+' if self.server == 1 else '13+'}"
        embed = discord.Embed(
            title=f"🟢 {label}",
            description=f"Der Server wurde erfolgreich von <@&{RP_STAFF_ROLE}> geöffnet.",
            color=discord.Color.green()
        )
        embed.add_field(name="🎮 Server-Code", value=f"`{SERVER_CODES[self.server]}`", inline=False)
        embed.add_field(name="🚀 Jetzt beitreten!", value="Komm gerne vorbei und hab Spaß mit uns!", inline=False)
        embed.set_footer(text="Server Status")
        await channel.send(f"<@&{RP_PING_ROLE}>", embed=embed)
        await interaction.response.send_message("✅ Server-Start wurde angekündigt!", ephemeral=True)

    @discord.ui.button(label="ServerInBearbeitung", style=discord.ButtonStyle.grey, custom_id="rp_wip")
    async def wip_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.get_role(RP_STAFF_ROLE):
            await interaction.response.send_message("Du hast keine Berechtigung dafür!", ephemeral=True)
            return
        channel = interaction.guild.get_channel(RP_STATUS_CHANNEL)
        if not channel:
            await interaction.response.send_message("Status-Channel nicht gefunden!", ephemeral=True)
            return
        embed = discord.Embed(
            title=f"🟡 SERVER {self.server} IN BEARBEITUNG",
            description=f"Der Server wird derzeit von <@&{RP_STAFF_ROLE}> vorbereitet und eingerichtet.",
            color=discord.Color.gold()
        )
        embed.add_field(name="🛠️ Status", value="Wird aktuell bearbeitet...", inline=False)
        embed.add_field(name="⏳ Bitte warten!", value="Der Server ist momentan noch nicht verfügbar. Sobald die Einrichtung abgeschlossen ist, wird der Server geöffnet und der Server-Code veröffentlicht.", inline=False)
        embed.set_footer(text="Server Status")
        await channel.send(f"<@&{RP_PING_ROLE}>", embed=embed)
        await interaction.response.send_message("✅ Server-Bearbeitung wurde angekündigt!", ephemeral=True)

    @discord.ui.button(label="ServerStop", style=discord.ButtonStyle.red, custom_id="rp_stop")
    async def stop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.get_role(RP_STAFF_ROLE):
            await interaction.response.send_message("Du hast keine Berechtigung dafür!", ephemeral=True)
            return
        channel = interaction.guild.get_channel(RP_STATUS_CHANNEL)
        if not channel:
            await interaction.response.send_message("Status-Channel nicht gefunden!", ephemeral=True)
            return
        embed = discord.Embed(
            title=f"🔴 SERVER {self.server} GESCHLOSSEN",
            description=f"Der Server wurde von <@&{RP_STAFF_ROLE}> geschlossen.",
            color=discord.Color.red()
        )
        embed.add_field(name="🔒 Status", value="Server momentan nicht verfügbar", inline=False)
        embed.add_field(name="⚠️ Zugriff geschlossen", value="Der Server ist aktuell geschlossen und kann derzeit nicht betreten werden.\nSobald der Server wieder geöffnet wird, informieren wir euch.", inline=False)
        embed.set_footer(text="Server Status")
        await channel.send(f"<@&{RP_PING_ROLE}>", embed=embed)
        await interaction.response.send_message("✅ Server-Stopp wurde angekündigt!", ephemeral=True)

BOT_STAFF_ROLE = 1497932354524676207

class Bot(discord.Client):
    def __init__(self):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.db_pool = None

    async def _connect_db(self):
        use_ssl = "proxy.rlwy.net" in DATABASE_URL
        db_pool = None
        for attempt in range(3):
            try:
                db_pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5, ssl=use_ssl, timeout=60)
                break
            except Exception as e:
                if attempt < 2:
                    print(f"DB connection failed (attempt {attempt+1}/3): {e}")
                    await asyncio.sleep(10)
                else:
                    print(f"DB connection failed after 3 attempts: {e}")
                    return
        self.db_pool = db_pool
        async with self.db_pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS warns (
                    id SERIAL PRIMARY KEY,
                    guild_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    reason TEXT DEFAULT '',
                    datum TEXT DEFAULT '',
                    von TEXT DEFAULT ''
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS notizen (
                    id SERIAL PRIMARY KEY,
                    guild_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    text TEXT DEFAULT '',
                    von TEXT DEFAULT '',
                    datum TEXT DEFAULT ''
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS ticket_counter (
                    id INT PRIMARY KEY DEFAULT 1,
                    counter INT DEFAULT 0
                )
            """)
            await conn.execute("""
                INSERT INTO ticket_counter (id, counter) VALUES (1, 0) ON CONFLICT (id) DO NOTHING
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS tickets (
                    channel_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    number INT NOT NULL,
                    staff_id TEXT,
                    open BOOLEAN DEFAULT TRUE
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS shifts (
                    guild_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    total_duty INT DEFAULT 0,
                    total_break INT DEFAULT 0,
                    shift_start DOUBLE PRECISION,
                    break_start DOUBLE PRECISION,
                    PRIMARY KEY (guild_id, user_id)
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS saved_messages (
                    id SERIAL PRIMARY KEY,
                    guild_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    titel TEXT DEFAULT '',
                    content TEXT DEFAULT '',
                    created_by TEXT DEFAULT '',
                    UNIQUE(guild_id, name)
                )
            """)
            rows = await conn.fetch("SELECT channel_id FROM tickets WHERE open = TRUE")
            for row in rows:
                self.add_view(TicketActionView(int(row["channel_id"])))

    async def setup_hook(self):
        asyncio.create_task(self._connect_db())
        self.add_view(RPView(1))
        self.add_view(RPView(2))
        self.add_view(TicketSetupView())
        self.add_view(AutoRoleView())
        self.add_view(ShiftStartView())
        await self.tree.sync()

    async def close(self):
        if self.db_pool:
            await self.db_pool.close()
        await super().close()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.type == discord.InteractionType.application_command and interaction.guild:
            role = interaction.guild.get_role(BOT_STAFF_ROLE)
            if role and role not in interaction.user.roles:
                await interaction.response.send_message("Du hast keine Berechtigung den Bot zu nutzen!", ephemeral=True)
                return False
        return True

bot = Bot()

@bot.tree.command(name="kick", description="Kickt einen Member vom Server")
@app_commands.describe(member="Der Member, der gekickt werden soll", reason="Grund für den Kick")
async def kick(interaction: discord.Interaction, member: discord.Member, reason: str = "Kein Grund angegeben"):
    await interaction.response.defer(ephemeral=True)

    if not interaction.guild:
        await interaction.followup.send("Das geht nur auf einem Server!", ephemeral=True)
        return

    if not interaction.user.guild_permissions.kick_members:
        await interaction.followup.send("Du hast keine Berechtigung Member zu kicken!", ephemeral=True)
        return

    if not interaction.guild.me.guild_permissions.kick_members:
        await interaction.followup.send("Ich habe keine Berechtigung Member zu kicken!", ephemeral=True)
        return

    if member.top_role >= interaction.user.top_role and interaction.user != interaction.guild.owner:
        await interaction.followup.send("Du kannst diesen Member nicht kicken – seine Rolle ist höher/gleich deiner!", ephemeral=True)
        return

    if member == interaction.guild.owner:
        await interaction.followup.send("Du kannst den Server-Owner nicht kicken!", ephemeral=True)
        return

    try:
        await member.kick(reason=reason)
        await send_mod_dm(member, "gekickt", reason)
        await send_log(interaction.guild, "Kick", interaction.user, member, f"Grund: {reason}")
        await interaction.followup.send(f"**{member}** wurde gekickt.\nGrund: {reason}", ephemeral=True)
    except discord.Forbidden:
        await interaction.followup.send("Ich habe keine Berechtigung diesen Member zu kicken!", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"Fehler beim Kicken: {e}", ephemeral=True)

@bot.tree.command(name="ban", description="Bannt einen Member vom Server")
@app_commands.describe(member="Der Member, der gebannt werden soll", reason="Grund für den Ban")
async def ban(interaction: discord.Interaction, member: discord.Member, reason: str = "Kein Grund angegeben"):
    await interaction.response.defer(ephemeral=True)

    if not interaction.guild:
        await interaction.followup.send("Das geht nur auf einem Server!", ephemeral=True)
        return

    if not interaction.user.guild_permissions.ban_members:
        await interaction.followup.send("Du hast keine Berechtigung Member zu bannen!", ephemeral=True)
        return

    if not interaction.guild.me.guild_permissions.ban_members:
        await interaction.followup.send("Ich habe keine Berechtigung Member zu bannen!", ephemeral=True)
        return

    if member.top_role >= interaction.user.top_role and interaction.user != interaction.guild.owner:
        await interaction.followup.send("Du kannst diesen Member nicht bannen – seine Rolle ist höher/gleich deiner!", ephemeral=True)
        return

    if member == interaction.guild.owner:
        await interaction.followup.send("Du kannst den Server-Owner nicht bannen!", ephemeral=True)
        return

    try:
        await member.ban(reason=reason)
        await send_mod_dm(member, "gebannt", reason)
        await send_log(interaction.guild, "Ban", interaction.user, member, f"Grund: {reason}")
        await interaction.followup.send(f"**{member}** wurde gebannt.\nGrund: {reason}", ephemeral=True)
    except discord.Forbidden:
        await interaction.followup.send("Ich habe keine Berechtigung diesen Member zu bannen!", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"Fehler beim Bannen: {e}", ephemeral=True)

@bot.tree.command(name="timeout", description="Timeout einen Member (bis zu 28 Tage)")
@app_commands.describe(member="Der Member, der getimeoutet werden soll", dauer="Dauer, z.B. 10m, 1h, 2d", reason="Grund für den Timeout")
async def timeout(interaction: discord.Interaction, member: discord.Member, dauer: str, reason: str = "Kein Grund angegeben"):
    await interaction.response.defer(ephemeral=True)

    if not interaction.guild:
        await interaction.followup.send("Das geht nur auf einem Server!", ephemeral=True)
        return

    if not interaction.user.guild_permissions.moderate_members:
        await interaction.followup.send("Du hast keine Berechtigung Member zu timeouten!", ephemeral=True)
        return

    if not interaction.guild.me.guild_permissions.moderate_members:
        await interaction.followup.send("Ich habe keine Berechtigung Member zu timeouten!", ephemeral=True)
        return

    if member.top_role >= interaction.user.top_role and interaction.user != interaction.guild.owner:
        await interaction.followup.send("Du kannst diesen Member nicht timeouten – seine Rolle ist höher/gleich deiner!", ephemeral=True)
        return

    if member == interaction.guild.owner:
        await interaction.followup.send("Du kannst den Server-Owner nicht timeouten!", ephemeral=True)
        return

    seconds = 0
    try:
        if dauer.endswith("m"):
            seconds = int(dauer[:-1]) * 60
        elif dauer.endswith("h"):
            seconds = int(dauer[:-1]) * 3600
        elif dauer.endswith("d"):
            seconds = int(dauer[:-1]) * 86400
        elif dauer.endswith("s"):
            seconds = int(dauer[:-1])
        else:
            seconds = int(dauer)
    except ValueError:
        await interaction.followup.send("Ungültiges Format! Nutze z.B. `10m`, `1h`, `2d`", ephemeral=True)
        return

    if seconds < 0:
        await interaction.followup.send("Die Dauer kann nicht negativ sein!", ephemeral=True)
        return
    if seconds > 2419200:
        await interaction.followup.send("Timeout kann maximal 28 Tage betragen!", ephemeral=True)
        return

    try:
        await member.timeout(discord.utils.utcnow() + timedelta(seconds=seconds), reason=reason)
        await send_mod_dm(member, "getimeoutet", reason, dauer)
        await send_log(interaction.guild, "Timeout", interaction.user, member, f"Dauer: {dauer}\nGrund: {reason}")
        await interaction.followup.send(f"**{member}** wurde für `{dauer}` getimeoutet.\nGrund: {reason}", ephemeral=True)
    except discord.Forbidden:
        await interaction.followup.send("Ich habe keine Berechtigung diesen Member zu timeouten!", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"Fehler beim Timeout: {e}", ephemeral=True)

@bot.tree.command(name="sync", description="Synct alle Slash-Commands (nur für Bot-Admin)")
async def sync(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    if not interaction.user.guild_permissions.administrator:
        await interaction.followup.send("Du brauchst Administrator-Rechte!", ephemeral=True)
        return
    await bot.tree.sync()
    await interaction.followup.send("✅ Slash-Commands wurden gesynct!", ephemeral=True)

@bot.tree.command(name="rp", description="RP-Setup: Sendet die Buttons in den Setup-Channel")
@app_commands.describe(server="Welcher Server? (1 = 21+, 2 = 13+)")
@app_commands.choices(server=[
    app_commands.Choice(name="Server 1 (21+)", value=1),
    app_commands.Choice(name="Server 2 (13+)", value=2),
])
async def rp_setup(interaction: discord.Interaction, server: int):
    if not interaction.user.get_role(RP_STAFF_ROLE):
        await interaction.response.send_message("Du hast keine Berechtigung dafür!", ephemeral=True)
        return

    channel = interaction.guild.get_channel(RP_SETUP_CHANNEL)
    if not channel:
        await interaction.response.send_message("Setup-Channel nicht gefunden!", ephemeral=True)
        return

    label = f"Server {server} ({'21+' if server == 1 else '13+'})"
    embed = discord.Embed(
        title=f"🎮 RP {label} Steuerung",
        description=f"Wähle eine Aktion für {label}:",
        color=discord.Color.blurple()
    )
    await channel.send(embed=embed, view=RPView(server))
    await interaction.response.send_message(f"✅ Steuerung für {label} wurde in <#{RP_SETUP_CHANNEL}> gesendet!", ephemeral=True)

@bot.tree.command(name="clear", description="Löscht Nachrichten in diesem Channel")
@app_commands.describe(anzahl="Anzahl der Nachrichten, die gelöscht werden sollen (max 100)")
async def clear(interaction: discord.Interaction, anzahl: int):
    await interaction.response.defer(ephemeral=True)

    if not interaction.user.guild_permissions.manage_messages:
        await interaction.followup.send("Du brauchst die Berechtigung Nachrichten zu verwalten!", ephemeral=True)
        return
    if anzahl < 1 or anzahl > 100:
        await interaction.followup.send("Bitte eine Zahl zwischen 1 und 100 angeben!", ephemeral=True)
        return
    try:
        deleted = await interaction.channel.purge(limit=anzahl)
        await send_log(interaction.guild, "Clear", interaction.user, None, f"Channel: {interaction.channel.mention}\nAnzahl: {len(deleted)}", discord.Color.orange())
        await interaction.followup.send(f"🗑️ {len(deleted)} Nachrichten gelöscht.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"Fehler beim Löschen: {e}", ephemeral=True)

WARN_ROLES_MAP = {1: WARN_ROLE_1, 2: WARN_ROLE_2, 3: WARN_ROLE_3}

@bot.tree.command(name="warn", description="Verwarnt einen Member (automatische Aktion je nach Warn-Stufe)")
@app_commands.describe(member="Der Member, der verwarnt werden soll", grund="Grund für die Verwarnung")
async def warn(interaction: discord.Interaction, member: discord.Member, grund: str = "Kein Grund angegeben"):
    await interaction.response.defer(ephemeral=True)

    if not interaction.user.guild_permissions.kick_members:
        await interaction.followup.send("Du hast keine Berechtigung Member zu verwarnen!", ephemeral=True)
        return
    if not interaction.guild.me.guild_permissions.moderate_members:
        await interaction.followup.send("Ich habe keine Berechtigung für Timeouts!", ephemeral=True)
        return
    if member == interaction.guild.owner:
        await interaction.followup.send("Du kannst den Server-Owner nicht verwarnen!", ephemeral=True)
        return
    if member.top_role >= interaction.user.top_role and interaction.user != interaction.guild.owner:
        await interaction.followup.send("Du kannst diesen Member nicht verwarnen – seine Rolle ist höher/gleich deiner!", ephemeral=True)
        return

    guild_id = str(interaction.guild.id)
    user_id = str(member.id)

    warn_num = await warn_count(guild_id, user_id) + 1

    await add_warn(guild_id, user_id, grund, str(discord.utils.utcnow()), str(interaction.user))

    role_id = WARN_ROLES_MAP.get(warn_num)
    if role_id:
        role = interaction.guild.get_role(role_id)
        if role:
            for old_rid in WARN_ROLES_MAP.values():
                old_role = interaction.guild.get_role(old_rid)
                if old_role and old_role in member.roles:
                    await member.remove_roles(old_role)
            await member.add_roles(role)

    if warn_num >= 3:
        try:
            await member.kick(reason=f"Warn {warn_num}: {grund}")
            await send_mod_dm(member, "gekickt (Warn 3/3)", grund)
            await send_log(interaction.guild, "Warn 3/3 – Kick", interaction.user, member, f"Grund: {grund}")
            await interaction.followup.send(f"**{member}** wurde verwarnet (Warn {warn_num}/3) und gekickt.\nGrund: {grund}", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"Fehler beim Kicken: {e}", ephemeral=True)
    elif warn_num == 2:
        try:
            await member.timeout(discord.utils.utcnow() + timedelta(minutes=30), reason=f"Warn 2: {grund}")
            await send_mod_dm(member, "verwarnt (Warn 2/3)", grund, "30 Minuten")
            await send_log(interaction.guild, "Warn 2/3 – Timeout", interaction.user, member, f"Dauer: 30 Min\nGrund: {grund}")
            await interaction.followup.send(f"**{member}** wurde verwarnet (Warn {warn_num}/3) und für 30 Min getimeoutet.\nGrund: {grund}", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"Fehler beim Timeout: {e}", ephemeral=True)
    elif warn_num == 1:
        try:
            await member.timeout(discord.utils.utcnow() + timedelta(minutes=5), reason=f"Warn 1: {grund}")
            await send_mod_dm(member, "verwarnt (Warn 1/3)", grund, "5 Minuten")
            await send_log(interaction.guild, "Warn 1/3 – Timeout", interaction.user, member, f"Dauer: 5 Min\nGrund: {grund}")
            await interaction.followup.send(f"**{member}** wurde verwarnet (Warn {warn_num}/3) und für 5 Min getimeoutet.\nGrund: {grund}", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"Fehler beim Timeout: {e}", ephemeral=True)

    if member.get_role(WARN_ROLE_3):
        try:
            await member.kick(reason="Auto-Kick wegen Warn 3 Rolle")
        except:
            pass

@bot.tree.command(name="unwarn", description="Entfernt die letzte Verwarnung eines Spielers")
@app_commands.describe(member="Der Member, dessen letzte Warn entfernt werden soll")
async def unwarn(interaction: discord.Interaction, member: discord.Member):
    await interaction.response.defer(ephemeral=True)

    if not interaction.user.guild_permissions.kick_members:
        await interaction.followup.send("Du hast keine Berechtigung dafür!", ephemeral=True)
        return

    guild_id = str(interaction.guild.id)
    user_id = str(member.id)

    current = await warn_count(guild_id, user_id)
    if current == 0:
        await interaction.followup.send("Dieser Spieler hat keine Verwarnungen.", ephemeral=True)
        return

    removed = await remove_last_warn(guild_id, user_id)
    if not removed:
        await interaction.followup.send("Fehler beim Entfernen der Warn.", ephemeral=True)
        return

    remaining = await warn_count(guild_id, user_id)
    if remaining == 0:
        for rid in WARN_ROLES_MAP.values():
            role = interaction.guild.get_role(rid)
            if role and role in member.roles:
                await member.remove_roles(role)
    else:
        old_roles = [interaction.guild.get_role(rid) for rid in WARN_ROLES_MAP.values()]
        for r in old_roles:
            if r and r in member.roles:
                await member.remove_roles(r)
        new_role = interaction.guild.get_role(WARN_ROLES_MAP[remaining])
        if new_role:
            await member.add_roles(new_role)

    await send_log(interaction.guild, "Unwarn", interaction.user, member, f"Verbleibende Warns: {remaining}", discord.Color.green())
    await interaction.followup.send(f"✅ Letzte Warn von {member.mention} entfernt.\nVerbleibende Warns: {remaining}", ephemeral=True)

class WarnsPaginator(discord.ui.View):
    def __init__(self, items, interaction):
        super().__init__(timeout=120)
        self.items = items
        self.interaction = interaction
        self.page = 0
        self.per_page = 5
        self.max_page = (len(items) - 1) // self.per_page

    def _build_embed(self):
        start = self.page * self.per_page
        end = start + self.per_page
        page_items = self.items[start:end]

        embed = discord.Embed(title="📋 Verwarnungen", color=discord.Color.orange())
        for user_id, user_warns in page_items:
            member = self.interaction.guild.get_member(int(user_id))
            name = member.mention if member else f"<@{user_id}> (nicht auf Server)"
            warn_count = len(user_warns)
            latest = user_warns[-1]
            von_name = latest['von'].split('#')[0] if '#' in latest['von'] else latest['von']
            embed.add_field(name=f"{name} – Warns: {warn_count}/3", value=f"Letzter Grund: {latest['grund']}\nDatum: {latest['datum']}\nVon: {von_name}", inline=False)

        embed.set_footer(text=f"Seite {self.page + 1}/{self.max_page + 1} • {len(self.items)} Spieler")
        return embed

    async def _update(self):
        self.prev_button.disabled = self.page == 0
        self.next_button.disabled = self.page >= self.max_page
        await self.interaction.edit_original_response(embed=self._build_embed(), view=self)

    @discord.ui.button(label="◀", style=discord.ButtonStyle.grey, custom_id="warns_prev")
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page > 0:
            self.page -= 1
        await self._update()
        await interaction.response.defer()

    @discord.ui.button(label="▶", style=discord.ButtonStyle.grey, custom_id="warns_next")
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page < self.max_page:
            self.page += 1
        await self._update()
        await interaction.response.defer()

    @discord.ui.button(label="Schließen", style=discord.ButtonStyle.red, custom_id="warns_close")
    async def close_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="📍 Geschlossen.", embed=None, view=None)
        self.stop()

@bot.tree.command(name="warns", description="Zeigt alle verwarneten Spieler mit Pagination an")
async def warns_list(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    if not interaction.user.guild_permissions.kick_members:
        await interaction.followup.send("Du hast keine Berechtigung dafür!", ephemeral=True)
        return

    guild_id = str(interaction.guild.id)
    guild_warns = await get_warns(guild_id)

    if not guild_warns:
        await interaction.followup.send("Es gibt keine Verwarnungen auf diesem Server.", ephemeral=True)
        return

    items = sorted(guild_warns.items(), key=lambda x: len(x[1]), reverse=True)
    view = WarnsPaginator(items, interaction)
    await interaction.followup.send(embed=view._build_embed(), view=view)

@bot.tree.command(name="serverinfo", description="Zeigt Informationen über den Server an")
async def serverinfo(interaction: discord.Interaction):
    guild = interaction.guild
    embed = discord.Embed(title=guild.name, color=discord.Color.blurple())
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    embed.add_field(name="👑 Owner", value=guild.owner.mention, inline=True)
    embed.add_field(name="📅 Erstellt", value=discord.utils.format_dt(guild.created_at, style="D"), inline=True)
    embed.add_field(name="👥 Members", value=guild.member_count, inline=True)
    embed.add_field(name="💬 Channel", value=len(guild.channels), inline=True)
    embed.add_field(name="🎭 Rollen", value=len(guild.roles), inline=True)
    embed.add_field(name="🌍 Boosts", value=guild.premium_subscription_count, inline=True)
    embed.set_footer(text=f"ID: {guild.id}")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="poll", description="Erstellt eine Umfrage")
@app_commands.describe(frage="Die Umfrage-Frage", option1="Option 1", option2="Option 2", option3="Option 3 (optional)", option4="Option 4 (optional)")
async def poll(interaction: discord.Interaction, frage: str, option1: str, option2: str, option3: str = None, option4: str = None):
    if not interaction.user.guild_permissions.manage_messages:
        await interaction.response.send_message("Du brauchst die Berechtigung Nachrichten zu verwalten!", ephemeral=True)
        return

    options = [option1, option2]
    if option3:
        options.append(option3)
    if option4:
        options.append(option4)

    emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣"]
    desc = "\n\n".join([f"{emojis[i]} {opt}" for i, opt in enumerate(options)])
    embed = discord.Embed(title=f"📊 {frage}", description=desc, color=discord.Color.blurple())
    embed.set_footer(text=f"Von {interaction.user}")
    msg = await interaction.channel.send(embed=embed)
    await interaction.response.send_message("✅ Umfrage erstellt!", ephemeral=True)

    for i in range(len(options)):
        await msg.add_reaction(emojis[i])

@bot.tree.command(name="teamliste", description="Zeigt alle Teammitglieder an")
async def teamliste(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    role1 = interaction.guild.get_role(1497932354524676207)
    role2 = interaction.guild.get_role(1497664906298785792)
    if not role1 and not role2:
        await interaction.followup.send("Rollen nicht gefunden!", ephemeral=True)
        return

    members = []
    for m in interaction.guild.members:
        if (role1 and role1 in m.roles) or (role2 and role2 in m.roles):
            members.append(m)

    if not members:
        await interaction.followup.send("Keine Teammitglieder gefunden.", ephemeral=True)
        return

    embed = discord.Embed(title="👥 Teamliste", color=discord.Color.blurple())
    text = ""
    for m in members:
        roles_mention = []
        if role1 and role1 in m.roles:
            roles_mention.append(role1.mention)
        if role2 and role2 in m.roles:
            roles_mention.append(role2.mention)
        text += f"{m.mention} – {', '.join(roles_mention)}\n"

    embed.description = text
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="giveaway", description="Erstellt ein Giveaway")
@app_commands.describe(robux="Anzahl Robux", bis="Datum z.B. 24.07.2026")
async def giveaway(interaction: discord.Interaction, robux: int, bis: str):
    await interaction.response.defer(ephemeral=True)

    if not interaction.user.guild_permissions.administrator:
        await interaction.followup.send("Du brauchst Administrator-Rechte!", ephemeral=True)
        return

    channel = interaction.guild.get_channel(1497886239314149548)
    if not channel:
        await interaction.followup.send("Giveaway-Channel nicht gefunden!", ephemeral=True)
        return

    embed = discord.Embed(
        title="🎉 Giveaway",
        description=f"**{robux} Robux**",
        color=discord.Color.gold()
    )
    embed.add_field(name="📅 Endet", value=bis, inline=True)
    embed.add_field(name="👤 Veranstalter", value=interaction.user.mention, inline=True)
    embed.set_footer(text="Klicke auf Teilnehmen!")
    view = GiveawayView(robux, bis, interaction.user)
    await channel.send(embed=embed, view=view)
    await interaction.followup.send(f"✅ Giveaway in {channel.mention} erstellt!", ephemeral=True)

@bot.tree.command(name="notiz", description="Fügt einem Spieler eine Notiz hinzu (nur für Admins)")
@app_commands.describe(member="Der Spieler", text="Die Notiz")
async def notiz(interaction: discord.Interaction, member: discord.Member, text: str):
    await interaction.response.defer(ephemeral=True)
    if not interaction.user.guild_permissions.administrator:
        await interaction.followup.send("Du brauchst Administrator-Rechte!", ephemeral=True)
        return

    guild_id = str(interaction.guild.id)
    user_id = str(member.id)
    await add_notiz(guild_id, user_id, text, str(interaction.user), str(discord.utils.utcnow()))
    await interaction.followup.send(f"✅ Notiz für {member.mention} hinzugefügt.", ephemeral=True)

@bot.tree.command(name="notizen", description="Zeigt alle Spieler mit Notizen an")
async def notizen_list(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    if not interaction.user.guild_permissions.administrator:
        await interaction.followup.send("Du brauchst Administrator-Rechte!", ephemeral=True)
        return

    guild_id = str(interaction.guild.id)
    guild_notizen = await get_notizen(guild_id)

    if not guild_notizen:
        await interaction.followup.send("Keine Notizen vorhanden.", ephemeral=True)
        return

    embed = discord.Embed(title="📝 Spieler-Notizen", color=discord.Color.dark_grey())
    for user_id, notes in guild_notizen.items():
        member = interaction.guild.get_member(int(user_id))
        name = member.mention if member else f"<@{user_id}> (nicht auf Server)"
        last_note = notes[-1]["text"]
        embed.add_field(name=name, value=f"Letzte Notiz: {last_note}\n({len(notes)} Notiz/en)", inline=False)

    await interaction.followup.send(embed=embed, ephemeral=True)

@bot.tree.command(name="announce", description="Sendet eine Ankündigung als Embed")
@app_commands.describe(channel="Der Channel für die Ankündigung", titel="Titel der Ankündigung", nachricht="Die Nachricht")
async def announce(interaction: discord.Interaction, channel: discord.TextChannel, titel: str, nachricht: str):
    await interaction.response.defer(ephemeral=True)
    if not interaction.user.guild_permissions.administrator:
        await interaction.followup.send("Du brauchst Administrator-Rechte!", ephemeral=True)
        return

    embed = discord.Embed(title=titel, description=nachricht, color=discord.Color.blue())
    embed.set_footer(text=f"Ankündigung von {interaction.user}")
    await channel.send(embed=embed)
    await interaction.followup.send(f"✅ Ankündigung in {channel.mention} gesendet!", ephemeral=True)
    await send_log(interaction.guild, "Announce", interaction.user, channel, f"Titel: {titel}")

@bot.tree.command(name="help", description="Zeigt alle Commands an")
async def help_command(interaction: discord.Interaction):
    embed = discord.Embed(title="📚 Command-Liste", color=discord.Color.blurple())

    embed.add_field(name="🛡️ Moderation", value=(
        "`/kick <member> [grund]` – Kickt einen Member\n"
        "`/ban <member> [grund]` – Bannt einen Member\n"
        "`/timeout <member> <dauer> [grund]` – Timeout (z.B. 10m, 1h, 2d)\n"
        "`/warn <member> [grund]` – Verwarnung (1=5min, 2=30min, 3=Kick)\n"
        "`/unwarn <member>` – Letzte Verwarnung entfernen\n"
        "`/warns` – Alle Verwarnungen anzeigen\n"
        "`/clear <anzahl>` – Nachrichten löschen (max 100)"
    ), inline=False)

    embed.add_field(name="📋 Team", value=(
        "`/teamliste` – Alle Teammitglieder anzeigen\n"
        "`/notiz <member> <text>` – Notiz hinzufügen\n"
        "`/notizen` – Alle Notizen anzeigen\n"
        "`/sync` – Slash-Commands synct\n"
        "`/announce <channel> <titel> <text>` – Ankündigung senden"
    ), inline=False)

    embed.add_field(name="🎮 Server", value=(
        "`/rp <server>` – RP-Steuerung (Buttons)\n"
        "`/serverinfo` – Server-Informationen\n"
        "`/poll <frage> <opt1> <opt2> [opt3] [opt4]` – Umfrage\n"
        "`/giveaway <robux> <bis>` – Giveaway erstellen"
    ), inline=False)

    embed.add_field(name="🎟️ Ticket", value=(
        "`/ticket setup` – Ticket-System einrichten"
    ), inline=False)

    embed.add_field(name="📢 Aktivität", value=(
        "`/activity` – Aktivitäts-Check senden"
    ), inline=False)

    embed.add_field(name="⚙️ System", value=(
        "`/autorole setup` – Altersauswahl-Buttons senden\n"
        "`/rules <typ>` – Regeln senden (discord/ingame)\n"
        "`/shiftmanage` – Shift starten/stoppen\n"
        "`/resetduty <member>` – Shift-Daten eines Members löschen\n"
        "`/resetall` – Alle Shift-Daten löschen"
    ), inline=False)

    embed.set_footer(text=f"{interaction.guild.name} • ERPBOT")

    await interaction.response.send_message(embed=embed, ephemeral=True)

# ─── Ticket System ───────────────────────────────────────────────

TICKET_SETUP_CHANNEL = 1497662554493681774
TICKET_CATEGORY = 1529823422694166588
TICKET_LOG_CHANNEL = 1529824134044057660
TICKET_SUPPORT_ROLES = [1497932354524676207, 1497861979262681209, 1497664906298785792]
async def get_ticket_counter():
    async with bot.db_pool.acquire() as conn:
        val = await conn.fetchval("SELECT counter FROM ticket_counter WHERE id = 1")
        return val or 0

async def increment_ticket_counter():
    async with bot.db_pool.acquire() as conn:
        val = await conn.fetchval("UPDATE ticket_counter SET counter = counter + 1 WHERE id = 1 RETURNING counter")
        return val

async def create_ticket(channel_id, user_id, number):
    async with bot.db_pool.acquire() as conn:
        await conn.execute("INSERT INTO tickets (channel_id, user_id, number) VALUES ($1, $2, $3) ON CONFLICT (channel_id) DO NOTHING", channel_id, user_id, number)

async def get_ticket(channel_id):
    async with bot.db_pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM tickets WHERE channel_id = $1", channel_id)

async def update_ticket_staff(channel_id, staff_id):
    async with bot.db_pool.acquire() as conn:
        await conn.execute("UPDATE tickets SET staff_id = $1 WHERE channel_id = $2", staff_id, channel_id)

async def close_ticket(channel_id):
    async with bot.db_pool.acquire() as conn:
        await conn.execute("UPDATE tickets SET open = FALSE WHERE channel_id = $1", channel_id)

async def delete_ticket(channel_id):
    async with bot.db_pool.acquire() as conn:
        await conn.execute("DELETE FROM tickets WHERE channel_id = $1", channel_id)

class TicketSetupView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Ticket erstellen", emoji="🎫", style=discord.ButtonStyle.blurple, custom_id="ticket_create")
    async def create_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.guild:
            return

        category = interaction.guild.get_channel(TICKET_CATEGORY)
        if not category or not isinstance(category, discord.CategoryChannel):
            await interaction.response.send_message("Ticket-Kategorie nicht gefunden!", ephemeral=True)
            return

        counter = await increment_ticket_counter()
        ticket_num = f"{counter:03d}"
        channel_name = f"{interaction.user.name}-{ticket_num}".replace(" ", "-").lower()[:32]

        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
        }
        for role_id in TICKET_SUPPORT_ROLES:
            role = interaction.guild.get_role(role_id)
            if role:
                overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)

        try:
            channel = await category.create_text_channel(name=channel_name, overwrites=overwrites)
        except Exception as e:
            await interaction.response.send_message(f"Fehler beim Erstellen des Ticket-Channels: {e}", ephemeral=True)
            return

        await create_ticket(str(channel.id), str(interaction.user.id), counter)

        embed = discord.Embed(
            title="🎫 Support-Ticket",
            description=f"Willkommen im Support-Ticket von {interaction.user.mention}.\nEin Supporter wird sich in Kürze um dein Anliegen kümmern.",
            color=discord.Color.blurple()
        )
        await channel.send(embed=embed, view=TicketActionView(channel.id))
        await interaction.response.send_message(f"✅ Ticket erstellt: {channel.mention}", ephemeral=True)

        log_channel = interaction.guild.get_channel(TICKET_LOG_CHANNEL)
        if log_channel:
            role_pings = " ".join(f"<@&{rid}>" for rid in TICKET_SUPPORT_ROLES)
            log_embed = discord.Embed(
                title="📩 Neues Ticket",
                description=f"**User:** {interaction.user.mention}\n**Ticket:** {channel.mention}",
                color=discord.Color.green()
            )
            await log_channel.send(content=role_pings, embed=log_embed)

class CloseTicketModal(discord.ui.Modal, title="Ticket schließen"):
    grund = discord.ui.TextInput(label="Grund für die Schließung", style=discord.TextStyle.paragraph, placeholder="Bitte gib einen Grund an...", required=True, max_length=500)

    def __init__(self, channel_id):
        super().__init__()
        self.channel_id = channel_id

    async def on_submit(self, interaction: discord.Interaction):
        ticket = await get_ticket(str(self.channel_id))
        if not ticket:
            await interaction.response.send_message("Ticket nicht gefunden!", ephemeral=True)
            return

        await close_ticket(str(self.channel_id))

        grund = self.grund.value
        user = interaction.guild.get_member(int(ticket["user_id"]))
        staff = interaction.guild.get_member(int(ticket["staff_id"])) if ticket["staff_id"] else None

        embed = discord.Embed(
            title="🔒 Ticket geschlossen",
            description=f"Ticket von {user.mention if user else 'Unbekannt'} wurde geschlossen.",
            color=discord.Color.red()
        )
        embed.add_field(name="Geschlossen von", value=interaction.user.mention, inline=True)
        embed.add_field(name="Grund", value=grund, inline=False)
        await interaction.response.send_message(embed=embed)

        await interaction.channel.edit(overwrites={
            interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False)
        })
        await interaction.channel.send("🔒 Ticket wird in 5 Sekunden gelöscht...")
        await asyncio.sleep(5)
        try:
            await interaction.channel.delete(reason=f"Ticket geschlossen: {grund}")
        except:
            pass

        log_channel = interaction.guild.get_channel(TICKET_LOG_CHANNEL)
        if log_channel:
            log_embed = discord.Embed(
                title="🔒 Ticket geschlossen",
                description=f"**User:** {user.mention if user else 'Unbekannt'}\n**Geschlossen von:** {interaction.user.mention}\n**Grund:** {grund}",
                color=discord.Color.red()
            )
            await log_channel.send(embed=log_embed)

# Unclaimed ticket view: "Übernehmen" + "Schließen mit Grund"
class TicketActionView(discord.ui.View):
    def __init__(self, channel_id):
        super().__init__(timeout=None)
        self.channel_id = channel_id

    async def _can_close(self, interaction, ticket):
        if interaction.user.id == int(ticket["user_id"]):
            return True
        if any(role.id in TICKET_SUPPORT_ROLES for role in interaction.user.roles):
            return True
        return False

    @discord.ui.button(label="Übernehmen", style=discord.ButtonStyle.green, custom_id="ticket_claim")
    async def claim_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        ticket = await get_ticket(str(self.channel_id))
        if not ticket:
            await interaction.response.send_message("Ticket nicht gefunden!", ephemeral=True)
            return

        if not any(role.id in TICKET_SUPPORT_ROLES for role in interaction.user.roles):
            await interaction.response.send_message("Nur Support-Mitarbeiter können Tickets übernehmen!", ephemeral=True)
            return
        if ticket["staff_id"]:
            await interaction.response.send_message("Dieses Ticket wird bereits bearbeitet!", ephemeral=True)
            return

        await update_ticket_staff(str(self.channel_id), str(interaction.user.id))

        embed = discord.Embed(
            title="🎫 Support-Ticket",
            description=f"Willkommen im Support-Ticket von <@{ticket['user_id']}>.\nDieses Ticket wird jetzt von {interaction.user.mention} bearbeitet.",
            color=discord.Color.green()
        )
        await interaction.response.edit_message(embed=embed, view=TicketClaimedView(self.channel_id))
        await interaction.followup.send("✅ Du hast das Ticket übernommen.", ephemeral=True)

    @discord.ui.button(label="Schließen mit Grund", style=discord.ButtonStyle.red, custom_id="ticket_close")
    async def close_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        ticket = await get_ticket(str(self.channel_id))
        if not ticket:
            await interaction.response.send_message("Ticket nicht gefunden!", ephemeral=True)
            return
        if not self._can_close(interaction, ticket):
            await interaction.response.send_message("Du bist nicht berechtigt dieses Ticket zu schließen!", ephemeral=True)
            return
        await interaction.response.send_modal(CloseTicketModal(self.channel_id))

# Claimed ticket view: "Freigeben" + "Schließen mit Grund"
class TicketClaimedView(discord.ui.View):
    def __init__(self, channel_id):
        super().__init__(timeout=None)
        self.channel_id = channel_id

    async def _can_close(self, interaction, ticket):
        user_id = int(ticket["user_id"])
        staff_id = int(ticket["staff_id"]) if ticket["staff_id"] else None
        if interaction.user.id == user_id:
            return True
        if staff_id and interaction.user.id == staff_id:
            return True
        if any(role.id in TICKET_SUPPORT_ROLES for role in interaction.user.roles):
            return True
        return False

    @discord.ui.button(label="Freigeben", style=discord.ButtonStyle.grey, custom_id="ticket_release")
    async def release_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        ticket = await get_ticket(str(self.channel_id))
        if not ticket:
            await interaction.response.send_message("Ticket nicht gefunden!", ephemeral=True)
            return
        if ticket["staff_id"] != str(interaction.user.id):
            await interaction.response.send_message("Nur der zuständige Staff kann das Ticket freigeben!", ephemeral=True)
            return

        await update_ticket_staff(str(self.channel_id), None)

        embed = discord.Embed(
            title="🎫 Support-Ticket",
            description=f"Willkommen im Support-Ticket von <@{ticket['user_id']}>.\nDas Ticket wurde freigegeben und kann von anderen übernommen werden.",
            color=discord.Color.blurple()
        )
        await interaction.response.edit_message(embed=embed, view=TicketActionView(self.channel_id))
        await interaction.followup.send("✅ Du hast das Ticket freigegeben.", ephemeral=True)

    @discord.ui.button(label="Schließen mit Grund", style=discord.ButtonStyle.red, custom_id="ticket_close_claimed")
    async def close_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        ticket = await get_ticket(str(self.channel_id))
        if not ticket:
            await interaction.response.send_message("Ticket nicht gefunden!", ephemeral=True)
            return
        if not self._can_close(interaction, ticket):
            await interaction.response.send_message("Du bist nicht berechtigt dieses Ticket zu schließen!", ephemeral=True)
            return
        await interaction.response.send_modal(CloseTicketModal(self.channel_id))

@bot.tree.command(name="ticket", description="Ticket-System einrichten")
@app_commands.describe(action="setup, um das Ticket-System einzurichten")
@app_commands.choices(action=[app_commands.Choice(name="setup", value="setup")])
async def ticket(interaction: discord.Interaction, action: str):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("Du brauchst Administrator-Rechte!", ephemeral=True)
        return

    if action == "setup":
        channel = interaction.guild.get_channel(TICKET_SETUP_CHANNEL)
        if not channel:
            await interaction.response.send_message("Setup-Channel nicht gefunden!", ephemeral=True)
            return

        async for msg in channel.history(limit=50):
            if msg.author.id == bot.user.id:
                await interaction.response.send_message("Es gibt bereits eine Setup-Nachricht in diesem Channel!", ephemeral=True)
                return

        embed = discord.Embed(
            title="🎫 Ticket-System",
            description="Klicke auf den Button unten, um ein Support-Ticket zu erstellen.",
            color=discord.Color.blurple()
        )
        embed.set_footer(text="Ein Supporter wird sich um dein Anliegen kümmern.")
        await channel.send(embed=embed, view=TicketSetupView())
        await interaction.response.send_message(f"✅ Ticket-Setup wurde in {channel.mention} gesendet!", ephemeral=True)

@bot.tree.command(name="activity", description="Sendet den Aktivitäts-Check in den Activity-Channel")
async def activity(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    channel = interaction.guild.get_channel(1497888557166231684)
    if not channel:
        await interaction.followup.send("Activity-Channel nicht gefunden!", ephemeral=True)
        return

    embed = discord.Embed(
        title="🚨 Aktivitäts-Check | Elbe RP 🚨",
        description=(
            "Hallo zusammen! 👋\n"
            "Wir führen einen **Aktivitäts-Check** durch, um zu sehen, wer weiterhin aktiv bei **Elbe RP (Emergency Hamburg Roblox)** dabei ist.\n\n"
            "Bitte reagiert innerhalb von **7 Tagen** auf diese Nachricht:\n\n"
            "🟢 **Aktiv** → Ich spiele weiterhin aktiv Elbe RP\n"
            "🟡 **Pause** → Ich bin momentan weniger aktiv, komme aber zurück\n"
            "🔴 **Inaktiv** → Ich bin nicht mehr aktiv / möchte den Server verlassen\n\n"
            "Falls ihr **keine Reaktion** hinterlasst, kann es sein, dass eure Rolle entfernt wird oder ihr aus bestimmten Bereichen ausgeschlossen werdet.\n\n"
            "Danke für eure Rückmeldung und weiterhin viel Spaß bei Elbe RP! 🚓🚒🚑"
        ),
        color=discord.Color.blue()
    )
    embed.set_footer(text="Euer Elbe RP Team")

    msg = await channel.send(embed=embed)
    await msg.add_reaction("🟢")
    await msg.add_reaction("🟡")
    await msg.add_reaction("🔴")
    await interaction.followup.send(f"Aktivitäts-Check in {channel.mention} gesendet!", ephemeral=True)

# ─── Auto-Role System ─────────────────────────────────────────────

AUTOROLE_CHANNEL = 1497661367396598057
AUTOROLE_REMOVE_ROLE = 1497661347343892711
AUTOROLE_KICK_AGE = "9-12+"
AUTOROLE_ROLE_13 = 1529835494056263751
AUTOROLE_ROLE_17 = 1529835665162768528

class AutoRoleView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    async def _cleanup(self, interaction: discord.Interaction):
        role = interaction.guild.get_role(AUTOROLE_REMOVE_ROLE)
        if role and role in interaction.user.roles:
            await interaction.user.remove_roles(role)

    @discord.ui.button(label="9-12+", style=discord.ButtonStyle.red, custom_id="autorole_9")
    async def age_9(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._cleanup(interaction)
        try:
            await interaction.user.kick(reason="Altersgruppe 9-12+ – nicht zugelassen")
            await interaction.response.send_message("Du wurdest gekickt, da diese Altersgruppe nicht zugelassen ist.", ephemeral=True)
        except:
            await interaction.response.send_message("Du konntest nicht gekickt werden (fehlende Berechtigungen).", ephemeral=True)

    @discord.ui.button(label="13-16+", style=discord.ButtonStyle.grey, custom_id="autorole_13")
    async def age_13(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._cleanup(interaction)
        role = interaction.guild.get_role(AUTOROLE_ROLE_13)
        if role:
            await interaction.user.add_roles(role)
            await interaction.response.send_message(f"✅ Du hast die Rolle {role.mention} erhalten!", ephemeral=True)

    @discord.ui.button(label="17-99+", style=discord.ButtonStyle.green, custom_id="autorole_17")
    async def age_17(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._cleanup(interaction)
        role = interaction.guild.get_role(AUTOROLE_ROLE_17)
        if role:
            await interaction.user.add_roles(role)
            await interaction.response.send_message(f"✅ Du hast die Rolle {role.mention} erhalten!", ephemeral=True)

@bot.tree.command(name="autorole", description="Autorole-Setup: Sendet die Altersauswahl-Buttons")
@app_commands.describe(action="setup, um die Buttons zu senden")
@app_commands.choices(action=[app_commands.Choice(name="setup", value="setup")])
async def autorole(interaction: discord.Interaction, action: str):
    await interaction.response.defer(ephemeral=True)
    if not interaction.user.get_role(BOT_STAFF_ROLE):
        await interaction.followup.send("Du hast keine Berechtigung dafür!", ephemeral=True)
        return

    channel = interaction.guild.get_channel(AUTOROLE_CHANNEL)
    if not channel:
        await interaction.followup.send("Autorole-Channel nicht gefunden!", ephemeral=True)
        return

    embed = discord.Embed(
        title="🎂 Altersauswahl",
        description="Wähle deine Altersgruppe aus, um die passende Rolle zu erhalten.",
        color=discord.Color.blurple()
    )
    await channel.send(embed=embed, view=AutoRoleView())
    await interaction.followup.send(f"✅ Autorole-Buttons in {channel.mention} gesendet!", ephemeral=True)

# ─── Rules System ─────────────────────────────────────────────────

DISCORD_RULES_CHANNEL = 1497658756652335114
INGAME_RULES_CHANNEL = 1497659024361918635

@bot.tree.command(name="rules", description="Sendet die Regeln in den entsprechenden Channel")
@app_commands.describe(typ="Welche Regeln? (discord oder ingame)")
@app_commands.choices(typ=[
    app_commands.Choice(name="Discord Regeln", value="discord"),
    app_commands.Choice(name="Ingame Regeln", value="ingame"),
])
async def rules(interaction: discord.Interaction, typ: str):
    await interaction.response.defer(ephemeral=True)
    if not interaction.user.get_role(BOT_STAFF_ROLE):
        await interaction.followup.send("Du hast keine Berechtigung dafür!", ephemeral=True)
        return

    if typ == "discord":
        channel = interaction.guild.get_channel(DISCORD_RULES_CHANNEL)
        if not channel:
            await interaction.followup.send("Discord-Regeln Channel nicht gefunden!", ephemeral=True)
            return

        rules_text = (
            "📜 **Discord Regelwerk**\n\n"
            "🧠 **Allgemeines Verhalten**\n"
            "• Behandle alle Mitglieder mit Respekt und Freundlichkeit.\n"
            "• Beleidigungen, Belästigungen, Provokationen oder Mobbing werden nicht toleriert.\n"
            "• Den Anweisungen von Teammitgliedern (Moderatoren/Admins) ist Folge zu leisten.\n"
            "• Absichtliches Stören, Trolling oder das Ausnutzen von Regeln ist verboten.\n"
            "• Verhalte dich so, wie du auch von anderen behandelt werden möchtest.\n\n"
            "💬 **Chat-Regeln**\n"
            "• Kein Spam – dazu zählen Nachrichten-Spam, Emoji-Spam, Flooding oder übermäßiger Caps-Lock-Gebrauch.\n"
            "• Nutze die passenden Channels und bleibe beim jeweiligen Thema.\n"
            "• Vermeide unnötige Pings von Teammitgliedern oder anderen Nutzern.\n"
            "• Werbung, Einladungen oder Eigenwerbung sind nur mit ausdrücklicher Erlaubnis erlaubt.\n"
            "• Keine unangemessenen, beleidigenden oder störenden Inhalte.\n\n"
            "🎧 **Sprachkanäle**\n"
            "• Respektiere andere Nutzer im Voice-Chat.\n"
            "• Kein Schreien, Soundboard-Spam oder absichtliches Stören.\n"
            "• Nutze ein angemessenes Mikrofonverhalten.\n"
            "• Musik oder andere Sounds dürfen andere nicht belästigen.\n\n"
            "🚫 **Verbotene Inhalte**\n"
            "• Keine NSFW-, gewaltverherrlichenden oder illegalen Inhalte.\n"
            "• Keine rassistischen, diskriminierenden oder hasserfüllten Aussagen.\n"
            "• Keine Weitergabe persönlicher Daten von anderen Personen.\n"
            "• Keine Cheats, Exploits oder schädliche Links.\n\n"
            "⚖️ **Konsequenzen**\n"
            "Bei Regelverstößen kann das Team Maßnahmen ergreifen, darunter:\n"
            "• Verwarnungen\n"
            "• Mutes\n"
            "• Kicks\n"
            "• Bans\n\n"
            "Die Entscheidungen des Teams dienen dazu, die Community sicher und angenehm für alle zu halten.\n\n"
            "Mit dem Betreten des Servers akzeptierst du diese Regeln. Viel Spaß und eine gute Zeit auf dem Server! 🚀"
        )
        embed = discord.Embed(title="📜 Discord Regelwerk", description=rules_text, color=discord.Color.blue())
        await channel.send(embed=embed)
        await interaction.followup.send(f"✅ Discord-Regeln in {channel.mention} gesendet!", ephemeral=True)

    elif typ == "ingame":
        channel = interaction.guild.get_channel(INGAME_RULES_CHANNEL)
        if not channel:
            await interaction.followup.send("Ingame-Regeln Channel nicht gefunden!", ephemeral=True)
            return

        rules_text = (
            "📜 **Roleplay Regelwerk**\n\n"
            "🧠 **Allgemeine Regeln**\n"
            "• Ein respektvoller Umgang mit allen Spielern ist jederzeit Pflicht.\n"
            "• Den Anweisungen von Admins und Teammitgliedern ist Folge zu leisten.\n"
            "• Realistisches und faires Roleplay steht immer im Vordergrund.\n"
            "• IC (In Character) und OOC (Out of Character) müssen strikt voneinander getrennt werden.\n"
            "• Absichtliches Stören des Roleplays oder Ausnutzen von Situationen ist verboten.\n\n"
            "🎭 **Roleplay Grundprinzipien**\n"
            "• Spiele deinen Charakter glaubwürdig und passe dein Verhalten der Rolle an.\n"
            "• Handle realistisch und denke über mögliche Konsequenzen deiner Aktionen nach.\n"
            "• Dein Charakter kann nur Dinge wissen, die er im Spiel erfahren hat.\n"
            "• Reagiere angemessen auf Situationen wie Verletzungen, Angst, Stress oder Gefahren.\n"
            "• Fördere gutes Roleplay und gib anderen Spielern die Möglichkeit, ihre Geschichten auszuspielen.\n\n"
            "🚫 **Strengstens verboten**\n\n"
            "❌ **FRP (Fail Roleplay)**\n"
            "→ Unrealistisches, unlogisches oder absichtliches schlechtes Roleplay.\n\n"
            "❌ **VDM (Vehicle Deathmatch)**\n"
            "→ Das absichtliche Verletzen oder Töten von Spielern mit Fahrzeugen ohne RP-Grund.\n\n"
            "❌ **RDM (Random Deathmatch)**\n"
            "→ Das Angreifen oder Töten von Spielern ohne nachvollziehbaren Roleplay-Hintergrund.\n\n"
            "❌ **Taschen-RP**\n"
            "→ Gegenstände oder Aktionen aus einer nicht ausgespielten „unsichtbaren Tasche“ verwenden.\n\n"
            "❌ **Powergaming**\n"
            "→ Andere Spieler zu Handlungen zwingen, ohne ihnen eine Reaktionsmöglichkeit zu geben.\n\n"
            "❌ **Metagaming**\n"
            "→ Informationen nutzen, die dein Charakter nicht im Spiel erhalten hat (z. B. Discord, Streams oder OOC-Chats).\n\n"
            "⚔️ **Konflikte & Situationen**\n"
            "• Konflikte müssen immer einen nachvollziehbaren RP-Grund haben.\n"
            "• Gib anderen Spielern die Chance, auf deine Aktionen zu reagieren.\n"
            "• Gewalt ist die letzte Möglichkeit und muss realistisch ausgespielt werden.\n"
            "• Kein absichtliches Provozieren, um eine Eskalation zu erzwingen.\n\n"
            "⚖️ **Konsequenzen bei Regelverstößen**\n"
            "Bei Verstößen gegen das Regelwerk kann das Team folgende Maßnahmen ergreifen:\n\n"
            "• Verwarnung\n"
            "• Zeitlicher Ausschluss\n"
            "• Kick vom Server\n"
            "• Permanenter Ausschluss\n\n"
            "Das Ziel ist nicht, Spieler zu bestrafen, sondern ein faires und realistisches Roleplay-Erlebnis für alle zu schaffen. 🎭"
        )
        embed = discord.Embed(title="📜 Roleplay Regelwerk", description=rules_text, color=discord.Color.dark_green())
        await channel.send(embed=embed)
        await interaction.followup.send(f"✅ Ingame-Regeln in {channel.mention} gesendet!", ephemeral=True)

# ─── Shift Manage System ──────────────────────────────────────────

SHIFT_DUTY_ROLE = 1498008061212622848
SHIFT_BREAK_ROLE = 1498008128275480718
async def get_shift(guild_id, user_id):
    async with bot.db_pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM shifts WHERE guild_id = $1 AND user_id = $2", guild_id, user_id)

async def upsert_shift(guild_id, user_id, **kwargs):
    async with bot.db_pool.acquire() as conn:
        cols = ", ".join(kwargs.keys())
        vals = list(kwargs.values())
        placeholders = ", ".join(f"${i+3}" for i in range(len(vals)))
        await conn.execute(f"""
            INSERT INTO shifts (guild_id, user_id, {cols})
            VALUES ($1, $2, {placeholders})
            ON CONFLICT (guild_id, user_id)
            DO UPDATE SET {', '.join(f'{k} = EXCLUDED.{k}' for k in kwargs)}
        """, guild_id, user_id, *vals)

async def reset_shift(guild_id, user_id=None):
    async with bot.db_pool.acquire() as conn:
        if user_id:
            await conn.execute("DELETE FROM shifts WHERE guild_id = $1 AND user_id = $2", guild_id, user_id)
        else:
            await conn.execute("DELETE FROM shifts WHERE guild_id = $1", guild_id)

def format_duration(seconds):
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h}h {m}m {s}s"

class ShiftStartView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Start Shift", style=discord.ButtonStyle.green, custom_id="shift_start")
    async def start_shift(self, interaction: discord.Interaction, button: discord.ui.Button):
        duty = interaction.guild.get_role(SHIFT_DUTY_ROLE)
        if duty:
            await interaction.user.add_roles(duty)

        gid = str(interaction.guild.id)
        uid = str(interaction.user.id)
        now = discord.utils.utcnow().timestamp()

        existing = await get_shift(gid, uid)
        total_duty = existing["total_duty"] if existing else 0
        total_break = existing["total_break"] if existing else 0

        await upsert_shift(gid, uid, total_duty=total_duty, total_break=total_break, shift_start=now, break_start=None)

        embed = discord.Embed(
            title="🟢 Shift aktiv",
            description=f"{interaction.user.mention} ist jetzt im Dienst.",
            color=discord.Color.green()
        )
        await interaction.response.edit_message(embed=embed, view=ShiftActiveView(interaction.user.id))

class ShiftActiveView(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=None)
        self.user_id = user_id

    @discord.ui.button(label="Break", style=discord.ButtonStyle.grey, custom_id="shift_break")
    async def break_shift(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Du kannst nur deine eigenen Shift-Buttons bedienen!", ephemeral=True)
            return
        gid = str(interaction.guild.id)
        uid = str(interaction.user.id)
        shift = await get_shift(gid, uid)
        if not shift or not shift["shift_start"]:
            await interaction.response.send_message("Kein aktiver Shift gefunden!", ephemeral=True)
            return

        await upsert_shift(gid, uid, break_start=discord.utils.utcnow().timestamp())

        break_role = interaction.guild.get_role(SHIFT_BREAK_ROLE)
        if break_role:
            await interaction.user.add_roles(break_role)

        embed = discord.Embed(
            title="🟡 Break",
            description=f"{interaction.user.mention} ist jetzt in der Pause.",
            color=discord.Color.gold()
        )
        await interaction.response.edit_message(embed=embed, view=ShiftBreakView(interaction.user.id))

    @discord.ui.button(label="Stop", style=discord.ButtonStyle.red, custom_id="shift_stop_active")
    async def stop_shift(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._end_shift(interaction)

    async def _end_shift(self, interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Du kannst nur deine eigenen Shift-Buttons bedienen!", ephemeral=True)
            return
        gid = str(interaction.guild.id)
        uid = str(interaction.user.id)
        shift = await get_shift(gid, uid)
        if not shift or not shift["shift_start"]:
            await interaction.response.send_message("Kein aktiver Shift gefunden!", ephemeral=True)
            return

        now = discord.utils.utcnow().timestamp()
        elapsed = int(now - shift["shift_start"])
        new_total = shift["total_duty"] + elapsed

        if shift["break_start"]:
            break_elapsed = int(now - shift["break_start"])
            new_break = shift["total_break"] + break_elapsed
        else:
            new_break = shift["total_break"]

        await upsert_shift(gid, uid, total_duty=new_total, total_break=new_break, shift_start=None, break_start=None)

        duty = interaction.guild.get_role(SHIFT_DUTY_ROLE)
        if duty and duty in interaction.user.roles:
            await interaction.user.remove_roles(duty)
        break_role = interaction.guild.get_role(SHIFT_BREAK_ROLE)
        if break_role and break_role in interaction.user.roles:
            await interaction.user.remove_roles(break_role)

        embed = discord.Embed(
            title="🔴 Shift beendet",
            description=f"Shift von {interaction.user.mention} beendet.",
            color=discord.Color.red()
        )
        embed.add_field(name="⏱️ Dienstzeit", value=format_duration(elapsed), inline=True)
        embed.add_field(name="📊 Gesamt (alle Shifts)", value=f"Dienst: {format_duration(new_total)}\nPause: {format_duration(new_break)}", inline=False)
        await interaction.response.edit_message(embed=embed, view=ShiftStartView())

class ShiftBreakView(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=None)
        self.user_id = user_id

    @discord.ui.button(label="Continue", style=discord.ButtonStyle.green, custom_id="shift_continue")
    async def continue_shift(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Du kannst nur deine eigenen Shift-Buttons bedienen!", ephemeral=True)
            return
        gid = str(interaction.guild.id)
        uid = str(interaction.user.id)
        shift = await get_shift(gid, uid)
        if not shift or not shift["break_start"]:
            await interaction.response.send_message("Kein Break gefunden!", ephemeral=True)
            return

        now = discord.utils.utcnow().timestamp()
        break_elapsed = int(now - shift["break_start"])
        new_break = shift["total_break"] + break_elapsed
        await upsert_shift(gid, uid, total_break=new_break, break_start=None)

        break_role = interaction.guild.get_role(SHIFT_BREAK_ROLE)
        if break_role and break_role in interaction.user.roles:
            await interaction.user.remove_roles(break_role)

        embed = discord.Embed(
            title="🟢 Shift aktiv",
            description=f"{interaction.user.mention} ist wieder im Dienst.",
            color=discord.Color.green()
        )
        await interaction.response.edit_message(embed=embed, view=ShiftActiveView(interaction.user.id))

    @discord.ui.button(label="Stop", style=discord.ButtonStyle.red, custom_id="shift_stop_break")
    async def stop_shift(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Du kannst nur deine eigenen Shift-Buttons bedienen!", ephemeral=True)
            return
        gid = str(interaction.guild.id)
        uid = str(interaction.user.id)
        shift = await get_shift(gid, uid)
        if not shift or not shift["shift_start"]:
            await interaction.response.send_message("Kein aktiver Shift gefunden!", ephemeral=True)
            return

        now = discord.utils.utcnow().timestamp()
        if shift["break_start"]:
            break_elapsed = int(now - shift["break_start"])
            new_break = shift["total_break"] + break_elapsed
        else:
            new_break = shift["total_break"]

        elapsed = int(now - shift["shift_start"])
        new_total = shift["total_duty"] + elapsed
        await upsert_shift(gid, uid, total_duty=new_total, total_break=new_break, shift_start=None, break_start=None)

        duty = interaction.guild.get_role(SHIFT_DUTY_ROLE)
        if duty and duty in interaction.user.roles:
            await interaction.user.remove_roles(duty)
        break_role = interaction.guild.get_role(SHIFT_BREAK_ROLE)
        if break_role and break_role in interaction.user.roles:
            await interaction.user.remove_roles(break_role)

        embed = discord.Embed(
            title="🔴 Shift beendet",
            description=f"Shift von {interaction.user.mention} beendet.",
            color=discord.Color.red()
        )
        embed.add_field(name="⏱️ Dienstzeit", value=format_duration(elapsed), inline=True)
        embed.add_field(name="📊 Gesamt (alle Shifts)", value=f"Dienst: {format_duration(new_total)}\nPause: {format_duration(new_break)}", inline=False)
        await interaction.response.edit_message(embed=embed, view=ShiftStartView())

@bot.tree.command(name="shiftmanage", description="Shift-Management: Starte/Stoppe deinen Dienst")
async def shiftmanage(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=False)

    gid = str(interaction.guild.id)
    uid = str(interaction.user.id)
    shift = await get_shift(gid, uid)
    total_duty = shift["total_duty"] if shift else 0
    total_break = shift["total_break"] if shift else 0
    shift_start = shift["shift_start"] if shift else None
    break_start = shift["break_start"] if shift else None

    embed = discord.Embed(
        title="👮 Shift-Management",
        description="Verwalte deine Dienstzeit.",
        color=discord.Color.blurple()
    )
    embed.add_field(name="📊 Statistik", value=f"Dienstzeit gesamt: {format_duration(total_duty)}\nPause gesamt: {format_duration(total_break)}", inline=False)

    if shift_start:
        if break_start:
            await interaction.followup.send(embed=embed, view=ShiftBreakView(interaction.user.id))
        else:
            await interaction.followup.send(embed=embed, view=ShiftActiveView(interaction.user.id))
    else:
        await interaction.followup.send(embed=embed, view=ShiftStartView())

@bot.tree.command(name="resetduty", description="Setzt die Shift-Daten eines Members zurück")
@app_commands.describe(member="Der Member dessen Daten zurückgesetzt werden sollen")
async def resetduty(interaction: discord.Interaction, member: discord.Member):
    await interaction.response.defer(ephemeral=True)
    if not interaction.user.get_role(1497932354524676207):
        await interaction.followup.send("Du hast keine Berechtigung dafür!", ephemeral=True)
        return

    await reset_shift(str(interaction.guild.id), str(member.id))
    await interaction.followup.send(f"✅ Shift-Daten von {member.mention} wurden zurückgesetzt.", ephemeral=True)

@bot.tree.command(name="resetall", description="Setzt ALLE Shift-Daten aller Member zurück")
async def resetall(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    if not interaction.user.get_role(1497932354524676207):
        await interaction.followup.send("Du hast keine Berechtigung dafür!", ephemeral=True)
        return

    await reset_shift(str(interaction.guild.id))
    await interaction.followup.send("✅ Alle Shift-Daten wurden zurückgesetzt.", ephemeral=True)

# ─── Saved Messages ──────────────────────────────────────────────

async def save_message(guild_id, name, titel, content, created_by):
    async with bot.db_pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO saved_messages (guild_id, name, titel, content, created_by)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (guild_id, name) DO UPDATE SET titel = $3, content = $4, created_by = $5
        """, guild_id, name, titel, content, created_by)

async def get_saved_message(guild_id, name):
    async with bot.db_pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM saved_messages WHERE guild_id = $1 AND name = $2", guild_id, name)

async def get_all_saved_messages(guild_id):
    async with bot.db_pool.acquire() as conn:
        return await conn.fetch("SELECT * FROM saved_messages WHERE guild_id = $1 ORDER BY id", guild_id)

async def delete_saved_message(guild_id, name):
    async with bot.db_pool.acquire() as conn:
        await conn.execute("DELETE FROM saved_messages WHERE guild_id = $1 AND name = $2", guild_id, name)

@bot.tree.command(name="savemessage", description="Speichert eine Nachricht als Vorlage")
@app_commands.describe(name="Name der Vorlage", titel="Titel der Nachricht", nachricht="Inhalt der Nachricht")
async def savemessage(interaction: discord.Interaction, name: str, titel: str, nachricht: str):
    await interaction.response.defer(ephemeral=True)
    if not interaction.user.guild_permissions.administrator:
        await interaction.followup.send("Du brauchst Administrator-Rechte!", ephemeral=True)
        return

    await save_message(str(interaction.guild.id), name.lower(), titel, nachricht, str(interaction.user))
    await interaction.followup.send(f"✅ Nachricht **{name}** gespeichert!", ephemeral=True)

@bot.tree.command(name="sendmessage", description="Sendet eine gespeicherte Nachricht in einen Channel")
@app_commands.describe(name="Name der Vorlage", channel="Der Ziel-Channel")
async def sendmessage(interaction: discord.Interaction, name: str, channel: discord.TextChannel):
    await interaction.response.defer(ephemeral=True)
    if not interaction.user.guild_permissions.administrator:
        await interaction.followup.send("Du brauchst Administrator-Rechte!", ephemeral=True)
        return

    msg = await get_saved_message(str(interaction.guild.id), name.lower())
    if not msg:
        await interaction.followup.send(f"❌ Keine Nachricht mit dem Namen **{name}** gefunden.", ephemeral=True)
        return

    embed = discord.Embed(title=msg["titel"], description=msg["content"], color=discord.Color.blue())
    embed.set_footer(text=f"Gespeichert von {msg['created_by']}")
    await channel.send(embed=embed)
    await send_log(interaction.guild, "SendMessage", interaction.user, channel, f"Vorlage: {name}")
    await interaction.followup.send(f"✅ **{name}** wurde in {channel.mention} gesendet!", ephemeral=True)

@bot.tree.command(name="deletemessage", description="Löscht eine gespeicherte Nachricht")
@app_commands.describe(name="Name der Vorlage")
async def deletemessage(interaction: discord.Interaction, name: str):
    await interaction.response.defer(ephemeral=True)
    if not interaction.user.guild_permissions.administrator:
        await interaction.followup.send("Du brauchst Administrator-Rechte!", ephemeral=True)
        return

    msg = await get_saved_message(str(interaction.guild.id), name.lower())
    if not msg:
        await interaction.followup.send(f"❌ Keine Nachricht mit dem Namen **{name}** gefunden.", ephemeral=True)
        return

    await delete_saved_message(str(interaction.guild.id), name.lower())
    await interaction.followup.send(f"✅ **{name}** wurde gelöscht.", ephemeral=True)

@bot.tree.command(name="savedmessages", description="Zeigt alle gespeicherten Nachrichten an")
async def savedmessages(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    if not interaction.user.guild_permissions.administrator:
        await interaction.followup.send("Du brauchst Administrator-Rechte!", ephemeral=True)
        return

    msgs = await get_all_saved_messages(str(interaction.guild.id))
    if not msgs:
        await interaction.followup.send("Keine gespeicherten Nachrichten.", ephemeral=True)
        return

    embed = discord.Embed(title="📦 Gespeicherte Nachrichten", color=discord.Color.blue())
    for m in msgs:
        embed.add_field(name=m["name"], value=f"Titel: {m['titel']}\nInhalt: {m['content'][:50]}{'...' if len(m['content']) > 50 else ''}", inline=False)

    await interaction.followup.send(embed=embed, ephemeral=True)


@bot.tree.command(name="warninfo", description="Zeigt alle Verwarnungen eines Members an")
@app_commands.describe(member="Der Member")
async def warninfo(interaction: discord.Interaction, member: discord.Member):
    await interaction.response.defer(ephemeral=True)
    if not interaction.user.guild_permissions.kick_members:
        await interaction.followup.send("Du hast keine Berechtigung dafür!", ephemeral=True)
        return

    guild_id = str(interaction.guild.id)
    user_id = str(member.id)
    warns = await get_warns(guild_id, user_id)

    if not warns:
        await interaction.followup.send(f"{member.mention} hat keine Verwarnungen.", ephemeral=True)
        return

    embed = discord.Embed(title=f"⚠️ Verwarnungen – {member.display_name}", color=discord.Color.orange())
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="Anzahl", value=f"{len(warns)}/3", inline=False)

    for i, w in enumerate(warns, 1):
        embed.add_field(name=f"#{i} – {w['datum']}", value=f"Grund: {w['grund']}\nVon: {w['von']}", inline=False)

    embed.set_footer(text=f"ID: {member.id}")
    await interaction.followup.send(embed=embed, ephemeral=True)


@bot.tree.command(name="userinfo", description="Zeigt detaillierte Informationen über einen Member an")
@app_commands.describe(member="Der Member")
async def userinfo(interaction: discord.Interaction, member: discord.Member):
    await interaction.response.defer(ephemeral=True)
    if not interaction.user.guild_permissions.kick_members:
        await interaction.followup.send("Du hast keine Berechtigung dafür!", ephemeral=True)
        return

    guild_id = str(interaction.guild.id)
    user_id = str(member.id)

    warns = await get_warns(guild_id, user_id)
    notizen = await get_notizen(guild_id)
    member_notizen = notizen.get(user_id, [])

    embed = discord.Embed(title=f"👤 {member.display_name}", color=member.color or discord.Color.blurple())
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="Benutzername", value=member.mention, inline=True)
    embed.add_field(name="ID", value=member.id, inline=True)
    embed.add_field(name="Beigetreten", value=discord.utils.format_dt(member.joined_at, style="D") if member.joined_at else "Unbekannt", inline=True)
    embed.add_field(name="Erstellt", value=discord.utils.format_dt(member.created_at, style="D"), inline=True)
    embed.add_field(name="Rollen", value=len(member.roles[1:]), inline=True)
    embed.add_field(name="Warns", value=f"{len(warns)}/3", inline=True)
    embed.add_field(name="Notizen", value=str(len(member_notizen)), inline=True)

    top_roles = ", ".join(r.mention for r in member.roles[-5:][::-1] if r.name != "@everyone")
    if top_roles:
        embed.add_field(name="Top-Rollen", value=top_roles, inline=False)

    if warns:
        embed.add_field(name="Letzter Warn", value=f"{warns[-1]['grund']} ({warns[-1]['datum']})", inline=False)
    if member_notizen:
        embed.add_field(name="Letzte Notiz", value=member_notizen[-1]["text"], inline=False)

    embed.set_footer(text=f"Bot-Staff: {BOT_STAFF_ROLE}")
    await interaction.followup.send(embed=embed, ephemeral=True)


@bot.tree.command(name="voicemove", description="Verschiebt einen Member in einen anderen Voice-Channel")
@app_commands.describe(member="Der Member", channel="Der Ziel-Voice-Channel")
async def voicemove(interaction: discord.Interaction, member: discord.Member, channel: discord.VoiceChannel):
    await interaction.response.defer(ephemeral=True)

    if not interaction.user.guild_permissions.move_members:
        await interaction.followup.send("Du hast keine Berechtigung Member zu verschieben!", ephemeral=True)
        return
    if not interaction.guild.me.guild_permissions.move_members:
        await interaction.followup.send("Ich habe keine Berechtigung Member zu verschieben!", ephemeral=True)
        return
    if not member.voice or not member.voice.channel:
        await interaction.followup.send(f"{member.mention} ist in keinem Voice-Channel!", ephemeral=True)
        return
    if member.voice.channel.id == channel.id:
        await interaction.followup.send(f"{member.mention} ist bereits in {channel.mention}!", ephemeral=True)
        return

    try:
        await member.move_to(channel, reason=f"Verschoben von {interaction.user}")
        await send_log(interaction.guild, "VoiceMove", interaction.user, member, f"Von: {member.voice.channel.mention}\nNach: {channel.mention}", discord.Color.blue())
        await interaction.followup.send(f"✅ {member.mention} wurde nach {channel.mention} verschoben.", ephemeral=True)
    except discord.Forbidden:
        await interaction.followup.send("Ich habe keine Berechtigung diesen Member zu verschieben!", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"Fehler beim Verschieben: {e}", ephemeral=True)


@bot.tree.command(name="vorlage", description="Sendet die Werbevorlage in den Werbe-Channel")
async def vorlage(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    if not interaction.user.get_role(BOT_STAFF_ROLE):
        await interaction.followup.send("Du hast keine Berechtigung dafür!", ephemeral=True)
        return

    channel = interaction.guild.get_channel(1498199142911184936)
    if not channel:
        await interaction.followup.send("Werbe-Channel nicht gefunden!", ephemeral=True)
        return

    text = (
        ":flag_de: **Elbe RP | :microphone2:**\n\n"
        "Willst du ein spannendes Roleplay erleben und Teil einer starken Community werden? "
        "Dann komm zu :flag_de: **Elbe RP | :microphone2:**\n\n"
        "Bei :flag_de: **Elbe RP | :microphone2:** kannst du viele verschiedene Jobs ausprobieren "
        "und deinen eigenen Weg gehen. Egal ob du Menschen helfen willst, für Recht und Ordnung "
        "sorgen möchtest oder spannende Einsätze erleben willst – hier ist für jeden etwas dabei!\n\n"
        "**Unsere Jobs zum Beispiel:**\n\n"
        ":red_car: **ADAC** – Hilf Spielern bei Pannen und Unfällen.\n"
        ":scales: **Polizei** – Arbeite bei der Polizei und sorge für Gerechtigkeit.\n"
        ":fire_engine: **Feuerwehr** – Lösche Brände und rette Menschen aus gefährlichen Situationen.\n"
        ":military_helmet: **Sek** – Erlebe spektakuläre Einsätze und arbeite im Team.\n\n"
        "Aber das ist noch lange nicht alles! Bei :flag_de: **Elbe RP | :microphone2:** erwarten "
        "dich viele weitere Möglichkeiten, spannende Storys und ein realistisches Roleplay.\n\n"
        ":handshake: Unser Team ist freundlich, hilfsbereit und immer für euch da.\n"
        ":crescent_moon: Zusammen könnt ihr viele coole Abende erleben, lachen und unvergessliche Momente im RP haben.\n\n"
        ":point_right: Also worauf wartest du noch? Join :flag_de: **Elbe RP | :microphone2:** "
        "und werde Teil unserer Community!\n\n"
        "https://discord.gg/wPhhBvbmaj\n\n"
        "Wir hoffen, dass ihr uns joint! :blue_heart:"
    )

    embed = discord.Embed(
        title=":flag_de: Elbe RP | :microphone2:",
        description=text,
        color=discord.Color.blue()
    )
    await channel.send(embed=embed)
    await interaction.followup.send(f"✅ Vorlage wurde in {channel.mention} gesendet!", ephemeral=True)


bot.run(TOKEN)
