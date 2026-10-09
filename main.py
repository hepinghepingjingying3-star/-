import discord
from discord import app_commands
from discord.ext import commands
import aiosqlite
import asyncio
import os
from flask import Flask
from threading import Thread

# ==================== Render 专属网页保活伪装 ====================
app = Flask('')

@app.route('/')
def home():
    return "🌐 机器人正在 Render 云端全天候安全运行中！"

def run_flask():
    # Render 免费网页必须绑定 0.0.0.0 和指定的 PORT
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_flask)
    t.start()

# ==================== 1. 初始化 ====================
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
DB_NAME = "shop_helper.db"

# ==================== 2. 数据库 ====================
async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("CREATE TABLE IF NOT EXISTS config (guild_id TEXT PRIMARY KEY, welcome_channel_id TEXT, review_channel_id TEXT)")
        await db.commit()

@bot.event
async def on_ready():
    await init_db()
    print(f"🚀 商城工单(纯评价版)已上线！账号: {bot.user}")
    try:
        await bot.tree.sync()
        print(f"✅ 成功同步所有服务指令！")
    except Exception as e:
        print(f"❌ 同步失败: {e}")

# ==================== 3. 纯欢迎系统 ====================
@bot.event
async def on_member_join(member: discord.Member):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT welcome_channel_id FROM config WHERE guild_id = ?", (str(member.guild.id),)) as cursor:
            row = await cursor.fetchone()
            if row and row:
                channel = member.guild.get_channel(int(row))
                if channel:
                    embed = discord.Embed(title="🎉 欢迎新成员！", description=f"热烈欢迎 {member.mention} 加入服务器！", color=discord.Color.green())
                    embed.set_thumbnail(url=member.display_avatar.url)
                    await channel.send(content=member.mention, embed=embed)

# ==================== 4. 下拉菜单与表单 ====================
class ShopDropdown(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="游戏代充", description="手游、端游代充值业务", emoji="🎮"),
            discord.SelectOption(label="网页代购", description="海外网站、软件代购服务", emoji="🌐"),
            discord.SelectOption(label="客服咨询", description="寻求人工客服沟通", emoji="👩‍💻"),
        ]
        super().__init__(placeholder="❓ 请选择您需要办理的业务分类", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(OrderModal(service_category=self.values))

class OrderModal(discord.ui.Modal, title="📝 填写服务单"):
    item_name = discord.ui.TextInput(label="代充的物品 / 代购的商品名称", placeholder="例如: 某某游戏点券、Roblox续费...")
    remarks = discord.ui.TextInput(label="具体账号信息 / 商品链接与要求", style=discord.TextStyle.long, placeholder="请在此填写账号、密码、区服或网址...")

    def __init__(self, service_category):
        super().__init__()
        self.service_category = service_category

    async def on_submit(self, interaction: discord.Interaction):
        guild = interaction.guild
        buyer = interaction.user

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            buyer: discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True)
        }

        order_channel = await guild.create_text_channel(name=f"📩-{buyer.name}", overwrites=overwrites)
        await interaction.response.send_message(f"✅ 工单已创建！请前往该频道沟通：{order_channel.mention}", ephemeral=True)

        embed = discord.Embed(title="📩 专属工单服务中心", description="管理员稍后会在此为您报价，请耐心等待。", color=discord.Color.blue())
        embed.add_field(name="🗂️ 业务分类", value=self.service_category, inline=True)
        embed.add_field(name="📦 目标商品", value=self.item_name.value, inline=True)
        embed.add_field(name="💬 详细账号要求", value=f"```\n{self.remarks.value}\n```", inline=False)

        await order_channel.send(embed=embed, view=OrderManagementView(buyer_id=buyer.id, item_name=self.item_name.value))

# ==================== 5. 好评收集系统的弹窗 ====================
class ReviewModal(discord.ui.Modal, title="⭐️ 留下您的开店好评"):
    rating = discord.ui.TextInput(label="您愿意给本次服务打几星？(1 到 5)", placeholder="5", min_length=1, max_length=1)
    comments = discord.ui.TextInput(label="您的评语与心得", style=discord.TextStyle.long, placeholder="写下您的交易体验吧...", required=True)

    def __init__(self, item_name, channel_to_delete):
        super().__init__()
        self.item_name = item_name
        self.channel_to_delete = channel_to_delete

    async def on_submit(self, interaction: discord.Interaction):
        guild = interaction.guild
        buyer = interaction.user
        
        stars = "⭐" * int(self.rating.value) if self.rating.value.isdigit() and 1 <= int(self.rating.value) <= 5 else "⭐⭐⭐⭐⭐"
        
        async with aiosqlite.connect(DB_NAME) as db:
            async with db.execute("SELECT review_channel_id FROM config WHERE guild_id = ?", (str(guild.id),)) as cursor:
                row = await cursor.fetchone()
                if row and row:
                    review_channel = guild.get_channel(int(row))
                    if review_channel:
                        rev_embed = discord.Embed(title="🛍️ 来自买家的真实好评", color=discord.Color.gold())
                        rev_embed.add_field(name="👤 满意买家", value=buyer.mention, inline=True)
                        rev_embed.add_field(name="📦 交易商品", value=self.item_name, inline=True)
                        rev_embed.add_field(name="✨ 评分等级", value=stars, inline=False)
                        rev_embed.add_field(name="💬 真实评语", value=f"```\n{self.comments.value}\n```", inline=False)
                        rev_embed.set_thumbnail(url=buyer.display_avatar.url)
                        await review_channel.send(embed=rev_embed)

        await interaction.response.send_message("💖 感谢您的评价！工单将在 3 秒后删除。")
        await asyncio.sleep(3)
        await self.channel_to_delete.delete()

# ==================== 6. 工单面板与结单评价 ====================
class OrderManagementView(discord.ui.View):
    def __init__(self, buyer_id, item_name):
        super().__init__(timeout=None)
        self.buyer_id = buyer_id
        self.item_name = item_name

    @discord.ui.button(label="🔒 管理员：完成交易并邀请评价", style=discord.ButtonStyle.danger, custom_id="close_order_with_review")
    async def close_order(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ 只有管理员可以结单！", ephemeral=True)
            return

        guild = interaction.guild
        buyer = guild.get_member(self.buyer_id)

        if buyer:
            class ReviewTriggerView(discord.ui.View):
                def __init__(self, item_name, channel):
                    super().__init__(timeout=60)
                    self.item_name = item_name
                    self.channel = channel
                
                @discord.ui.button(label="⭐ 点击为本次交易打分留评", style=discord.ButtonStyle.primary)
                async def click_review(self, inter: discord.Interaction, btn: discord.ui.Button):
                    if inter.user.id != buyer.id:
                        await inter.response.send_message("❌ 只有买家本人可以评价！", ephemeral=True)
                        return
                    await inter.response.send_modal(ReviewModal(item_name=self.item_name, channel_to_delete=self.channel))

            await interaction.response.send_message(
                content=f"🔔 {buyer.mention} 订单已处理完毕！请点击下方按钮打个分，提交后频道会自动销毁：",
                view=ReviewTriggerView(item_name=self.item_name, channel=interaction.channel)
            )
        else:
            await interaction.response.send_message("🚧 找不到买家，5秒后自动强制删除频道...")
            await asyncio.sleep(5)
            await interaction.channel.delete()

# ==================== 7. 全局命令 ====================
@bot.tree.command(name="shop", description="🛍️ 呼出客服中心（选择业务）")
async def shop(interaction: discord.Interaction):
    view = discord.ui.View(timeout=None)
    view.add_item(ShopDropdown())
    embed = discord.Embed(title="📥 客服中心", description="欢迎光临！请在下方下拉菜单中选择您需要办理的业务通道。", color=discord.Color.from_rgb(47, 49, 54))
    await interaction.response.send_message(embed=embed, view=view)

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

# ==================== 8. 启动机器人 ====================
# 先开启网页保活线程，再启动 Discord 机器人
keep_alive()
bot.run(os.environ.get('DISCORD_TOKEN'))

