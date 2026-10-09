import discord
from discord import app_commands
from discord.ext import commands
import aiosqlite
import asyncio
import os
from flask import Flask
from threading import Thread

app = Flask('')
@app.route('/')
def home(): return "OK"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

bot = commands.Bot(command_prefix="!", intents=discord.Intents.all())
DB_NAME = "shop_helper.db"

# ⚠️ 请在这里换上你的两个频道 ID
STATUS_CHANNEL_ID = 1558161595996315779
MEMBER_COUNT_CHANNEL_ID = 876543210987654321  

async def update_member_count(guild):
    ch = guild.get_channel(MEMBER_COUNT_CHANNEL_ID)
    if ch:
        try: await ch.edit(name=f"🔒 成员总数: {guild.member_count}")
        except: pass

@bot.event
async def on_ready():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("CREATE TABLE IF NOT EXISTS config (guild_id TEXT PRIMARY KEY, welcome_channel_id TEXT, review_channel_id TEXT)")
        await db.commit()
    print("Online")
    try: await bot.tree.sync()
    except: pass

@bot.event
async def on_member_join(member: discord.Member):
    await update_member_count(member.guild)
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT welcome_channel_id FROM config WHERE guild_id = ?", (str(member.guild.id),)) as cur:
            row = await cur.fetchone()
            if row and row[0]:
                ch = member.guild.get_channel(int(row[0]))
                if ch:
                    embed = discord.Embed(title="🎉 欢迎新成员！", description=f"欢迎 {member.mention} 加入服务器！", color=discord.Color.green())
                    embed.set_thumbnail(url=member.display_avatar.url)
                    await ch.send(content=member.mention, embed=embed)

@bot.event
async def on_member_remove(member: discord.Member):
    await update_member_count(member.guild)

class ShopDropdown(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="游戏代充", description="手游、端游代充值业务", emoji="🎮"),
            discord.SelectOption(label="网页代购", description="海外网站、软件代购服务", emoji="🌐"),
            discord.SelectOption(label="客服咨询", description="寻求人工客服沟通", emoji="👩‍💻"),
        ]
        super().__init__(placeholder="❓ 请选择您需要办理的业务分类", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(OrderModal(self.values[0]))

class OrderModal(discord.ui.Modal, title="📝 填写服务单"):
    item = discord.ui.TextInput(label="代充的物品 / 代购的商品名称", placeholder="例如: 某某游戏点券...")
    remarks = discord.ui.TextInput(label="具体账号信息 / 商品链接与要求", style=discord.TextStyle.long, placeholder="请在此填写账号、密码或网址...")

    def __init__(self, category):
        super().__init__()
        self.category = category

    async def on_submit(self, interaction: discord.Interaction):
        guild = interaction.guild
        buyer = interaction.user
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            buyer: discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True)
        }
        ch = await guild.create_text_channel(name=f"📩-{buyer.name}", overwrites=overwrites)
        await interaction.response.send_message(f"✅ 工单已创建！{ch.mention}", ephemeral=True)
        embed = discord.Embed(title="📩 专属工单服务中心", description="管理员稍后会在此为您报价，请耐心等待。", color=discord.Color.blue())
        embed.add_field(name="🗂️ 业务分类", value=self.category, inline=True)
        embed.add_field(name="📦 目标商品", value=self.item.value, inline=True)
        embed.add_field(name="💬 详细账号要求", value=f"```\n{self.remarks.value}\n```", inline=False)
        await ch.send(embed=embed, view=OrderManagementView(buyer.id, self.item.value))

class ReviewModal(discord.ui.Modal, title="⭐️ 留下您的开店好评"):
    rating = discord.ui.TextInput(label="您愿意给本次服务打几星？(1 到 5)", placeholder="5", min_length=1, max_length=1)
    comments = discord.ui.TextInput(label="您的评语与心得", style=discord.TextStyle.long, placeholder="写下您的交易体验吧...", required=True)

    def __init__(self, item, ch_del):
        super().__init__()
        self.item = item
        self.ch_del = ch_del

    async def on_submit(self, interaction: discord.Interaction):
        guild = interaction.guild
        buyer = interaction.user
        stars = "⭐" * int(self.rating.value) if self.rating.value.isdigit() and 1 <= int(self.rating.value) <= 5 else "⭐⭐⭐⭐⭐"
        async with aiosqlite.connect(DB_NAME) as db:
            async with db.execute("SELECT review_channel_id FROM config WHERE guild_id = ?", (str(guild.id),)) as cur:
                row = await cur.fetchone()
                if row and row[0]:
                    r_ch = guild.get_channel(int(row[0]))
                    if r_ch:
                        embed = discord.Embed(title="🛍️ 来自买家的真实好评", color=discord.Color.gold())
                        embed.add_field(name="👤 满意买家", value=buyer.mention, inline=True)
                        embed.add_field(name="📦 交易商品", value=self.item, inline=True)
                        embed.add_field(name="✨ 评分等级", value=stars, inline=False)
                        embed.add_field(name="💬 真实评语", value=f"```\n{self.comments.value}\n```", inline=False)
                        embed.set_thumbnail(url=buyer.display_avatar.url)
                        await r_ch.send(embed=embed)
        await interaction.response.send_message("💖 感谢您的评价！工单将在 3 秒后删除。")
        await asyncio.sleep(3)
        await self.ch_del.delete()

class OrderManagementView(discord.ui.View):
    def __init__(self, buyer_id, item):
        super().__init__(timeout=None)
        self.buyer_id = buyer_id
        self.item = item

    @discord.ui.button(label="🔒 管理员：完成交易并邀请评价", style=discord.ButtonStyle.danger, custom_id="close_order_with_review")
    async def close_order(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ 只有管理员可以结单！", ephemeral=True)
            return
        buyer = interaction.guild.get_member(self.buyer_id)
        if buyer:
            class ReviewTriggerView(discord.ui.View):
                def __init__(self, item, channel):
                    super().__init__(timeout=60)
                    self.item = item
                    self.channel = channel
                @discord.ui.button(label="⭐ 点击为本次交易打分留评", style=discord.ButtonStyle.primary)
                async def click_review(self, inter: discord.Interaction, btn: discord.ui.Button):
                    if inter.user.id != buyer.id:
                        await inter.response.send_message("❌ 只有买家本人可以评价！", ephemeral=True)
                        return
                    await inter.response.send_modal(ReviewModal(self.item, self.channel))
            await interaction.response.send_message(content=f"🔔 {buyer.mention} 订单已处理完毕！请点击下方按钮打个分，提交后频道会自动销毁：", view=ReviewTriggerView(self.item, interaction.channel))
        else:
            await interaction.channel.delete()

@bot.tree.command(name="shop", description="🛍️ 呼出客服中心")
async def shop(interaction: discord.Interaction):
    v = discord.ui.View(timeout=None)
    v.add_item(ShopDropdown())
    embed = discord.Embed(title="📥 客服中心", description="欢迎光临！请在下方下拉菜单中选择您需要办理的业务通道。", color=discord.Color.from_rgb(47, 49, 54))
    await interaction.response.send_message(embed=embed, view=v)

@bot.tree.command(name="status", description="🛠️ [管理员] 一键切换店铺营业状态招牌")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.choices(state=[
    app_commands.Choice(name="🟢 正常营业 (OPEN)", value="OPEN"),
    app_commands.Choice(name="🔴 暂停营业 (CLOSE)", value="CLOSE")
])
async def set_shop_status(interaction: discord.Interaction, state: app_commands.Choice[str]):
    ch = interaction.guild.get_channel(STATUS_CHANNEL_ID)
    if not ch:
        await interaction.response.send_message("❌ 未找到指定的招牌频道！", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    if state.value == "OPEN":
        await ch.edit(name="🔒 JT SHOP 🟢OPEN")
        await interaction.followup.send("✅ 招牌已成功修改为 OPEN！")
    else:
        await ch.edit(name="🔒 JT SHOP 🔴CLOSE")
        await interaction.followup.send("✅ 招牌已成功修改为 CLOSE！")

@bot.tree.command(name="set_welcome", description="🛠️ 设置新成员的欢迎通知频道")
@app_commands.checks.has_permissions(administrator=True)
async def set_welcome(interaction: discord.Interaction, channel: discord.TextChannel):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT INTO config (guild_id, welcome_channel_id) VALUES (?, ?) ON CONFLICT(guild_id) DO UPDATE SET welcome_channel_id = excluded.welcome_channel_id", (str(interaction.guild.id), str(channel.id)))
        await db.commit()
    await interaction.response.send_message(f"✅ 欢迎频道已绑定至: {channel.mention}", ephemeral=True)

@bot.tree.command(name="set_review", description="🛠️ 设置买家好评同步展示的频道")
@app_commands.checks.has_permissions(administrator=True)
async def set_review(interaction: discord.Interaction, channel: discord.TextChannel):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT INTO config (guild_id, review_channel_id) VALUES (?, ?) ON CONFLICT(guild_id) DO UPDATE SET review_channel_id = excluded.review_channel_id", (str(interaction.guild.id), str(channel.id)))
        await db.commit()
    await interaction.response.send_message(f"✅ 好评展示墙已绑定至: {channel.mention}", ephemeral=True)

Thread(target=run_flask).start()
bot.run(os.environ.get('DISCORD_TOKEN'))
