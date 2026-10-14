import discord, io, math, os, tempfile, time
from PIL import Image, ImageDraw, ImageFont

from core.settings import SettingsManager
from util.embeds import TextTableEmbed, PaginatedTextTable
from util.guilds import guild_tags_from_names
from util.mappings import UI_EMOJI_MAP
from util.requests import fetch_player_busts, request


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


def assetp(filename: str) -> str:
    base_dir = os.path.dirname(os.path.dirname(__file__))
    candidates = [
        filename,
        os.path.join(base_dir, filename),
        os.path.join("assets", filename),
        os.path.join(base_dir, "assets", filename),
    ]
    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate
    return filename


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
        await interaction.response.defer()
        if self.is_fancy:
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
            await interaction.edit_original_response(content=content, view=self, attachments=[])


    @discord.ui.button(emoji=UI_EMOJI_MAP["left_arrow"])
    async def previous(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page > 0:
            self.page -= 1
            await self.update_message(interaction)
        else:
            await interaction.response.send_message("You are at the first page!", ephemeral=True)


    @discord.ui.button(emoji=UI_EMOJI_MAP["right_arrow"])
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page < self.max_pages - 1:
            self.page += 1
            await self.update_message(interaction)
        else:
            await interaction.response.send_message("You are at the last page!", ephemeral=True)

    @discord.ui.button(emoji=UI_EMOJI_MAP.get("newspaper", "📰"))
    async def toggle_table_view(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.is_fancy = not self.is_fancy
        await self.update_message(interaction)



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

async def get_player_avatar(username: str, uuid: str = None) -> Image.Image:
    tmp_path = os.path.join(tempfile.gettempdir(), f"{username}_model.png")
    legacy_tmp = f"/tmp/{username}_model.png"

    for path in (tmp_path, legacy_tmp):
        if os.path.exists(path) and time.time() - os.path.getmtime(path) < 86400:
            try:
                return Image.open(path).convert("RGBA")
            except Exception:
                pass

    target = uuid if uuid else username
    try:
        headers = {"User-Agent": "valor-bot/1.0"}
        model_data = await request(
            f"https://visage.surgeplay.com/bust/{target}.png",
            headers=headers,
            return_type="image",
        )
        if model_data:
            with open(tmp_path, "wb") as f:
                f.write(model_data)
            return Image.open(tmp_path).convert("RGBA")
    except Exception:
        pass

    unknown_path = assetp("unknown_model.png")
    if os.path.exists(unknown_path):
        try:
            return Image.open(unknown_path).convert("RGBA")
        except Exception:
            pass

    return Image.new("RGBA", (64, 64), (60, 60, 65, 255))


async def build_history_board(
    username: str,
    uuid: str,
    data: list[list[str]],
    page: int,
    rows_per_page: int = 10,
    total_guilds: int = None,
) -> discord.File:
    start = page * rows_per_page
    end = start + rows_per_page
    sliced = data[start:end]

    total_count = total_guilds if total_guilds is not None else len(data)
    total_pages = max(1, math.ceil(len(data) / rows_per_page))

    board_width = 820
    header_h = 75
    col_header_h = 32
    row_spacing = 68
    footer_h = 24
    rows_count = max(1, len(sliced))
    board_height = 8 + header_h + 10 + col_header_h + 8 + (rows_count * row_spacing) + footer_h + 8
    board = Image.new("RGBA", (board_width, board_height), (32, 34, 38))
    draw = ImageDraw.Draw(board)

    font_path = _resolve_font_path()
    title_font = ImageFont.truetype(font_path, 24)
    header_font = ImageFont.truetype(font_path, 17)
    font = ImageFont.truetype(font_path, 18)
    font_small = ImageFont.truetype(font_path, 15)
    font_sub = ImageFont.truetype(font_path, 14)
    font_tiny = ImageFont.truetype(font_path, 12)

    draw.rounded_rectangle(
        [(8, 8), (board_width - 8, 8 + header_h)],
        radius=8,
        fill=(42, 45, 52),
        outline=(58, 62, 72),
        width=1,
    )

    avatar_img = await get_player_avatar(username, uuid)
    avatar_img = avatar_img.resize((54, 54))
    mask = avatar_img.getchannel("A") if "A" in avatar_img.getbands() else None
    board.paste(avatar_img, (18, 18), mask)

    draw.text((84, 20), username, font=title_font, fill=(255, 255, 255))
    draw.text(
        (86, 48),
        f"Guild Membership Timeline  •  {total_count} Guilds Recorded",
        font=font_sub,
        fill=(160, 168, 185),
    )
    draw.text(
        (board_width - 24, 34),
        f"Page {page + 1}/{total_pages}",
        font=header_font,
        fill=(200, 205, 215),
        anchor="ra",
    )

    col_y = 8 + header_h + 8
    draw.rounded_rectangle(
        [(8, col_y), (board_width - 8, col_y + col_header_h)],
        radius=5,
        fill=(45, 48, 56),
    )
    draw.text((78, col_y + 8), "GUILD", font=header_font, fill=(210, 215, 225))
    draw.text((360, col_y + 8), "RANK", font=header_font, fill=(210, 215, 225))
    draw.text((515, col_y + 8), "JOINED", font=header_font, fill=(210, 215, 225))
    draw.text((675, col_y + 8), "LEFT", font=header_font, fill=(210, 215, 225))

    seg_path = assetp("board_segment.png")
    seg_dark_path = assetp("board_segment_dark.png")
    overlay = Image.open(seg_path)
    overlay2 = Image.open(seg_dark_path)
    ov1 = overlay.resize((board_width - 16, 64))
    ov2 = overlay2.resize((board_width - 16, 64))

    fallback_icon_path = assetp("icons/gamemodes/guild.png")
    if os.path.exists(fallback_icon_path):
        fallback_icon = Image.open(fallback_icon_path).convert("RGBA").resize((46, 46))
    else:
        fallback_icon = Image.new("RGBA", (46, 46), (70, 75, 85, 255))

    guild_names = [row[0] for row in sliced]
    tags, _ = await guild_tags_from_names(guild_names)
    rank_colors = {
        "owner": (255, 180, 0),
        "leader": (255, 180, 0),
        "chief": (255, 95, 95),
        "strategist": (85, 225, 255),
        "captain": (195, 115, 255),
        "recruiter": (100, 240, 120),
        "recruit": (215, 215, 225),
    }

    y_start = col_y + col_header_h + 6
    for idx, row in enumerate(sliced):
        guild = str(row[0])
        rank = str(row[1])
        joined = str(row[2])
        left = str(row[3])
        tag = tags[idx] if idx < len(tags) else None
        curr_y = y_start + (idx * row_spacing)
        seg = ov1 if idx % 2 == 0 else ov2
        board.paste(seg, (8, curr_y), seg)

        g_icon = fallback_icon
        if tag:
            icon_file = assetp(f"icons/guilds/{tag}.png")
            if os.path.exists(icon_file):
                try:
                    g_icon = Image.open(icon_file).convert("RGBA").resize((46, 46))
                except Exception:
                    g_icon = fallback_icon

        board.paste(g_icon, (20, curr_y + 9), g_icon.getchannel("A") if "A" in g_icon.getbands() else None)
        g_font = font if len(guild) <= 22 else font_small
        draw.text((78, curr_y + 22), guild, font=g_font, fill=(255, 255, 255))
        r_color = rank_colors.get(rank.lower(), (200, 200, 200))
        draw.text((360, curr_y + 22), rank, font=font, fill=r_color)
        draw.text((515, curr_y + 22), joined, font=font, fill=(215, 220, 230))
        l_color = (100, 245, 130) if left.lower() == "current" else (215, 220, 230)
        draw.text((675, curr_y + 22), left, font=font, fill=l_color)

    footer_y = y_start + (rows_count * row_spacing) + 4
    draw.text(
        (12, footer_y),
        "* Membership tracking updated 29 Sep 2026. Most entries at this date will be prior to it.",
        font=font_tiny,
        fill=(130, 136, 150),
    )

    with io.BytesIO() as img_binary:
        board.save(img_binary, "PNG")
        img_binary.seek(0)
        return discord.File(fp=img_binary, filename="history_board.png")


class HistoryBoardView(discord.ui.View):
    def __init__(
        self,
        user_id: int,
        username: str,
        uuid: str,
        rows: list[list[str]],
        headers: list[str] = None,
        timeout: int = 120,
    ):
        super().__init__(timeout=timeout)
        self.user_id = user_id
        self.username = username
        self.uuid = uuid
        self.data = rows
        self.headers = headers or ["Guild", "Rank", "Joined", "Left"]
        self.page = 0
        self.max_pages = max(1, math.ceil(len(rows) / 10))

        setting = SettingsManager("user", user_id).get("preferred_leaderboard_output_type")
        self.is_fancy = True if setting == "image" else False

    @discord.ui.button(emoji=UI_EMOJI_MAP["left_arrow"], row=1)
    async def previous(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page > 0:
            self.page -= 1
            await self.update(interaction)
        else:
            await interaction.response.send_message("You are at the first page!", ephemeral=True)

    @discord.ui.button(emoji=UI_EMOJI_MAP["right_arrow"], row=1)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page < self.max_pages - 1:
            self.page += 1
            await self.update(interaction)
        else:
            await interaction.response.send_message("You are at the last page!", ephemeral=True)

    @discord.ui.button(emoji=UI_EMOJI_MAP.get("newspaper", "📰"), row=1)
    async def toggle_table_view(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.is_fancy = not self.is_fancy
        await self.update(interaction)

    async def update(self, interaction: discord.Interaction):
        await interaction.response.defer()

        if self.is_fancy:
            board = await build_history_board(self.username, self.uuid, self.data, self.page)
            await interaction.edit_original_response(content=None, embed=None, view=self, attachments=[board])
        else:
            table = format_board_table_text(
                self.headers,
                self.data,
                self.page,
                title=f"Guild History of {self.username}",
                show_rank=False,
            )
            await interaction.edit_original_response(content=table, embed=None, view=self, attachments=[])
