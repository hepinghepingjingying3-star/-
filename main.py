import discord
from discord import app_commands
from discord.ext import commands
import aiosqlite
import asyncio
import os
import random
from flask import Flask
from threading import Thread

app = Flask('')
@app.route('/')
def home(): return "DEE & XERN APP IS RUNNING"
def run_flask(): app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))

bot = commands.Bot(command_prefix="!", intents=discord.Intents.all())
DB_NAME = "shop_helper.db"

# ⚠️ 请在此处换上你真实的锁头分类/频道 ID
STATUS_CHANNEL_ID = 123456789012345678  
MEMBER_COUNT_CHANNEL_ID = 876543210987654321  

async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("CREATE TABLE IF NOT EXISTS config (guild_id TEXT PRIMARY KEY, welcome_channel_id TEXT, review_channel_id TEXT)")
        await db.execute("CREATE TABLE IF NOT EXISTS users (user_id TEXT PRIMARY KEY, balance REAL DEFAULT 0.0, points INTEGER DEFAULT 0)")
        await db.execute("CREATE TABLE IF NOT EXISTS coupons (code TEXT PRIMARY KEY, discount REAL, is_used INTEGER DEFAULT 0, user_id TEXT)")
        await db.execute("CREATE TABLE IF NOT EXISTS giveaways (msg_id TEXT PRIMARY KEY, prize_name TEXT, prize_type TEXT, prize_value TEXT, winners_count INTEGER, status TEXT DEFAULT 'OPEN')")
        await db.execute("CREATE TABLE IF NOT EXISTS giveaway_participants (msg_id TEXT, user_id TEXT, PRIMARY KEY(msg_id, user_id))")
        await db.commit()

async def update_member_count(guild):
    ch = guild.get_channel(MEMBER_COUNT_CHANNEL_ID)
    if ch:
        try: await ch.edit(name=f"🔒 成员总数: {guild.member_count}")
        except: pass

@bot.event
async def on_ready():
    await init_db()
    print("🚀 BOT ONLINE")
    try: await bot.tree.sync()
    except: pass

@bot.event
async def on_member_join(member: discord.Member): await update_member_count(member.guild)
@bot.event
async def on_member_remove(member: discord.Member): await update_member_count(member.guild)

class GiveawayJoinView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="🎉 参与抽奖", style=discord.ButtonStyle.success, custom_id="join_giveaway_btn")
    async def join_giveaway(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        msg_id, user_id = str(interaction.message.id), str(interaction.user.id)
        async with aiosqlite.connect(DB_NAME) as db:
            async with db.execute("SELECT status FROM giveaways WHERE msg_id = ?", (msg_id,)) as cur:
                g = await cur.fetchone()
                if not g or g[0] != 'OPEN':
                    await interaction.followup.send("❌ 该抽奖活动已经结束或已被删除！", ephemeral=True)
                    return
            try:
                await db.execute("INSERT INTO giveaway_participants (msg_id, user_id) VALUES (?, ?)", (msg_id, user_id))
                await db.commit()
                await interaction.followup.send("✅ 成功参与抽奖！祝您好运连连！", ephemeral=True)
            except:
                await interaction.followup.send("⚠️ 您已经参与过本次抽奖，请勿重复点击！", ephemeral=True)

async def draw_giveaway_winners(msg_id, interaction_or_guild):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT prize_name, prize_type, prize_value, winners_count FROM giveaways WHERE msg_id = ?", (msg_id,)) as cur:
            g = await cur.fetchone()
            if not g: return None
            prize_name, prize_type, prize_value, winners_count = g
        async with db.execute("SELECT user_id FROM giveaway_participants WHERE msg_id = ?", (msg_id,)) as cur:
            rows = await cur.fetchall()
            participants = [r[0] for r in rows]
        if not participants: return "❌ 没有足够的参与者，无法开奖！"
        winners = random.sample(participants, min(winners_count, len(participants)))
        guild = interaction_or_guild.guild if hasattr(interaction_or_guild, 'guild') else interaction_or_guild
        winner_mentions = []
        async with aiosqlite.connect(DB_NAME) as db:
            for w_id in winners:
                member = guild.get_member(int(w_id))
                if member:
                    winner_mentions.append(member.mention)
                    if prize_type == "balance":
                        val = float(prize_value)
                        await db.execute("INSERT INTO users (user_id, balance) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET balance = balance + ?", (w_id, val, val))
                    elif prize_type == "points":
                        val = int(prize_value)
                        await db.execute("INSERT INTO users (user_id, points) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET points = points + ?", (w_id, val, val))
                    elif prize_type == "coupon":
                        cp_code = f"DX-{random.randint(1000,9999)}"
                        await db.execute("INSERT INTO coupons (code, discount, user_id) VALUES (?, ?, ?)", (cp_code, float(prize_value), w_id))
            await db.execute("UPDATE giveaways SET status = 'CLOSED' WHERE msg_id = ?", (msg_id,))
            await db.commit()
        return winner_mentions, prize_name

@bot.tree.command(name="抽奖建立", description="🎁 [管理员] 建立一个自动派奖的抽奖活动")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.choices(奖品类型=[
    app_commands.Choice(name="💰 自动发放余额", value="balance"),
    app_commands.Choice(name="✨ 自动发放积分", value="points"),
    app_commands.Choice(name="🎟️ 自动发放优惠券", value="coupon")
])
async def create_giveaway(interaction: discord.Interaction, 奖品名称: str, 奖品类型: app_commands.Choice[str], 奖品价值: float, 中奖人数: int):
    embed = discord.Embed(title="🎉 限时抽奖活动！", description=f"**奖品：** {奖品名称}\n**类型：** 自动发放{奖品类型.name}\n**中奖名额：** {中奖人数} 人", color=discord.Color.gold())
    await interaction.response.send_message("正在发布抽奖...", ephemeral=True)
    msg = await interaction.channel.send(embed=embed, view=GiveawayJoinView())
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT INTO giveaways (msg_id, prize_name, prize_type, prize_value, winners_count) VALUES (?, ?, ?, ?, ?)", (str(msg.id), 奖品名称, 奖品类型.value, str(奖品价值), 中奖人数))
        await db.commit()
@bot.tree.command(name="抽奖结束", description="🔒 [管理员] 立即开奖并结束指定的抽奖")
@app_commands.checks.has_permissions(administrator=True)
async def end_giveaway(interaction: discord.Interaction, 抽奖消息id: str):
    await interaction.response.defer(ephemeral=True)
    res = await draw_giveaway_winners(抽奖消息id, interaction)
    if isinstance(res, str): await interaction.followup.send(res)
    elif res:
        mentions, p_name = res
        await interaction.channel.send(f"🎉 恭喜：{', '.join(mentions)} 获得 **{p_name}**！奖品已到账！")
        await interaction.followup.send("✅ 已成功强制开奖！")

@bot.tree.command(name="抽奖重新抽", description="🔄 [管理员] 重新抽取幸运中奖者")
@app_commands.checks.has_permissions(administrator=True)
async def reroll_giveaway(interaction: discord.Interaction, 抽奖消息id: str):
    await interaction.response.defer(ephemeral=True)
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE giveaways SET status = 'OPEN' WHERE msg_id = ?", (抽奖消息id,))
        await db.commit()
    res = await draw_giveaway_winners(抽奖消息id, interaction)
    if isinstance(res, str): await interaction.followup.send(res)
    elif res:
        mentions, p_name = res
        await interaction.channel.send(f"🔄 重新开奖成功！恭喜新幸运儿：{', '.join(mentions)} 获得 **{p_name}**！")
        await interaction.followup.send("✅ 重新抽奖成功！")

@bot.tree.command(name="抽奖删除", description="🗑️ [管理员] 彻底删除一个抽奖活动")
@app_commands.checks.has_permissions(administrator=True)
async def delete_giveaway(interaction: discord.Interaction, 抽奖消息id: str):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM giveaways WHERE msg_id = ?", (抽奖消息id,))
        await db.execute("DELETE FROM giveaway_participants WHERE msg_id = ?", (抽奖消息id,))
        await db.commit()
    try:
        msg = await interaction.channel.fetch_message(int(抽奖消息id))
        await msg.delete()
    except: pass
    await interaction.response.send_message("🗑️ 抽奖已被彻底删除！", ephemeral=True)

class ShopDropdown(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="游戏代充", description="手游、端游代充值业务", emoji="🎮"),
            discord.SelectOption(label="网页代购", description="海外网站、软件代购服务", emoji="🌐"),
            discord.SelectOption(label="客服咨询", description="寻求人工客服沟通", emoji="👩‍💻"),
        ]
        super().__init__(placeholder="❓ 请选择您需要办理的业务分类", min_values=1, max_values=1, options=options)
    async def callback(self, interaction: discord.Interaction):
        # ⚡ 终极修复：此处绝对不能先调用 defer，直接转换传参唤起弹窗，彻底根治开单报错！
        await interaction.response.send_modal(OrderModal(self.values[0]))

class ShopMainView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None); self.add_item(ShopDropdown())

class OrderModal(discord.ui.Modal, title="📝 填写代充/代购服务单"):
    item = discord.ui.TextInput(label="代充的物品 / 代购的商品名称", placeholder="例如: 某某游戏点券...")
    remarks = discord.ui.TextInput(label="具体账号信息 / 商品链接与要求", style=discord.TextStyle.long, placeholder="请在此填写账号、密码、区服...")
    def __init__(self, category): super().__init__(); self.category = category
    async def on_submit(self, interaction: discord.Interaction):
        guild, buyer = interaction.guild, interaction.user
        overwrites = {guild.default_role: discord.PermissionOverwrite(read_messages=False), buyer: discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True), guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True)}
        ch = await guild.create_text_channel(name=f"📩-{buyer.name}", overwrites=overwrites)
        await interaction.response.send_message(f"✅ 工单已创建！{ch.mention}", ephemeral=True)
        embed = discord.Embed(title="📩 专属工单服务中心", description="请核对需求，等待管理员报价处理。", color=discord.Color.blue())
        embed.add_field(name="🗂️ 业务分类", value=self.category, inline=True)
        embed.add_field(name="📦 目标商品", value=self.item.value, inline=True)
        embed.add_field(name="💬 账号信息与要求", value=f"```\n{self.remarks.value}\n```", inline=False)
        await ch.send(embed=embed, view=OrderManagementView(buyer.id, self.item.value))

class ReviewModal(discord.ui.Modal, title="⭐️ 留下您的开店好评"):
    rating = discord.ui.TextInput(label="您愿意给本次服务打几星？(1 到 5)", placeholder="5", min_length=1, max_length=1)
    comments = discord.ui.TextInput(label="您的评语与心得", style=discord.TextStyle.long, placeholder="写下您的交易体验吧...", required=True)
    def __init__(self, item, ch_del): super().__init__(); self.item = item; self.ch_del = ch_del
    async def on_submit(self, interaction: discord.Interaction):
        guild, buyer = interaction.guild, interaction.user
        stars = "⭐" * int(self.rating.value) if self.rating.value.isdigit() and 1 <= int(self.rating.value) <= 5 else "⭐⭐⭐⭐⭐"
        async with aiosqlite.connect(DB_NAME) as db:
            async with db.execute("SELECT review_channel_id FROM config WHERE guild_id = ?", (str(guild.id),)) as cur:
                row = await cur.fetchone() # 🔥 核心修正：完美替换变量拼写错误，彻底恢复数据库对齐
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
        await interaction.response.send_message("💖 感谢评价！工单将在 3 秒后关闭。")
        await asyncio.sleep(3); await self.ch_del.delete()

class OrderManagementView(discord.ui.View):
    def __init__(self, buyer_id, item): super().__init__(timeout=None); self.buyer_id = buyer_id; self.item = item
    @discord.ui.button(label="🔒 管理员：完成交易并邀请评价", style=discord.ButtonStyle.danger, custom_id="close_order_with_review")
    async def close_order(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ 只有管理员可以执行结单操作！", ephemeral=True)
            return
        buyer = interaction.guild.get_member(self.buyer_id)
        if buyer:
            class ReviewTriggerView(discord.ui.View):
                def __init__(self, item, channel): super().__init__(timeout=60); self.item = item; self.channel = channel
                @discord.ui.button(label="⭐ 点击为本次交易打分留评", style=discord.ButtonStyle.primary)
                async def click_review(self, inter: discord.Interaction, btn: discord.ui.Button):
                    if inter.user.id != buyer.id:
                        await inter.response.send_message("❌ 只有买家本人可以评价！", ephemeral=True)
                        return
                    await inter.response.send_modal(ReviewModal(self.item, self.channel))
            await interaction.response.send_message(content=f"🔔 {buyer.mention} 订单已充值完毕！请点击下方按钮打个分：", view=ReviewTriggerView(self.item, interaction.channel))
        else: await interaction.channel.delete()

@bot.tree.command(name="shop", description="🛍️ 呼出客服中心")
async def shop(interaction: discord.Interaction):
    embed = discord.Embed(title="📥 客服中心", description="欢迎光临！请选择您需要办理的业务通道。", color=discord.Color.from_rgb(47, 49, 54))
    await interaction.response.send_message(embed=embed, view=ShopMainView())

@bot.tree.command(name="status", description="🛠️ [管理员] 一键切换店铺营业状态招牌")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.choices(state=[app_commands.Choice(name="🟢 正常营业 (OPEN)", value="OPEN"), app_commands.Choice(name="🔴 暂停营业 (CLOSE)", value="CLOSE")])
async def set_shop_status(interaction: discord.Interaction, state: app_commands.Choice[str]):
    ch = interaction.guild.get_channel(STATUS_CHANNEL_ID)
    if not ch: return
    await interaction.response.defer(ephemeral=True)
    if state.value == "OPEN":
        await ch.edit(name="🔒 DEE & XERN 🟢OPEN")
        await interaction.followup.send("✅ 招牌已成功修改为 OPEN！")
    else:
        await ch.edit(name="🔒 DEE & XERN 🔴CLOSE")
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

@bot.tree.command(name="管理查询账户", description="🛠️ [管理员] 查询用户的余额与积分")
@app_commands.checks.has_permissions(administrator=True)
async def admin_check_user(interaction: discord.Interaction, 目标成员: discord.Member):
    async with aiosqlite.connect(DB_NAME) as db:async with db.execute("SELECT balance, points FROM users WHERE user_id = ?", (str(目标成员.id),)) as cur:
row = await cur.fetchone()
bal, pts = (row[0], row[1]) if row else (0.0, 0)
await interaction.response.send_message(f"👤 账户：{目标成员.mention}\n💰 余额：￥{bal}\n✨ 积分：{pts}", ephemeral=True)
@bot.tree.command(name="管理充值", description="🛠️ [管理员] 后台充值并等额赠送积分")
@app_commands.checks.has_permissions(administrator=True)
async def admin_add_balance(interaction: discord.Interaction, 目标成员: discord.Member, 储值金额: float):
async with aiosqlite.connect(DB_NAME) as db:
pts = int(储值金额)
await db.execute("INSERT INTO users (user_id, balance, points) VALUES (?, ?, ?) ON CONFLICT(user_id) DO UPDATE SET balance = balance + ?, points = points + ?", (str(目标成员.id), 储值金额, pts, 储值金额, pts))
await db.commit()
await interaction.response.send_message(f"✅ 成功为 {目标成员.mention} 充值 ￥{储值金额} 并赠送 {pts} 积分！", ephemeral=True)
Thread(target=run_flask).start()
bot.run(os.environ.get('DISCORD_TOKEN'))
