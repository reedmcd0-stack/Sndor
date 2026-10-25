BOT DE FICHAS OC — INSTALACIÓN

1. Sube estos archivos a un repositorio de GitHub.
2. En Railway, crea un proyecto y despliega el repositorio.
3. En Variables de Railway, añade TOKEN con el token de tu bot.
4. En Discord Developer Portal > Bot:
   - Activa SERVER MEMBERS INTENT.
5. Invita el bot con los permisos:
   - Manage Roles
   - Send Messages
   - Embed Links
   - Read Message History
   - Use Application Commands
6. IMPORTANTE: coloca el rol del bot por encima de los roles de clanes,
   aldeas, elementos, especialidades y el rol de eliminación.
7. En el servidor, usa /publicar_fichas en el canal donde quieres el panel.
8. Usa /cupos para ver miembros de los clanes y /aldeas para ver miembros de aldeas.

NOTAS:
- El canal de revisión está configurado como 1543580022399311903.
- El rol autorizado para eliminar fichas es 1563912834616655892.
- Cada clan tiene un límite de 5.
- El límite de aldea está fijado en 100 en fichas.py (VILLAGE_LIMIT); puedes cambiarlo.
- Para que SQLite persista en Railway, monta un Volume y establece DATA_DIR al punto de montaje.
  Por ejemplo, si el volumen está montado en /data, define DATA_DIR=/data.
- Los cupos de /cupos y /aldeas consultan los roles actuales de Discord.
