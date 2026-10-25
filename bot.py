import os
import discord
from discord.ext import commands
from fichas import FichasSystem

TOKEN = os.getenv("TOKEN") or os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise RuntimeError("Falta la variable TOKEN (o DISCORD_TOKEN) en Railway.")

intents = discord.Intents.default()
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
system = FichasSystem(bot)

@bot.event
async def on_ready():
    await system.setup()
    try:
        synced = await bot.tree.sync()
        print(f"Conectado como {bot.user}. Comandos sincronizados: {len(synced)}")
    except Exception as e:
        print(f"Error sincronizando comandos: {e}")
    print("Bot de Fichas OC listo.")

@bot.event
async def on_member_update(before: discord.Member, after: discord.Member):
    await system.handle_member_update(before, after)

@bot.event
async def on_member_join(member: discord.Member):
    await system.refresh_panels(member.guild)

@bot.event
async def on_member_remove(member: discord.Member):
    await system.refresh_panels(member.guild)

@bot.tree.command(name="publicar_fichas", description="Publica el panel para crear y consultar fichas OC.")
async def publicar_fichas(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.manage_guild:
        await interaction.response.send_message("Necesitas el permiso Gestionar servidor.", ephemeral=True)
        return
    await system.publish_main_panel(interaction)

@bot.tree.command(name="cupos", description="Muestra los cupos y miembros de cada clan.")
async def cupos(interaction: discord.Interaction):
    await system.show_clan_cupos(interaction)

@bot.tree.command(name="aldeas", description="Muestra los miembros de Konohagakure y Sunagakure.")
async def aldeas(interaction: discord.Interaction):
    await system.show_village_cupos(interaction)

@bot.tree.command(name="actualizar_cupos", description="Actualiza los paneles de cupos.")
async def actualizar_cupos(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.manage_guild:
        await interaction.response.send_message("Necesitas el permiso Gestionar servidor.", ephemeral=True)
        return
    await system.refresh_panels(interaction.guild)
    await interaction.response.send_message("✅ Cupos actualizados.", ephemeral=True)

from discord import app_commands
# Decorator placeholder is replaced below to keep command registration straightforward.
bot.run(TOKEN)
