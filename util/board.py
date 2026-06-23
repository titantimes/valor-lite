import discord, io, math, os
from PIL import Image, ImageDraw, ImageFont

from core.settings import SettingsManager
from util.embeds import TextTableEmbed, PaginatedTextTable
from util.guilds import guild_tags_from_names
from util.mappings import UI_EMOJI_MAP
from util.requests import fetch_player_busts


FONT_PATHS = [
    "MinecraftRegular.ttf",
    "assets/MinecraftRegular.ttf",
    "assets/fonts/MinecraftRegular.ttf",
]


def _resolve_font_path() -> str:
    base_dir = os.path.dirname(os.path.dirname(__file__))

    for path in FONT_PATHS:
        candidates = [path, os.path.join(base_dir, path)]
        for candidate in candidates:
            if os.path.exists(candidate):
                return candidate
    return FONT_PATHS[0]


def format_board_table_text(
    headers: list[str],
    data: list[list[str]],
    page: int,
    title: str = "Leaderboard",
    show_rank: bool = True,
    rows_per_page: int = 10,
    rank_values: list[int] = None,
) -> str:
    start = page * rows_per_page
    end = start + rows_per_page
    sliced = [list(row) for row in data[start:end]]

    if show_rank:
        for i in range(len(sliced)):
            if rank_values and (i + start) < len(rank_values):
                rank_label = f"{rank_values[i + start]}."
            else:
                rank_label = f"{i + start + 1}."
            sliced[i] = [rank_label] + list(sliced[i])

    column_widths = [max(len(str(item)) for item in col) for col in zip(headers, *(sliced or [headers]))]

    def row_format(row: list[str]) -> str:
        cells = []
        for i, col in enumerate(row):
            value = str(col)
            if i < len(row) - 1:
                cells.append(f"{value:<{column_widths[i]}}")
            else:
                cells.append(value)
        return " ┃ ".join(cells).rstrip()

    header_row = row_format(headers)
    separator = "━╋━".join("━" * column_widths[i] for i in range(len(headers)))
    data_rows = [row_format(row) for row in sliced]

    total_pages = max(1, math.ceil(len(data) / rows_per_page))
    lines = [title, "", header_row, separator, *data_rows, "", f"Page {page + 1}/{total_pages}"]
    return "```isbl\n" + "\n".join(lines) + "\n```"


class BoardView(discord.ui.View):
    def __init__(
        self,
        user_id,
        data: list[tuple[str, int]],
        title: str = "Leaderboard",
        max_page: int = None,
        stat_counter: str = "Value",
        is_guild_board: bool = False,
        use_text_embed: bool = True,
        show_rank: bool = True,
        headers: list[str] = None,
        text_data: list[list[str]] = None,
        text_headers: list[str] = None,
        image_labels: list[str] = None,
        image_value_headers: list[str] = None,
        rank_values: list[int] = None,
    ):
        super().__init__()
        self.user_id = user_id
        self.data = data
        self.max_page = max_page if max_page is not None else math.ceil(len(data) / 10)
        self.title = title
        self.show_rank = show_rank
        if headers:
            self.headers = (["Rank"] + headers) if show_rank else headers
        else:
            self.headers = ["Name", stat_counter]
            if show_rank:
                self.headers.insert(0, "Rank")

        self.stat_counter = stat_counter
        self.is_guild_board = is_guild_board
        self.use_text_embed = use_text_embed
        self.text_data = text_data if text_data is not None else data
        self.image_labels = image_labels
        self.image_value_headers = image_value_headers
        self.rank_values = rank_values
        if text_headers is not None:
            self.text_headers = (["Rank"] + text_headers) if show_rank else text_headers
        else:
            self.text_headers = self.headers

        self.page = 0 

        setting = SettingsManager("user", user_id).get("preferred_leaderboard_output_type")
        self.is_fancy = True if setting == "image" else False


    @discord.ui.button(emoji=UI_EMOJI_MAP["left_arrow"], row=1)
    async def previous(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page -= 1
        if self.page < 0:
            self.page = 0
            await interaction.response.send_message("You are at the first page!", ephemeral=True)
        else:
            await self.update(interaction)


    @discord.ui.button(emoji=UI_EMOJI_MAP["right_arrow"], row=1)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page += 1
        if self.page > self.max_page:
            self.page = self.max_page
            await interaction.response.send_message("You are at the last page!", ephemeral=True)
        else:
            await self.update(interaction)


    @discord.ui.button(emoji=UI_EMOJI_MAP.get("newspaper", "📰"), row=1)
    async def toggle_table_view(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.is_fancy = not self.is_fancy
        await self.update(interaction)


    async def update(self, interaction: discord.Interaction):
        await interaction.response.defer()

        if self.is_fancy:
            board = await build_board(
                self.data,
                self.page,
                is_guild_board=self.is_guild_board,
                show_rank=self.show_rank,
                row_labels=self.image_labels,
                value_headers=self.image_value_headers,
                rank_values=self.rank_values,
            )
            await interaction.edit_original_response(content=None, embed=None, view=self, attachments=[board])
        else:
            if self.use_text_embed:
                start = self.page * 10
                end = start + 10
                sliced = [list(row) for row in self.text_data[start:end]]

                if self.show_rank:
                    for i in range(len(sliced)):
                        if self.rank_values and (i + start) < len(self.rank_values):
                            rank_label = f"{self.rank_values[i + start]}."
                        else:
                            rank_label = f"{i+start+1}."
                        sliced[i] = [rank_label] + list(sliced[i])

                embed = TextTableEmbed(self.text_headers, sliced, title=self.title, color=0x333333)
                await interaction.edit_original_response(content=None, embed=embed, view=self, attachments=[])
            else:
                table = format_board_table_text(
                    self.text_headers,
                    self.text_data,
                    self.page,
                    title=self.title,
                    show_rank=self.show_rank,
                    rank_values=self.rank_values,
                )
                await interaction.edit_original_response(content=table, embed=None, view=self, attachments=[])



class WarcountBoardView(discord.ui.View):
    def __init__(
        self,
        user_id,
        headers,
        rows,
        listed_classes,
        is_guild_board: bool = False,
        timeout=60,
    ):
        super().__init__(timeout=timeout)
        self.listed_classes = listed_classes

        self.page = 0
        self.headers = headers
        self.data = rows
        self.user_id = user_id

        self.is_guild_board = is_guild_board

        setting = SettingsManager("user", user_id).get("preferred_leaderboard_output_type")
        self.is_fancy = True if setting == "image" else False

        self.max_pages = math.ceil(len(rows) / 10)


    async def update_message(self, interaction: discord.Interaction):
        if self.is_fancy:
            await interaction.response.defer()
            content = await build_warcount_board(self.data, self.page, self.listed_classes)
            await interaction.edit_original_response(content="", view=self, attachments=[content])
        else:
            start, end = self.page * 10, (self.page + 1) * 10
            sliced = self.data[start:end]

            widths = [len(h) for h in self.headers]
            fmt = ' ┃ '.join(f'%{w}s' for w in widths)

            lines = [fmt % tuple(self.headers)]
            separator = ''.join('╋' if c == '┃' else '━' for c in lines[0])
            lines.append(separator)

            for row in sliced:
                lines.append(' ┃ '.join(str(cell).ljust(widths[i]) for i, cell in enumerate(row)))
            lines.append(separator)

            content = '```isbl\n' + '\n'.join(lines) + '```'
            await interaction.response.edit_message(content=content, view=self, attachments=[])


    @discord.ui.button(emoji=UI_EMOJI_MAP["left_arrow"])
    async def previous(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page > 0:
            self.page -= 1
            await self.update_message(interaction)
        else:
            await interaction.response.defer()


    @discord.ui.button(emoji=UI_EMOJI_MAP["right_arrow"])
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page < self.max_pages - 1:
            self.page += 1
            await self.update_message(interaction)
        else:
            await interaction.response.defer()



async def build_board(
    data: list[list],
    page: int,
    is_guild_board: bool = False,
    show_rank: bool = True,
    row_labels: list[str] = None,
    value_headers: list[str] = None,
    rank_values: list[int] = None,
) -> discord.File:
    data_list = []
    for i in range(len(data)):
        if rank_values and i < len(rank_values):
            rank = rank_values[i]
        else:
            rank = i + 1
        data_list.append([rank] + list(data[i]))

    value_columns = 1
    if data_list:
        value_columns = max(1, len(data_list[0]) - 2)

    rank_margin = 45
    model_margin = 115 if show_rank else 45
    name_margin = 205 if show_rank else 135

    if value_columns == 1:
        value_positions = [685]
        board_width = 730
    else:
        value_step = 110
        min_left_value_margin = 470
        board_width = max(730, (min_left_value_margin + (value_step * (value_columns - 1))) + 45)
        right_anchor = board_width - 45
        value_positions = [right_anchor - (value_step * (value_columns - 1 - idx)) for idx in range(value_columns)]

    font = ImageFont.truetype(_resolve_font_path(), 20)
    secondary_font = ImageFont.truetype(_resolve_font_path(), 16)
    header_font = ImageFont.truetype(_resolve_font_path(), 24)

    top_padding = 48 if value_headers else 0
    board_height = 695 + top_padding
    board = Image.new("RGBA", (board_width, board_height), (110, 110, 110))

    overlay = Image.open("assets/board_segment.png")
    overlay2 = Image.open("assets/board_segment_dark.png")
    if overlay.width != board_width - 10:
        overlay = overlay.resize((board_width - 10, overlay.height))
        overlay2 = overlay2.resize((board_width - 10, overlay2.height))
    overlay_toggle = True

    draw = ImageDraw.Draw(board)

    names = []
    for i in data_list:
        names.append(i[1])

    if is_guild_board:
        tags = (await guild_tags_from_names(names))[0]
    else:
        await fetch_player_busts(names)

    if value_headers:
        header_color = (242, 242, 242)
        header_bg = (120, 120, 120, 255)

        draw.rounded_rectangle(
            [(6, 6), (board_width - 6, 42)],
            radius=6,
            fill=header_bg,
        )

        draw.text(
            (name_margin, 10),
            "Name",
            font=header_font,
            fill=header_color,
            stroke_width=1,
            stroke_fill=(40, 40, 40),
        )
        for idx, header in enumerate(value_headers):
            if idx >= len(value_positions):
                break
            draw.text(
                (value_positions[idx], 10),
                str(header),
                font=header_font,
                fill=header_color,
                anchor="rt",
                stroke_width=1,
                stroke_fill=(40, 40, 40),
            )

    for i in range(1, 11):
        try:
            stat = data_list[(i - 1) + (page * 10)]
        except IndexError:
            continue

        height = ((i - 1) * 69) + 5 + top_padding

        board.paste(overlay if overlay_toggle else overlay2, (5, height), overlay)
        overlay_toggle = not overlay_toggle

        if is_guild_board:
            tag = tags[names.index(stat[1])]
            try:
                model_img = Image.open(f"assets/icons/guilds/{tag}.png", 'r').convert("RGBA")
            except FileNotFoundError:
                model_img = Image.new("RGBA", (64, 64))
        else:
            try:
                model_img = Image.open(f"/tmp/{stat[1]}_model.png", 'r').convert("RGBA")
            except Exception as e:
                model_img = Image.open(f"assets/unknown_model.png", 'r').convert("RGBA")
                print(f"Error loading image: {e}")

        model_img = model_img.resize((64, 64))
        board.paste(model_img, (model_margin, height), model_img.getchannel("A"))

        if show_rank:
            draw.text((rank_margin, height + 22), "#" + str(stat[0]), font=font)
        draw.text((name_margin, height + 22), str(stat[1]), font=font)
        if row_labels and (i - 1) + (page * 10) < len(row_labels):
            row_label = str(row_labels[(i - 1) + (page * 10)])
            draw.text((max(name_margin + 220, value_positions[0] - 95), height + 22), row_label, font=secondary_font)

        values = stat[2:]
        for idx, value in enumerate(values):
            if idx >= len(value_positions):
                break
            draw.text((value_positions[idx], height + 22), str(value), font=font, anchor="rt")

    with io.BytesIO() as img_binary:
        board.save(img_binary, 'PNG')
        img_binary.seek(0)
        file = discord.File(fp=img_binary, filename="board.png")

    return file


async def build_warcount_board(
    data: list[tuple],
    page: int,
    listed_classes: list[str],
    is_guild_board: bool = False,
) -> discord.File:
    start = page * 10
    end = start + 10
    sliced = data[start:end]

    img = Image.open("assets/warcount_template.png")
    draw = ImageDraw.Draw(img)

    name_fontsize = 20
    text_fontsize = 16
    total_fontsize = 18

    font_path = _resolve_font_path()
    name_font = ImageFont.truetype(font_path, name_fontsize)
    text_font = ImageFont.truetype(font_path, text_fontsize)
    total_font = ImageFont.truetype(font_path, total_fontsize)

    names = []
    for i in sliced:
        names.append(i[1])

    if is_guild_board:
        tags = (await guild_tags_from_names(names))[0]
    else:
        await fetch_player_busts(names)

    i = 1
    for row in sliced:
        y = ((57 * (i / 2)) + (59 * (i / 2))) + 27

        draw.text((62, y), f"{row[0]}.", "white", total_font, anchor="rm")
        draw.text((153, y), row[1], "white", name_font, anchor="lm")

        if is_guild_board:
            tag = tags[names.index(row[1])]
            try:
                model_img = Image.open(f"assets/icons/guilds/{tag}.png", 'r').convert("RGBA")
                model_img = model_img.crop(model_img.getbbox())
            except FileNotFoundError:
                model_img = Image.new("RGBA", (54, 54))
        else:
            try:
                model_img = Image.open(f"/tmp/{row[1]}_model.png", 'r').convert("RGBA")
            except Exception as e:
                model_img = Image.open(f"assets/unknown_model.png", 'r').convert("RGBA")
                print(f"Error loading image: {e}")

        model_img = model_img.resize((54, 54))
        img.paste(model_img, (84, int(y) - 29), model_img.getchannel("A"))

        draw.text((445, y), row[2], "white", total_font, anchor="mm")

        x = 0  # Offset for class warcount columns

        if "ARCHER" in listed_classes:
            draw.text((532, y), str(row[3 + x]), "white", text_font, anchor="mm")
            x += 1
        if "WARRIOR" in listed_classes:
            draw.text((593, y), str(row[3 + x]), "white", text_font, anchor="mm")
            x += 1
        if "MAGE" in listed_classes:
            draw.text((658, y), str(row[3 + x]), "white", text_font, anchor="mm")
            x += 1
        if "ASSASSIN" in listed_classes:
            draw.text((718, y), str(row[3 + x]), "white", text_font, anchor="mm")
            x += 1
        if "SHAMAN" in listed_classes:
            draw.text((780, y), str(row[3 + x]), "white", text_font, anchor="mm")
            x += 1

        draw.text((827, y), str(row[3 + x]), "white", total_font, anchor="lm")

        i += 1

    img_binary = io.BytesIO()
    img.save(img_binary, 'PNG')
    img_binary.seek(0)

    return discord.File(fp=img_binary, filename="board.png")
