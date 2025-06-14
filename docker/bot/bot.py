import os
import re
import discord
from discord.ext import commands
import wavelink
import aiohttp
import json
import base64
import asyncio

# Environment variables
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
LAVALINK_HOST = os.getenv("LAVALINK_HOST", "lavalink")
LAVALINK_PORT = int(os.getenv("LAVALINK_PORT", "2333"))
LAVALINK_PASSWORD = os.getenv("LAVALINK_PASSWORD", "youshallnotpass")
FALLBACK_VOICE_CHANNEL_ID = int(os.getenv("FALLBACK_VOICE_CHANNEL_ID", "0"))
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")

# Discord bot setup
intents = discord.Intents.none()
intents.guilds = True
intents.guild_messages = True
intents.voice_states = True
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

URL_REGEX = re.compile(r"https?://\S+")

# Global variable for Spotify token
spotify_token = None

# Events
@bot.event
async def on_ready():
    print(f"Bot ready as {bot.user} ({bot.user.id})")
    
    # Wait for Lavalink to be ready with retries
    await setup_lavalink()

async def setup_lavalink():
    """Setup Lavalink connection with retries."""
    max_retries = 10
    retry_delay = 5
    
    for attempt in range(max_retries):
        try:
            # Check if Lavalink is accessible
            async with aiohttp.ClientSession() as session:
                try:
                    async with session.get(f"http://{LAVALINK_HOST}:{LAVALINK_PORT}/version", 
                                         timeout=aiohttp.ClientTimeout(total=5)) as resp:
                        if resp.status == 200:
                            print(f"Lavalink is accessible, connecting... (attempt {attempt + 1})")
                            break
                        else:
                            print(f"Lavalink returned status {resp.status}")
                except Exception as e:
                    print(f"Lavalink not accessible yet: {e}")
                    
            if attempt < max_retries - 1:
                print(f"Waiting {retry_delay} seconds before retry...")
                await asyncio.sleep(retry_delay)
            else:
                print("Max retries reached, attempting connection anyway...")
                
        except Exception as e:
            print(f"Error checking Lavalink: {e}")
            
    try:
        nodes = [wavelink.Node(
            uri=f"http://{LAVALINK_HOST}:{LAVALINK_PORT}",
            password=LAVALINK_PASSWORD,
        )]
        
        # Connect to Lavalink with timeout
        await wavelink.Pool.connect(nodes=nodes, client=bot)
        print("Lavalink connected successfully")
        
        # Verify connection
        if wavelink.Pool.nodes:
            for node in wavelink.Pool.nodes.values():
                print(f"Node {node.identifier}: {node.status}")
        
    except Exception as e:
        print(f"Failed to connect to Lavalink: {e}")
        print("Bot will continue running, but music commands may not work")

# Helper functions
async def get_spotify_access_token():
    """Get Spotify access token using client credentials."""
    global spotify_token
    
    if not SPOTIFY_CLIENT_ID or not SPOTIFY_CLIENT_SECRET:
        return None
    
    try:
        # Encode credentials
        credentials = f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        
        headers = {
            'Authorization': f'Basic {encoded_credentials}',
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        
        data = {
            'grant_type': 'client_credentials'
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post('https://accounts.spotify.com/api/token', 
                                  headers=headers, data=data) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    spotify_token = result.get('access_token')
                    return spotify_token
                else:
                    print(f"Failed to get Spotify token: {resp.status}")
                    return None
    except Exception as e:
        print(f"Error getting Spotify token: {e}")
        return None

async def get_spotify_track_info(spotify_url: str):
    """Extract track info from Spotify URL using official API."""
    try:
        # Extract track ID from URL
        track_id_match = re.search(r'/track/([a-zA-Z0-9]+)', spotify_url)
        if not track_id_match:
            return None
        
        track_id = track_id_match.group(1)
        
        # Get access token if we don't have one
        if not spotify_token:
            await get_spotify_access_token()
        
        if not spotify_token:
            print("No Spotify token available, falling back to web scraping")
            return await get_spotify_track_info_fallback(spotify_url)
        
        # Use Spotify Web API
        headers = {
            'Authorization': f'Bearer {spotify_token}'
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(f'https://api.spotify.com/v1/tracks/{track_id}', 
                                 headers=headers) as resp:
                if resp.status == 200:
                    track_data = await resp.json()
                    track_name = track_data['name']
                    artists = [artist['name'] for artist in track_data['artists']]
                    artist_string = ', '.join(artists)
                    return f"{track_name} {artist_string}"
                elif resp.status == 401:  # Token expired
                    spotify_token = None
                    await get_spotify_access_token()
                    if spotify_token:
                        headers['Authorization'] = f'Bearer {spotify_token}'
                        async with session.get(f'https://api.spotify.com/v1/tracks/{track_id}', 
                                             headers=headers) as retry_resp:
                            if retry_resp.status == 200:
                                track_data = await retry_resp.json()
                                track_name = track_data['name']
                                artists = [artist['name'] for artist in track_data['artists']]
                                artist_string = ', '.join(artists)
                                return f"{track_name} {artist_string}"
                
                print(f"Spotify API failed with status {resp.status}, falling back")
                return await get_spotify_track_info_fallback(spotify_url)
        
    except Exception as e:
        print(f"Error with Spotify API: {e}")
        return await get_spotify_track_info_fallback(spotify_url)

async def get_spotify_track_info_fallback(spotify_url: str):
    """Fallback method using different scraping approach."""
    try:
        # Extract track ID from URL
        track_id_match = re.search(r'/track/([a-zA-Z0-9]+)', spotify_url)
        if not track_id_match:
            return None
        
        track_id = track_id_match.group(1)
        
        # Try different approaches
        approaches = [
            f"https://open.spotify.com/embed/track/{track_id}",
            f"https://open.spotify.com/track/{track_id}",
        ]
        
        async with aiohttp.ClientSession() as session:
            for url in approaches:
                try:
                    headers = {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                    }
                    
                    async with session.get(url, headers=headers) as resp:
                        if resp.status == 200:
                            html = await resp.text()
                            
                            # Try multiple extraction methods
                            patterns = [
                                # OpenGraph tags
                                (r'<meta property="og:title" content="([^"]+)"', r'<meta property="og:description" content="([^"]+)"'),
                                # JSON-LD structured data
                                (r'"name":"([^"]+)".*?"byArtist":\{"@type":"MusicGroup","name":"([^"]+)"', None),
                                # Title tag
                                (r'<title>([^<]+)</title>', None),
                            ]
                            
                            for title_pattern, desc_pattern in patterns:
                                title_match = re.search(title_pattern, html, re.DOTALL)
                                if title_match:
                                    title = title_match.group(1).strip()
                                    
                                    if desc_pattern:
                                        desc_match = re.search(desc_pattern, html, re.DOTALL)
                                        if desc_match and "song by" in desc_match.group(1).lower():
                                            desc = desc_match.group(1)
                                            artist_match = re.search(r'song by ([^·•]+)', desc, re.IGNORECASE)
                                            if artist_match:
                                                artist = artist_match.group(1).strip()
                                                return f"{title} {artist}"
                                    
                                    # If we have a title but no artist description, try to extract from title
                                    if " - " in title:
                                        return title.replace(" - ", " ")
                                    elif " by " in title.lower():
                                        return title.replace(" by ", " ").replace(" By ", " ")
                                    else:
                                        return title
                                        
                except Exception as e:
                    print(f"Failed approach {url}: {e}")
                    continue
        
        return None
        
    except Exception as e:
        print(f"Error in fallback method: {e}")
        return None

async def ensure_voice(ctx: commands.Context) -> wavelink.Player:
    """Join the author's voice channel or the fallback channel."""
    if ctx.voice_client and isinstance(ctx.voice_client, wavelink.Player):
        return ctx.voice_client
    
    if ctx.author.voice and ctx.author.voice.channel:
        channel = ctx.author.voice.channel
    else:
        channel = ctx.guild.get_channel(FALLBACK_VOICE_CHANNEL_ID)
    
    if channel is None:
        raise commands.CommandError("No voice channel available")
    
    player = await channel.connect(cls=wavelink.Player)
    return player

async def check_lavalink_connection():
    """Check if Lavalink is connected and working."""
    if not wavelink.Pool.nodes:
        return False, "No Lavalink nodes available"
    
    for node in wavelink.Pool.nodes.values():
        if node.status == wavelink.NodeStatus.CONNECTED:
            return True, "Connected"
    
    return False, "No connected nodes"

# Commands
@bot.command(name="play")
async def play(ctx: commands.Context, *, query: str):
    """Play a track from YouTube or Spotify."""
    try:
        # Check Lavalink connection first
        connected, status = await check_lavalink_connection()
        if not connected:
            return await ctx.send(f"❌ Lavalink not connected: {status}")
        
        player = await ensure_voice(ctx)
        
        # Handle Spotify URLs
        if "open.spotify.com" in query:
            await ctx.send("🔍 Searching Spotify track on YouTube...")
            spotify_info = await get_spotify_track_info(query)
            if spotify_info:
                query = spotify_info
                await ctx.send(f"Found: **{spotify_info}**")
            else:
                return await ctx.send("❌ Could not extract track info from Spotify URL")
        
        # Search for tracks
        try:
            tracks = await wavelink.Playable.search(query)
        except Exception as e:
            return await ctx.send(f"❌ Search failed: {str(e)}")
        
        if not tracks:
            return await ctx.send("❌ No tracks found")
        
        # If it's a playlist, add all tracks
        if isinstance(tracks, wavelink.Playlist):
            added = 0
            for track in tracks.tracks:
                await player.queue.put_wait(track)
                added += 1
            await ctx.send(f"✅ Added playlist **{tracks.name}** with {added} tracks")
            
            # Start playing if not already playing
            if not player.playing and not player.paused:
                next_track = await player.queue.get_wait()
                await player.play(next_track)
        else:
            # Add the first track found
            track = tracks[0]
            
            # Debug info
            print(f"Track found: {track.title}")
            print(f"Track URI: {track.uri}")
            print(f"Track source: {track.source}")
            
            # If nothing is playing, play immediately
            if not player.playing and not player.paused:
                try:
                    await player.play(track)
                    await ctx.send(f"🎵 Now playing: **{track.title}**")
                    
                    # Wait a moment and check if it's actually playing
                    await asyncio.sleep(3)
                    
                    if not player.playing:
                        await ctx.send("⚠️ Track failed to start. Trying alternative...")
                        
                        # Try with different tracks from search results
                        for i, alt_track in enumerate(tracks[1:6], 1):  # Try next 5 results
                            try:
                                await player.play(alt_track)
                                await asyncio.sleep(2)
                                if player.playing:
                                    await ctx.send(f"🎵 Successfully playing: **{alt_track.title}**")
                                    break
                                else:
                                    print(f"Alternative track {i} failed to play")
                            except Exception as e:
                                print(f"Error with alternative track {i}: {e}")
                                continue
                        else:
                            # If all alternatives failed, try a more generic search
                            try:
                                generic_query = f"{query} audio"
                                generic_tracks = await wavelink.Playable.search(generic_query)
                                if generic_tracks:
                                    await player.play(generic_tracks[0])
                                    await ctx.send(f"🎵 Playing alternative: **{generic_tracks[0].title}**")
                                else:
                                    await ctx.send("❌ Unable to play any version of this track")
                            except Exception as e:
                                await ctx.send(f"❌ All playback attempts failed: {str(e)}")
                
                except Exception as e:
                    print(f"Error playing track: {e}")
                    await ctx.send(f"❌ Error playing track: {str(e)}")
            else:
                # Add to queue
                await player.queue.put_wait(track)
                await ctx.send(f"✅ Added to queue: **{track.title}**")
        
    except Exception as e:
        print(f"Error in play command: {e}")
        await ctx.send(f"❌ An error occurred: {str(e)[:100]}...")

@bot.command(name="skip")
async def skip(ctx: commands.Context):
    """Skip the current track."""
    if not ctx.voice_client or not isinstance(ctx.voice_client, wavelink.Player):
        return await ctx.send("Not connected to voice")
    
    player = ctx.voice_client
    await player.skip(force=True)
    await ctx.send("⏭️ Skipped!")

@bot.command(name="pause")
async def pause(ctx: commands.Context):
    """Pause or resume the current track."""
    if not ctx.voice_client or not isinstance(ctx.voice_client, wavelink.Player):
        return await ctx.send("Not connected to voice")
    
    player = ctx.voice_client
    await player.pause(not player.paused)
    
    if player.paused:
        await ctx.send("⏸️ Paused")
    else:
        await ctx.send("▶️ Resumed")

@bot.command(name="queue", aliases=["q"])
async def queue_cmd(ctx: commands.Context):
    """Show the current queue."""
    if not ctx.voice_client or not isinstance(ctx.voice_client, wavelink.Player):
        return await ctx.send("Not connected to voice")
    
    player = ctx.voice_client
    
    # Create a list starting with currently playing track
    queue_list = []
    
    # Add currently playing track
    if player.current:
        queue_list.append(f"🎵 **Currently playing:** {player.current.title}")
        queue_list.append("")  # Empty line for separation
    
    # Add queued tracks
    if player.queue.is_empty:
        if not player.current:
            return await ctx.send("Queue is empty and nothing is playing")
        queue_list.append("Queue is empty")
    else:
        queue_list.append(f"**Upcoming tracks ({len(player.queue)}):**")
        for i, track in enumerate(player.queue):
            queue_list.append(f"{i+1}. **{track.title}**")
            if i >= 9:  # Limit to first 10 tracks
                queue_list.append(f"... and {len(player.queue)-10} more tracks")
                break
    
    queue_text = "\n".join(queue_list)
    await ctx.send(queue_text)

@bot.command(name="stop")
async def stop(ctx: commands.Context):
    """Stop playing and clear the queue."""
    if not ctx.voice_client or not isinstance(ctx.voice_client, wavelink.Player):
        return await ctx.send("Not connected to voice")
    
    player = ctx.voice_client
    player.queue.clear()
    await player.stop()
    await ctx.send("⏹️ Stopped and cleared queue")

@bot.command(name="disconnect", aliases=["dc", "leave"])
async def disconnect(ctx: commands.Context):
    """Disconnect from voice channel."""
    if not ctx.voice_client or not isinstance(ctx.voice_client, wavelink.Player):
        return await ctx.send("Not connected to voice")
    
    player = ctx.voice_client
    await player.disconnect()
    await ctx.send("👋 Disconnected")

@bot.command(name="nowplaying", aliases=["np", "current"])
async def now_playing(ctx: commands.Context):
    """Show the currently playing track."""
    if not ctx.voice_client or not isinstance(ctx.voice_client, wavelink.Player):
        return await ctx.send("Nothing is playing")
    
    player = ctx.voice_client
    
    if not player.current:
        return await ctx.send("Nothing is playing")
    
    track = player.current
    
    # Format duration
    duration = f"{track.length // 60000}:{(track.length // 1000) % 60:02d}"
    position = f"{player.position // 60000}:{(player.position // 1000) % 60:02d}"
    
    embed = discord.Embed(
        title="🎵 Now Playing",
        description=f"**{track.title}**\n{track.author}",
        color=0x00ff00
    )
    embed.add_field(name="Duration", value=f"{position} / {duration}", inline=True)
    embed.add_field(name="Requested by", value=getattr(track, 'requester', 'Unknown'), inline=True)
    
    if hasattr(track, 'artwork'):
        embed.set_thumbnail(url=track.artwork)
    
    await ctx.send(embed=embed)

@bot.command(name="volume", aliases=["vol"])
async def volume(ctx: commands.Context, vol: int = None):
    """Set or show the volume (1-100)."""
    if not ctx.voice_client or not isinstance(ctx.voice_client, wavelink.Player):
        return await ctx.send("Not connected to voice")
    
    player = ctx.voice_client
    
    if vol is None:
        return await ctx.send(f"Current volume: {player.volume}%")
    
    if not 1 <= vol <= 100:
        return await ctx.send("Volume must be between 1 and 100")
    
    await player.set_volume(vol)
    await ctx.send(f"🔊 Volume set to {vol}%")

@bot.command(name="shuffle")
async def shuffle(ctx: commands.Context):
    """Shuffle the queue."""
    if not ctx.voice_client or not isinstance(ctx.voice_client, wavelink.Player):
        return await ctx.send("Not connected to voice")
    
    player = ctx.voice_client
    
    if player.queue.is_empty:
        return await ctx.send("Queue is empty")
    
    player.queue.shuffle()
    await ctx.send("🔀 Queue shuffled!")

@bot.command(name="debug")
async def debug(ctx: commands.Context):
    """Debug information about the player."""
    # Lavalink connection status
    connected, status = await check_lavalink_connection()
    debug_info = [
        f"**Lavalink Status:** {status}",
        f"**Nodes:** {len(wavelink.Pool.nodes)}",
    ]
    
    if wavelink.Pool.nodes:
        for node in wavelink.Pool.nodes.values():
            debug_info.append(f"Node {node.identifier}: {node.status.name}")
    
    # Player status
    if ctx.voice_client and isinstance(ctx.voice_client, wavelink.Player):
        player = ctx.voice_client
        debug_info.extend([
            f"",
            f"**Player Status:**",
            f"Playing: {player.playing}",
            f"Paused: {player.paused}",
            f"Connected: {player.connected}",
            f"Queue size: {len(player.queue)}",
            f"Current track: {player.current.title if player.current else 'None'}",
            f"Position: {player.position}ms" if player.current else "Position: N/A",
            f"Volume: {player.volume}%",
            f"Channel: {player.channel.name if player.channel else 'None'}",
        ])
    else:
        debug_info.append("**Player:** Not connected to voice")
    
    await ctx.send("\n".join(debug_info))

@bot.command(name="test_lavalink")
async def test_lavalink(ctx: commands.Context):
    """Test Lavalink connection."""
    try:
        # Test HTTP connection
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(f"http://{LAVALINK_HOST}:{LAVALINK_PORT}/version", 
                                     timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status == 200:
                        version_data = await resp.text()
                        await ctx.send(f"✅ Lavalink HTTP accessible\nVersion response: {version_data}")
                    else:
                        await ctx.send(f"⚠️ Lavalink HTTP returned status {resp.status}")
            except Exception as e:
                await ctx.send(f"❌ Lavalink HTTP not accessible: {e}")
        
        # Test WebSocket connection
        nodes = wavelink.Pool.nodes
        if not nodes:
            await ctx.send("❌ No Lavalink nodes connected")
            return
        
        node_info = []
        for node in nodes.values():
            node_info.append(f"**Node {node.identifier}:**")
            node_info.append(f"Status: {node.status.name}")
            node_info.append(f"Players: {len(node.players)}")
            node_info.append(f"URI: {node.uri}")
            node_info.append("")
        
        await ctx.send("\n".join(node_info))
        
    except Exception as e:
        await ctx.send(f"❌ Lavalink test error: {str(e)}")

@bot.command(name="reconnect")
async def reconnect_lavalink(ctx: commands.Context):
    """Attempt to reconnect to Lavalink."""
    await ctx.send("🔄 Attempting to reconnect to Lavalink...")
    try:
        # Disconnect existing nodes
        for node in wavelink.Pool.nodes.values():
            await node.disconnect()
        
        # Clear nodes
        wavelink.Pool._nodes.clear()
        
        # Reconnect
        await setup_lavalink()
        
        connected, status = await check_lavalink_connection()
        if connected:
            await ctx.send("✅ Successfully reconnected to Lavalink")
        else:
            await ctx.send(f"❌ Failed to reconnect: {status}")
            
    except Exception as e:
        await ctx.send(f"❌ Reconnection error: {str(e)}")

# Event handlers for player - Simplified version
@bot.event  
async def on_wavelink_track_end(payload):
    """Handle when a track ends."""
    player = payload.player
    
    if not player.queue.is_empty:
        try:
            next_track = await player.queue.get_wait()
            await player.play(next_track)
        except Exception as e:
            print(f"Error playing next track: {e}")

@bot.event
async def on_wavelink_track_start(payload):
    """Handle when a track starts playing."""
    print(f"Now playing: {payload.track.title}")

@bot.event
async def on_wavelink_track_exception(payload):
    """Handle track exceptions."""
    print(f"Track exception: {payload.exception}")
    player = payload.player
    
    # Try to play next track if available
    if not player.queue.is_empty:
        try:
            next_track = await player.queue.get_wait()
            await player.play(next_track)
        except Exception as e:
            print(f"Error playing next track after exception: {e}")

@bot.event
async def on_wavelink_node_ready(payload):
    """Handle when a node connects."""
    print(f"Wavelink node {payload.node.identifier} is ready!")

# Error handling
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("❌ Missing required argument")
    elif isinstance(error, commands.BadArgument):
        await ctx.send("❌ Invalid argument")
    else:
        print(f"Error in command {ctx.command}: {error}")
        await ctx.send("❌ An error occurred while processing the command")

# Run the bot
if __name__ == "__main__":
    if not DISCORD_TOKEN:
        print("Error: DISCORD_TOKEN environment variable not set")
    else:
        bot.run(DISCORD_TOKEN)
