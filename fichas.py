import asyncio
import sqlite3
import os
from pathlib import Path
from typing import Optional

import discord
from discord import app_commands

REVIEW_CHANNEL_ID = 1543580022399311903
DELETE_ROLE_ID = 1563912834616655892
CLAN_LIMIT = 5
# Para cambiar el límite de miembros de cada aldea, modifica este valor.
VILLAGE_LIMIT = 100

CLANS = {
    "Uchiha": 1544420692907397261,
    "Senju": 1544420894674526259,
    "Namikaze": 1544421110999687230,
    "Hyuga": 1544421002476519535,
    "Sarutobi": 1544420795709919362,
    "Yuki": 1544421498897563688,
    "Lee": 1544422359937712218,
    "Aburame": 1544421300863504414,
    "Sabaku": 1544421411744124928,
    "Uzumaki": 1544421208836284496,
    "Chinoike": 1563911034488492155,
    "Hatake": 1563911483140743228,
    "Nara": 1563911332703772754,
}
VILLAGES = {
    "Konohagakure": 1543575782130188329,
    "Sunagakure": 1543575908185669713,
}
ELEMENTS = {
    "Katon (Fuego)": 1543325475475296390,
    "Raiton (Rayo)": 1543325995312877759,
    "Doton (Tierra)": 1543325835011035167,
    "Suiton (Agua)": 1543325704140234882,
    "Fūton (Viento)": 1543325589207916605,
}
SPECIALTIES = {
    "Ninjutsu": 1543324515864547388,
    "Taijutsu": 1543324380828794880,
    "Genjutsu": 1543324637251899402,
    "Ninjutsu Médico": 1543324751789821983,
    "Fūinjutsu": 1543324864704946327,
}

DB_PATH = Path(os.getenv("DATA_DIR", ".")) / "fichas.sqlite3"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with db() as con:
        con.execute("""CREATE TABLE IF NOT EXISTS fichas (
            user_id INTEGER PRIMARY KEY,
            guild_id INTEGER NOT NULL,
            character_name TEXT NOT NULL,
            clan TEXT NOT NULL,
            village TEXT NOT NULL,
            elements TEXT NOT NULL,
            specialties TEXT NOT NULL,
            objectives TEXT NOT NULL,
            history TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'draft',
            review_message_id INTEGER,
            review_channel_id INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS settings (
            guild_id INTEGER PRIMARY KEY,
            panel_channel_id INTEGER,
            panel_message_id INTEGER
        )""")

def get_profile(user_id):
    with db() as con:
        return con.execute("SELECT * FROM fichas WHERE user_id=?", (user_id,)).fetchone()

def save_profile(data):
    with db() as con:
        con.execute("""INSERT INTO fichas
            (user_id,guild_id,character_name,clan,village,elements,specialties,objectives,history,status)
            VALUES (?,?,?,?,?,?,?,?,?,'pending')
            ON CONFLICT(user_id) DO UPDATE SET
            guild_id=excluded.guild_id, character_name=excluded.character_name,
            clan=excluded.clan, village=excluded.village, elements=excluded.elements,
            specialties=excluded.specialties, objectives=excluded.objectives,
            history=excluded.history, status='pending', review_message_id=NULL,
            review_channel_id=NULL, created_at=CURRENT_TIMESTAMP""",
            (data["user_id"], data["guild_id"], data["name"], data["clan"], data["village"],
             "|".join(data["elements"]), "|".join(data["specialties"]), data["objectives"], data["history"]))

def update_status(user_id, status, message_id=None):
    with db() as con:
        con.execute("UPDATE fichas SET status=?, review_message_id=? WHERE user_id=?",
                    (status, message_id, user_id))

def delete_profile(user_id):
    with db() as con:
        con.execute("DELETE FROM fichas WHERE user_id=?", (user_id,))

def all_profiles(guild_id):
    with db() as con:
        return con.execute("SELECT * FROM fichas WHERE guild_id=?", (guild_id,)).fetchall()

class FichasSystem:
    def __init__(self, bot):
        self.bot = bot
        self._locks = {}

    async def setup(self):
        init_db()
        # Registrar el panel principal persistente tras reinicios.
        self.bot.add_view(MainPanelView(self))
        # Reanudar botones persistentes de los mensajes de revisión que siguen pendientes.
        for guild in self.bot.guilds:
            with db() as con:
                rows = con.execute("SELECT user_id, review_message_id FROM fichas WHERE guild_id=? AND status='pending' AND review_message_id IS NOT NULL", (guild.id,)).fetchall()
            for row in rows:
                self.bot.add_view(ReviewView(self, row["user_id"]))

    def lock_for(self, guild_id):
        return self._locks.setdefault(guild_id, asyncio.Lock())

    async def publish_main_panel(self, interaction):
        embed = discord.Embed(
            title="📜・FICHAS OC",
            description="Crea tu personaje original y envía su ficha para revisión.\n\n"
                        "🥷 **Una ficha por usuario**\n"
                        "🔥 Elige hasta **2 elementos**\n"
                        "⚔️ Elige hasta **2 especialidades**\n"
                        "🏯 Selecciona tu aldea\n\n"
                        "Pulsa **Crear OC** para empezar.",
            color=discord.Color.dark_teal()
        )
        embed.add_field(name="Cupos de clanes", value=await self.clan_summary(interaction.guild), inline=False)
        view = MainPanelView(self)
        await interaction.channel.send(embed=embed, view=view)
        await interaction.response.send_message("✅ Panel de fichas publicado.", ephemeral=True)

    async def refresh_panels(self, guild):
        if not guild:
            return
        # Actualiza el panel principal si fue guardado por /publicar_fichas (buscarlo por custom_id no requiere almacenar mensaje).
        # El comando /cupos siempre consulta los roles actuales, así que nunca muestra datos en caché.
        return

    async def handle_member_update(self, before, after):
        before_ids = {r.id for r in before.roles}
        after_ids = {r.id for r in after.roles}
        if before_ids != after_ids:
            await self.refresh_panels(after.guild)

    async def clan_summary(self, guild):
        parts = []
        for name, role_id in CLANS.items():
            role = guild.get_role(role_id)
            count = len(role.members) if role else 0
            parts.append(f"**{name}** — `{count}/{CLAN_LIMIT}` · {max(0, CLAN_LIMIT-count)} disponibles")
        return "\n".join(parts)

    async def show_clan_cupos(self, interaction):
        guild = interaction.guild
        if not guild:
            await interaction.response.send_message("Usa este comando dentro del servidor.", ephemeral=True)
            return
        embed = discord.Embed(title="🥷・CUPOS DE CLANES", color=discord.Color.dark_teal())
        for name, role_id in CLANS.items():
            role = guild.get_role(role_id)
            members = list(role.members) if role else []
            member_text = ", ".join(m.mention for m in members[:20]) or "Ningún miembro"
            if len(members) > 20:
                member_text += f" y {len(members)-20} más"
            embed.add_field(
                name=f"{name} — {len(members)}/{CLAN_LIMIT} ({max(0, CLAN_LIMIT-len(members))} disponibles)",
                value=member_text,
                inline=False
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def show_village_cupos(self, interaction):
        guild = interaction.guild
        if not guild:
            await interaction.response.send_message("Usa este comando dentro del servidor.", ephemeral=True)
            return
        embed = discord.Embed(title="🏯・MIEMBROS POR ALDEA", color=discord.Color.dark_teal())
        for name, role_id in VILLAGES.items():
            role = guild.get_role(role_id)
            members = list(role.members) if role else []
            member_text = ", ".join(m.mention for m in members[:25]) or "Ningún miembro"
            if len(members) > 25:
                member_text += f" y {len(members)-25} más"
            embed.add_field(name=f"{name} — {len(members)} miembros", value=member_text, inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def start_creation(self, interaction):
        existing = get_profile(interaction.user.id)
        if existing:
            msg = "Ya tienes una ficha registrada. Usa **Ver mi OC** o solicita al staff que la elimine antes de crear otra."
            if existing["status"] == "rejected":
                msg = "Tu ficha anterior fue rechazada. Usa **Ver mi OC** para consultar el estado y contacta con el staff para volver a enviarla."
            await interaction.response.send_message(msg, ephemeral=True)
            return
        await interaction.response.send_modal(NameModal(self))

    async def send_review(self, interaction, data):
        guild = interaction.guild
        channel = guild.get_channel(REVIEW_CHANNEL_ID) if guild else None
        if not isinstance(channel, discord.TextChannel):
            await interaction.followup.send("❌ No encuentro el canal de revisión. Comprueba el ID y que el bot pueda verlo.", ephemeral=True)
            return
        embed = discord.Embed(title="📜 Nueva ficha OC", color=discord.Color.orange())
        embed.add_field(name="Personaje", value=data["name"], inline=False)
        embed.add_field(name="Usuario", value=f"<@{data['user_id']}> (`{data['user_id']}`)", inline=False)
        embed.add_field(name="Clan", value=data["clan"], inline=True)
        embed.add_field(name="Aldea", value=data["village"], inline=True)
        embed.add_field(name="Elementos", value=", ".join(data["elements"]), inline=False)
        embed.add_field(name="Especialidades", value=", ".join(data["specialties"]), inline=False)
        embed.add_field(name="Objetivos", value=data["objectives"][:1024], inline=False)
        embed.add_field(name="Historia", value=data["history"][:1024], inline=False)
        embed.set_footer(text="Estado: pendiente de revisión")
        message = await channel.send(embed=embed, view=ReviewView(self, data["user_id"]))
        with db() as con:
            con.execute("UPDATE fichas SET review_message_id=?, review_channel_id=? WHERE user_id=?",
                        (message.id, channel.id, data["user_id"]))
        await interaction.followup.send("✅ Tu ficha se ha enviado al staff para su revisión.", ephemeral=True)

    async def approve(self, interaction, user_id):
        if not interaction.user.guild_permissions.manage_roles and not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("No tienes permisos para aprobar fichas.", ephemeral=True)
            return
        lock = self.lock_for(interaction.guild_id)
        async with lock:
            row = get_profile(user_id)
            if not row or row["status"] != "pending":
                await interaction.response.send_message("Esta ficha ya fue procesada o no existe.", ephemeral=True)
                return
            guild = interaction.guild
            clan_role = guild.get_role(CLANS[row["clan"]])
            village_role = guild.get_role(VILLAGES[row["village"]])
            if not clan_role or not village_role:
                await interaction.response.send_message("Falta uno de los roles configurados. Revisa los IDs.", ephemeral=True)
                return
            if len(clan_role.members) >= CLAN_LIMIT:
                await interaction.response.send_message(f"❌ {row['clan']} ya está completo ({CLAN_LIMIT}/{CLAN_LIMIT}).", ephemeral=True)
                return
            if len(village_role.members) >= VILLAGE_LIMIT:
                await interaction.response.send_message(f"❌ {row['village']} ha alcanzado su límite configurado.", ephemeral=True)
                return
            member = guild.get_member(user_id)
            if member is None:
                try:
                    member = await guild.fetch_member(user_id)
                except discord.NotFound:
                    await interaction.response.send_message("El usuario ya no está en el servidor.", ephemeral=True)
                    return
            role_ids = [CLANS[row["clan"]], VILLAGES[row["village"]]]
            role_ids += [ELEMENTS[x] for x in row["elements"].split("|") if x]
            role_ids += [SPECIALTIES[x] for x in row["specialties"].split("|") if x]
            roles = [guild.get_role(rid) for rid in role_ids]
            if any(r is None for r in roles):
                await interaction.response.send_message("Falta algún rol configurado. Revisa los IDs.", ephemeral=True)
                return
            try:
                await member.add_roles(*roles, reason=f"Ficha OC aprobada por {interaction.user}")
            except discord.Forbidden:
                await interaction.response.send_message("No puedo asignar los roles. Coloca el rol del bot por encima de los roles OC y habilita Gestionar roles.", ephemeral=True)
                return
            update_status(user_id, "approved", row["review_message_id"])
            try:
                await member.send(f"✅ ¡Tu ficha OC **{row['character_name']}** ha sido aceptada! Ya tienes los roles de clan, aldea, elementos y especialidades.")
            except discord.Forbidden:
                pass
            embed = interaction.message.embeds[0]
            embed.color = discord.Color.green()
            embed.set_footer(text=f"Aprobada por {interaction.user}")
            await interaction.response.edit_message(embed=embed, view=ReviewDoneView())
            await self.refresh_panels(guild)

    async def reject(self, interaction, user_id):
        if not interaction.user.guild_permissions.manage_roles and not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("No tienes permisos para rechazar fichas.", ephemeral=True)
            return
        await interaction.response.send_modal(RejectModal(self, user_id, interaction.message.id))

    async def finish_rejection(self, interaction, user_id, reason, message_id):
        row = get_profile(user_id)
        if not row or row["status"] != "pending":
            await interaction.response.send_message("Esta ficha ya fue procesada o no existe.", ephemeral=True)
            return
        update_status(user_id, "rejected", message_id)
        try:
            user = self.bot.get_user(user_id) or await self.bot.fetch_user(user_id)
            await user.send(f"❌ Tu ficha OC **{row['character_name']}** ha sido rechazada.\n**Motivo:** {reason}")
        except (discord.Forbidden, discord.NotFound):
            pass
        embed = interaction.message.embeds[0]
        embed.color = discord.Color.red()
        embed.set_footer(text=f"Rechazada por {interaction.user} · Motivo: {reason[:150]}")
        await interaction.response.edit_message(embed=embed, view=ReviewDoneView())

    async def show_profile(self, interaction):
        row = get_profile(interaction.user.id)
        if not row:
            await interaction.response.send_message("Todavía no tienes una ficha registrada.", ephemeral=True)
            return
        embed = discord.Embed(title=f"📜 OC · {row['character_name']}", color=discord.Color.blurple())
        embed.add_field(name="Estado", value=row["status"].capitalize(), inline=True)
        embed.add_field(name="Clan", value=row["clan"], inline=True)
        embed.add_field(name="Aldea", value=row["village"], inline=True)
        embed.add_field(name="Elementos", value=row["elements"].replace("|", ", "), inline=False)
        embed.add_field(name="Especialidades", value=row["specialties"].replace("|", ", "), inline=False)
        embed.add_field(name="Objetivos", value=row["objectives"][:1024], inline=False)
        embed.add_field(name="Historia", value=row["history"][:1024], inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def begin_delete(self, interaction):
        if not any(r.id == DELETE_ROLE_ID for r in getattr(interaction.user, "roles", [])):
            await interaction.response.send_message("❌ No tienes el rol autorizado para eliminar fichas.", ephemeral=True)
            return
        await interaction.response.send_message("¿Seguro que quieres eliminar tu ficha OC? Esto retirará los roles asociados a ella.", view=DeleteConfirmView(self, interaction.user.id), ephemeral=True)

    async def confirm_delete(self, interaction, user_id):
        if interaction.user.id != user_id:
            await interaction.response.send_message("Este botón no te pertenece.", ephemeral=True)
            return
        if not any(r.id == DELETE_ROLE_ID for r in getattr(interaction.user, "roles", [])):
            await interaction.response.send_message("No tienes permiso para eliminar fichas.", ephemeral=True)
            return
        row = get_profile(user_id)
        if not row:
            await interaction.response.send_message("No tienes ninguna ficha guardada.", ephemeral=True)
            return
        guild = interaction.guild
        member = guild.get_member(user_id) if guild else None
        if member:
            ids = [CLANS.get(row["clan"]), VILLAGES.get(row["village"])]
            ids += [ELEMENTS.get(x) for x in row["elements"].split("|") if x]
            ids += [SPECIALTIES.get(x) for x in row["specialties"].split("|") if x]
            roles = [guild.get_role(rid) for rid in ids if rid]
            roles = [r for r in roles if r and r in member.roles]
            try:
                if roles:
                    await member.remove_roles(*roles, reason="Ficha OC eliminada por usuario autorizado")
            except discord.Forbidden:
                await interaction.response.send_message("No puedo retirar roles. Revisa el permiso Gestionar roles y la jerarquía del bot.", ephemeral=True)
                return
        delete_profile(user_id)
        await interaction.response.edit_message(content="✅ Ficha eliminada y roles asociados retirados.", view=None)
        await self.refresh_panels(guild)

    async def edit_pending(self, interaction, data):
        save_profile(data)
        await self.send_review(interaction, data)

class MainPanelView(discord.ui.View):
    def __init__(self, system):
        super().__init__(timeout=None)
        self.system = system

    @discord.ui.button(label="Crear OC", style=discord.ButtonStyle.success, emoji="📝", custom_id="oc:create")
    async def create(self, interaction, button):
        await self.system.start_creation(interaction)

    @discord.ui.button(label="Ver mi OC", style=discord.ButtonStyle.primary, emoji="📜", custom_id="oc:view")
    async def view_profile(self, interaction, button):
        await self.system.show_profile(interaction)

    @discord.ui.button(label="Eliminar OC", style=discord.ButtonStyle.danger, emoji="🗑️", custom_id="oc:delete")
    async def delete(self, interaction, button):
        await self.system.begin_delete(interaction)

class NameModal(discord.ui.Modal, title="Crear OC · Paso 1/4"):
    name = discord.ui.TextInput(label="Nombre del personaje", max_length=80, placeholder="Ej. Itachi Uchiha")
    def __init__(self, system):
        super().__init__()
        self.system = system
    async def on_submit(self, interaction):
        existing = get_profile(interaction.user.id)
        if existing:
            await interaction.response.send_message("Ya tienes una ficha registrada.", ephemeral=True)
            return
        data = {"user_id": interaction.user.id, "guild_id": interaction.guild_id, "name": str(self.name).strip()}
        await interaction.response.send_message("Elige el clan y la aldea de tu personaje:", view=ClanVillageView(self.system, data), ephemeral=True)

class ClanVillageView(discord.ui.View):
    def __init__(self, system, data):
        super().__init__(timeout=300)
        self.system, self.data = system, data
        self.add_item(ClanSelect(data))
        self.add_item(VillageSelect(data))
    @discord.ui.button(label="Continuar", style=discord.ButtonStyle.primary)
    async def next(self, interaction, button):
        if interaction.user.id != self.data["user_id"]:
            await interaction.response.send_message("Este formulario no te pertenece.", ephemeral=True)
            return
        if not self.data.get("clan") or not self.data.get("village"):
            await interaction.response.send_message("Selecciona un clan y una aldea antes de continuar.", ephemeral=True)
            return
        await interaction.response.send_message("Selecciona hasta 2 elementos y hasta 2 especialidades:", view=ElementSpecialtyView(self.system, self.data), ephemeral=True)

class ClanSelect(discord.ui.Select):
    def __init__(self, data):
        self.data = data
        super().__init__(placeholder="Elige un clan", min_values=1, max_values=1,
            options=[discord.SelectOption(label=x, value=x) for x in CLANS])
    async def callback(self, interaction):
        self.data["clan"] = self.values[0]
        await interaction.response.send_message(f"Clan seleccionado: **{self.values[0]}**", ephemeral=True)

class VillageSelect(discord.ui.Select):
    def __init__(self, data):
        self.data = data
        super().__init__(placeholder="Elige una aldea", min_values=1, max_values=1,
            options=[discord.SelectOption(label=x, value=x) for x in VILLAGES])
    async def callback(self, interaction):
        self.data["village"] = self.values[0]
        await interaction.response.send_message(f"Aldea seleccionada: **{self.values[0]}**", ephemeral=True)

class ElementSpecialtyView(discord.ui.View):
    def __init__(self, system, data):
        super().__init__(timeout=300)
        self.system, self.data = system, data
        self.add_item(ElementSelect(data))
        self.add_item(SpecialtySelect(data))
    @discord.ui.button(label="Continuar", style=discord.ButtonStyle.primary)
    async def next(self, interaction, button):
        if interaction.user.id != self.data["user_id"]:
            await interaction.response.send_message("Este formulario no te pertenece.", ephemeral=True)
            return
        if not self.data.get("elements") or not self.data.get("specialties"):
            await interaction.response.send_message("Selecciona al menos un elemento y una especialidad.", ephemeral=True)
            return
        await interaction.response.send_modal(ObjectivesModal(self.system, self.data))

class ElementSelect(discord.ui.Select):
    def __init__(self, data):
        self.data = data
        super().__init__(placeholder="Elige hasta 2 elementos", min_values=1, max_values=2,
            options=[discord.SelectOption(label=x, value=x) for x in ELEMENTS])
    async def callback(self, interaction):
        self.data["elements"] = self.values
        await interaction.response.send_message("Elementos: " + ", ".join(self.values), ephemeral=True)

class SpecialtySelect(discord.ui.Select):
    def __init__(self, data):
        self.data = data
        super().__init__(placeholder="Elige hasta 2 especialidades", min_values=1, max_values=2,
            options=[discord.SelectOption(label=x, value=x) for x in SPECIALTIES])
    async def callback(self, interaction):
        self.data["specialties"] = self.values
        await interaction.response.send_message("Especialidades: " + ", ".join(self.values), ephemeral=True)

class ObjectivesModal(discord.ui.Modal, title="Crear OC · Paso 3/4"):
    objectives = discord.ui.TextInput(label="Objetivos del personaje", style=discord.TextStyle.paragraph, max_length=1000)
    def __init__(self, system, data):
        super().__init__()
        self.system, self.data = system, data
    async def on_submit(self, interaction):
        self.data["objectives"] = str(self.objectives).strip()
        await interaction.response.send_modal(HistoryModal(self.system, self.data))

class HistoryModal(discord.ui.Modal, title="Crear OC · Paso 4/4"):
    history = discord.ui.TextInput(label="Historia del personaje", style=discord.TextStyle.paragraph, max_length=1000, placeholder="Escribe el pasado de tu personaje...")
    def __init__(self, system, data):
        super().__init__()
        self.system, self.data = system, data
    async def on_submit(self, interaction):
        self.data["history"] = str(self.history).strip()
        if get_profile(interaction.user.id):
            await interaction.response.send_message("Ya tienes una ficha registrada. Contacta con el staff si necesitas corregirla.", ephemeral=True)
            return
        save_profile(self.data)
        await interaction.response.defer(ephemeral=True, thinking=True)
        await self.system.send_review(interaction, self.data)

class ReviewView(discord.ui.View):
    def __init__(self, system, user_id):
        super().__init__(timeout=None)
        self.system, self.user_id = system, user_id
        self.add_item(ReviewButton(system, user_id, True))
        self.add_item(ReviewButton(system, user_id, False))

class ReviewButton(discord.ui.Button):
    def __init__(self, system, user_id, approve):
        self.system, self.user_id, self.approve_action = system, user_id, approve
        label = "Aceptar ficha" if approve else "Rechazar ficha"
        style = discord.ButtonStyle.success if approve else discord.ButtonStyle.danger
        super().__init__(label=label, style=style, custom_id=f"oc:review:{'yes' if approve else 'no'}:{user_id}")
    async def callback(self, interaction):
        if self.approve_action:
            await self.system.approve(interaction, self.user_id)
        else:
            await self.system.reject(interaction, self.user_id)

class RejectModal(discord.ui.Modal, title="Motivo del rechazo"):
    reason = discord.ui.TextInput(label="Explica el motivo", style=discord.TextStyle.paragraph, max_length=800)
    def __init__(self, system, user_id, message_id):
        super().__init__()
        self.system, self.user_id, self.message_id = system, user_id, message_id
    async def on_submit(self, interaction):
        await self.system.finish_rejection(interaction, self.user_id, str(self.reason).strip(), self.message_id)

class ReviewDoneView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

class DeleteConfirmView(discord.ui.View):
    def __init__(self, system, user_id):
        super().__init__(timeout=60)
        self.system, self.user_id = system, user_id
    @discord.ui.button(label="Confirmar eliminación", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction, button):
        await self.system.confirm_delete(interaction, self.user_id)
    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction, button):
        await interaction.response.edit_message(content="Eliminación cancelada.", view=None)
