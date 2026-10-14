import discord, logging

from discord import app_commands
from discord.app_commands import Choice, checks
from discord.ext import commands

from core.settings import SettingsManager, SETTINGS_SCHEMAS
from util.embeds import ErrorEmbed, InfoEmbed


class ValueModal(discord.ui.Modal, title="Set Setting Value"):
    def __init__(
        self,
        user: discord.User,
        manager: SettingsManager,
        key: str,
        target_id: int,
        scope: str,
        interaction: discord.Interaction,
        field_label: str = "Value",
        is_list: bool = False,
        list_add_or_remove: str = None,
    ):
        super().__init__()
        self.user = user
        self.manager = manager
        self.key = key
        self.target_id = target_id
        self.scope = scope
        self.original_interaction = interaction
        self.is_list = is_list
        self.list_add_or_remove = list_add_or_remove
        self.input = discord.ui.TextInput(label=field_label, placeholder="Enter a value")
        self.add_item(self.input)

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message(
                "You can't interact with this modal.", ephemeral=True
            )

        try:
            if self.is_list:
                l = self.manager.get(self.key)
                if self.list_add_or_remove == "remove":
                    l.remove(self.input.value)
                else:
                    l.append(self.input.value)
                self.manager.set(self.key, l)
            else:
                self.manager.set(self.key, self.input.value)

            updated_embed = await construct_embed(self.key, self.target_id, self.scope)
            await self.original_interaction.edit_original_response(
                embed=updated_embed,
                view=SettingsView(self.original_interaction, self.key, self.scope),
            )

            await interaction.response.send_message("Setting updated.", ephemeral=True)
        except ValueError as e:
            if self.is_list:
                embed = ErrorEmbed(f"Value '{self.input.value}' is not found in the list")
            else:
                embed = ErrorEmbed(str(e))
            await interaction.response.send_message(embed=embed, ephemeral=True)



class ChoiceDropdown(discord.ui.Select):
    def __init__(
        self,
        user: discord.User,
        manager: SettingsManager,
        key: str,
        target_id: int,
        scope: str,
        choices: list[str],
        interaction: discord.Interaction,
    ):
        self.user = user
        self.manager = manager
        self.key = key
        self.target_id = target_id
        self.scope = scope
        self.original_interaction = interaction

        options = [discord.SelectOption(label=val, value=val) for val in choices]
        super().__init__(
            placeholder="Choose a value", options=options, min_values=1, max_values=1
        )

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message(
                "You can't interact with this menu.", ephemeral=True
            )

        try:
            self.manager.set(self.key, self.values[0])
            updated_embed = await construct_embed(self.key, self.target_id, self.scope)
            await self.original_interaction.edit_original_response(
                embed=updated_embed,
                view=SettingsView(self.original_interaction, self.key, self.scope),
            )
            await interaction.response.edit_message(embed=InfoEmbed("Setting updated."), view=None)
        except ValueError as e:
            await interaction.response.send_message(embed=ErrorEmbed(str(e)), ephemeral=True)



class ChoiceView(discord.ui.View):
    def __init__(
        self,
        user: discord.User,
        key: str,
        target_id: int,
        scope: str,
        interaction: discord.Interaction,
    ):
        super().__init__(timeout=60)
        self.user = user
        self.key = key
        self.target_id = target_id
        self.scope = scope
        self.manager = SettingsManager(self.scope, target_id)
        schema = SETTINGS_SCHEMAS[self.scope][key]
        self.add_item(
            ChoiceDropdown(
                self.user,
                SettingsManager(self.scope, self.target_id),
                self.key,
                self.target_id,
                self.scope,
                schema["choices"],
                interaction,
            )
        )

class ConfirmResetView(discord.ui.View):
    def __init__(
        self,
        user: discord.User,
        manager: SettingsManager,
        key: str,
        target_id: int,
        scope: str,
        original_interaction: discord.Interaction,
    ):
        super().__init__(timeout=30)
        self.user = user
        self.manager = manager
        self.key = key
        self.target_id = target_id
        self.scope = scope
        self.original_interaction = original_interaction

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message(
                "You can't interact with this.", ephemeral=True
            )

        self.manager.reset(self.key)
        updated_embed = await construct_embed(self.key, self.target_id, self.scope)
        await self.original_interaction.edit_original_response(
            embed=updated_embed, view=SettingsView(self.original_interaction, self.key, self.scope)
        )
        await interaction.response.edit_message(
            embed=InfoEmbed("Setting reset to default."), view=None
        )

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message(
                "You can't interact with this.", ephemeral=True
            )
        await interaction.response.edit_message(embed=InfoEmbed("Reset cancelled."), view=None)



class SettingsView(discord.ui.View):
    def __init__(self, interaction: discord.Interaction, key: str, scope: str):
        super().__init__(timeout=60)
        self.user = interaction.user
        self.key = key
        self.target_id = interaction.guild.id if scope == "guild" else interaction.user.id
        self.scope = scope
        self.manager = SettingsManager(self.scope, self.target_id)
        self.interaction = interaction
        schema = SETTINGS_SCHEMAS[self.scope][key]

        type_ = schema["type"]
        if type_ in ["text", "number"]:
            self.add_item(SetButton(self.user, key, self.target_id, scope, interaction, self.manager))
        elif type_ == "bool":
            self.add_item(BoolButton(self.user, key, self.target_id, scope, interaction, self.manager))
        elif type_ == "list":
            self.add_item(AddButton(self.user, key, self.target_id, scope, interaction, self.manager))
            self.add_item(RemoveButton(self.user, key, self.target_id, scope, interaction, self.manager))

        self.add_item(ResetButton(self.user, key, self.target_id, scope, interaction, self.manager))



class SetButton(discord.ui.Button):
    def __init__(self, user, key, target_id, scope, interaction, manager):
        super().__init__(label="Set Value", style=discord.ButtonStyle.primary)
        self.user = user
        self.key = key
        self.target_id = target_id
        self.scope = scope
        self.original_interaction = interaction
        self.manager = manager

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message(
                "Only the command user can press this button.", ephemeral=True
            )

        schema = SETTINGS_SCHEMAS[self.scope][self.key]
        if "choices" in schema:
            await interaction.response.send_message(
                view=ChoiceView(
                    self.user, self.key, self.target_id, self.scope, self.original_interaction
                ),
                ephemeral=True,
            )
        else:
            await interaction.response.send_modal(
                ValueModal(
                    self.user, self.manager, self.key, self.target_id, self.scope, self.original_interaction
                )
            )



class BoolButton(discord.ui.Button):
    def __init__(self, user, key, target_id, scope, interaction, manager):
        super().__init__(label="Toggle Setting", style=discord.ButtonStyle.primary)
        self.user = user
        self.key = key
        self.target_id = target_id
        self.scope = scope
        self.original_interaction = interaction
        self.manager = manager

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message(
                "Only the command user can press this button.", ephemeral=True
            )

        b = not self.manager.get(self.key)
        self.manager.set(self.key, b)
        updated_embed = await construct_embed(self.key, self.target_id, self.scope)
        await self.original_interaction.edit_original_response(
            embed=updated_embed, view=SettingsView(self.original_interaction, self.key, self.scope)
        )

        await interaction.response.send_message("Setting updated.", ephemeral=True)



class AddButton(discord.ui.Button):
    def __init__(self, user, key, target_id, scope, interaction, manager):
        super().__init__(label="Add Value", style=discord.ButtonStyle.success)
        self.user = user
        self.key = key
        self.target_id = target_id
        self.scope = scope
        self.original_interaction = interaction
        self.manager = manager

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message(
                "Only the command user can press this button.", ephemeral=True
            )
        await interaction.response.send_modal(
            ValueModal(
                self.user,
                self.manager,
                self.key,
                self.target_id,
                self.scope,
                self.original_interaction,
                field_label="Value to add",
                is_list=True,
            )
        )



class RemoveButton(discord.ui.Button):
    def __init__(self, user, key, target_id, scope, interaction, manager):
        super().__init__(label="Remove Value", style=discord.ButtonStyle.danger)
        self.user = user
        self.key = key
        self.target_id = target_id
        self.scope = scope
        self.original_interaction = interaction
        self.manager = manager

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message(
                "Only the command user can press this button.", ephemeral=True
            )
        await interaction.response.send_modal(
            ValueModal(
                self.user,
                self.manager,
                self.key,
                self.target_id,
                self.scope,
                self.original_interaction,
                field_label="Value to remove",
                is_list=True,
                list_add_or_remove="remove",
            )
        )



class ResetButton(discord.ui.Button):
    def __init__(self, user, key, target_id, scope, interaction, manager):
        super().__init__(label="Reset to Default", style=discord.ButtonStyle.secondary)
        self.user = user
        self.key = key
        self.target_id = target_id
        self.scope = scope
        self.original_interaction = interaction
        self.manager = manager

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message(
                "Only the command user can press this button.", ephemeral=True
            )
        await interaction.response.send_message(
            embed=InfoEmbed("Are you sure you want to reset this setting to default?"),
            view=ConfirmResetView(
                self.user, self.manager, self.key, self.target_id, self.scope, self.original_interaction
            ),
            ephemeral=True,
        )



async def construct_embed(key: str, user_id: str, scope: str) -> discord.Embed:
    schema = SETTINGS_SCHEMAS[scope][key]
    manager = SettingsManager(scope, user_id)
    current = manager.get(key)

    key_label = key.replace("_", " ").capitalize()
    embed = discord.Embed(
        title=f"{scope.capitalize()} Setting: {key_label}",
        description=schema.get("description", ""),
    )

    embed.add_field(name="Type", value=schema["type"].capitalize(), inline=True)

    if "choices" in schema:
        embed.add_field(name="Choices", value=", ".join(map(str, schema["choices"])), inline=True)

    embed.add_field(
        name="Current Value",
        value=(str(current).replace("'", "") if current else "None"),
        inline=False,
    )
    embed.add_field(
        name="Default Value",
        value=(str(schema.get("default")).replace("'", "").capitalize() if schema.get("default") else "None"),
        inline=False,
    )

    return embed



class SettingsCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="user_settings", description="View and edit your user settings")
    @app_commands.describe(setting="The setting you want to manage")
    async def user_settings(self, interaction: discord.Interaction, setting: str):
        schema = SETTINGS_SCHEMAS["user"].get(setting)
        if not schema:
            return await interaction.response.send_message("Invalid setting selected.", ephemeral=True)

        embed = await construct_embed(setting, interaction.user.id, "user")
        await interaction.response.send_message(
            embed=embed,
            view=SettingsView(interaction, setting, "user"),
        )


    @app_commands.command(name="guild_settings", description="View and edit this server's settings")
    @checks.has_permissions(administrator=True)
    @app_commands.describe(setting="The setting you want to manage")
    @app_commands.guild_only() # Make sure this command is only ran inside servers due to its reliance on interaction.guild.id
    async def guild_settings(self, interaction: discord.Interaction, setting: str):
        schema = SETTINGS_SCHEMAS["guild"].get(setting)
        if not schema:
            return await interaction.response.send_message("Invalid setting selected.", ephemeral=True)

        embed = await construct_embed(setting, interaction.guild.id, "guild")
        await interaction.response.send_message(
            embed=embed,
            view=SettingsView(interaction, setting, "guild"),
        )


    @user_settings.autocomplete("setting")
    async def user_settings_autocomplete(self, interaction: discord.Interaction, current: str) -> list[Choice[str]]:
        autocomplete = []
        for setting in SETTINGS_SCHEMAS["user"].keys():
            name = setting.replace("_", " ").capitalize()
            autocomplete.append(Choice(name=name, value=setting))
        return autocomplete


    @guild_settings.autocomplete("setting")
    async def guild_settings_autocomplete(self, interaction: discord.Interaction, current: str) -> list[Choice[str]]:
        autocomplete = []
        for setting in SETTINGS_SCHEMAS["guild"].keys():
            name = setting.replace("_", " ").capitalize()
            autocomplete.append(Choice(name=name, value=setting))
        return autocomplete

async def setup(bot: commands.Bot):
    await bot.add_cog(SettingsCommands(bot))
