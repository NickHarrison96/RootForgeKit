# =============================================================================
# RootForgeKit — Gamer Tools Tab
#
# Same shape as TechToolsTab (see tabs/tool_tab_base.py): status-aware winget
# app cards plus command cards that run through TerminalConsoleWidget.
# =============================================================================

from tabs.tool_tab_base import ToolTabBase
from utils.command_builder import ps_encoded_command

# -- monitoring / health commands: (command_key, glyph, name, desc) ---------
MONITORING = [
    ("gpu_info",     "🎮", "GPU Monitor",
     "GPU adapter, driver version, VRAM and status. Outdated drivers cost frames."),
    ("process_list", "⚡", "Process Priority",
     "Top CPU consumers — the background apps eating your headroom."),
    ("network_diag", "📶", "Network Check",
     "Network configuration and every listening port, for lag hunting."),
    ("disk_health",  "💽", "Drive Health",
     "SMART status. A failing drive shows up as stutter and long load times."),
]

# -- raw PowerShell one-shots: (key, command, glyph, name, desc) ------------
# Wrapped through ps_encoded_command(): a plain `powershell -Command "..."`
# gets mangled by the cmd.exe /c quoting layer (see utils/command_builder.py
# for the reproduction), so these go out base64-encoded.
TELEMETRY = [
    ("tele_top_procs",
     ps_encoded_command(
         "Get-Process | Sort-Object CPU -Descending | "
         "Select-Object -First 15 Name,CPU,WorkingSet | Format-Table -AutoSize"
     ),
     "🎯", "Top Processes (Detailed)",
     "Top 15 CPU consumers with per-process memory usage."),

    ("tele_net_adapter",
     ps_encoded_command(
         "Get-NetAdapterAdvancedProperty | Format-Table -AutoSize"
     ),
     "📡", "Network Adapter Tweaks",
     "Advanced adapter properties — offloads, RSS and interrupt moderation."),

    ("tele_gpu_driver",
     ps_encoded_command(
         "Get-CimInstance Win32_VideoController | "
         "Select-Object Name,DriverVersion,DriverDate | Format-List"
     ),
     "🖥️", "GPU Driver Info",
     "Driver version and release date — stale drivers hurt frame times."),

    ("tele_power_plan",
     ps_encoded_command("powercfg /getactivescheme"),
     "🔋", "Active Power Plan",
     "Which power plan is live. High Performance suits gaming better than Balanced."),
]

# -- optimization: (key, glyph, name, desc, command, risk, skip_confirm) ----
OPTIMIZATION = [
    ("opt_high_perf", "⚡", "Enable High Performance Plan",
     "Switch to the High Performance power plan.",
     "powercfg /setactive 8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c",
     "medium", False),

    ("opt_power_opts", "🔋", "Open Power Options",
     "Tune plan settings, PCIe power states and hibernation.",
     "start powercfg.cpl", "low", True),

    ("opt_game_mode", "🎮", "Game Mode Settings",
     "Windows Game Mode and background recording toggles.",
     "start ms-settings:gaming-gamemode", "low", True),

    ("opt_storage", "🧹", "Storage Sense",
     "Automatic temp and recycle-bin cleanup settings.",
     "start ms-settings:storagesense", "low", True),

    ("toggle_dark_mode", "🌗", "Toggle Dark Mode",
     "Switch between dark and light theme for apps and system chrome.",
     ps_encoded_command(
         "$p='HKCU:\\SOFTWARE\\Microsoft\\Windows\\"
         "CurrentVersion\\Themes\\Personalize';"
         "$v=(Get-ItemProperty $p -Name AppsUseLightTheme "
         "-ErrorAction SilentlyContinue).AppsUseLightTheme;"
         "if($v -eq 1){Set-ItemProperty $p AppsUseLightTheme "
         "0;Set-ItemProperty $p SystemUsesLightTheme 0;"
         "'Dark mode ON'}"
         "else{Set-ItemProperty $p AppsUseLightTheme 1;"
         "Set-ItemProperty $p SystemUsesLightTheme 1;"
         "'Dark mode OFF'}"
     ),
     "low", True),
]

# -- winget platform installers: (key, glyph, name, desc, winget_id) --------
PLATFORM_APPS = [
    ("app_steam",        "Steam",        "Valve's game store and library.",
     "Valve.Steam"),
    ("app_discord",      "Discord",      "Voice, video and text chat.",
     "Discord.Discord"),
    ("app_directx",      "DirectX",      "DirectX End-User Runtime (June 2010 redist).",
     "Microsoft.DirectX"),
    ("app_vcredist",     "VC++ Runtimes","Visual C++ 2015-2022 redistributable — needed by most games.",
     "Microsoft.VCRedist.2015+.x64"),
    ("app_afterburner",  "MSI Afterburner", "GPU overclocking, fan curve and on-screen overlay.",
     "Guru3D.MSIAfterburner"),
    ("app_epic",         "Epic Games",   "Epic Games Launcher and Store.",
     "EpicGames.EpicGamesLauncher"),
    ("app_ea",           "EA app",       "Electronic Arts desktop client.",
     "ElectronicArts.EADesktop"),
    ("app_blizzard",     "Blizzard App", "Blizzard game launcher.",
     "Blizzard.BlizzardApp"),
    ("app_icue",         "iCUE 4",       "CORSAIR RGB and peripheral control. Requires elevation.",
     "Corsair.iCUE.4", True),
    ("app_streamlabs",   "Streamlabs",   "Live streaming with OBS-based features.",
     "Streamlabs.Streamlabs"),
]

# -- tools with no winget package: shown as a link ------------------
# (key, glyph, name, description, url)
GAMING_LINKS = [
    ("link_cheatengine", "🎯", "Cheat Engine",
     "Memory scanner and editor for running games. Not in winget — opens the "
     "official download page.",
     "https://cheatengine.org/"),
    ("link_armoury",     "🔧", "Armoury Crate",
     "ASUS ROG/TUF RGB lighting and hardware control. Not in winget — "
     "opens the official ASUS download page.",
     "https://www.asus.com/supportonly/armoury%20crate/helpdesk_download"),
]


class GamerToolsTab(ToolTabBase):
    """Gaming utilities: monitoring, telemetry, tuning and platform installs."""

    def __init__(self, parent=None):
        super().__init__(
            title="🎮  Gamer Utilities",
            subtitle="Monitor the hardware, tune power and networking, and install "
                     "the platform runtimes games depend on. Everything runs in "
                     "the console below.",
            console_label="📟  Gaming Console",
            parent=parent,
        )
        self._build()
        self.finish_sections()

    def _build(self) -> None:
        # ---- Monitoring ----------------------------------------------
        section = self.add_section("📈  Performance Monitoring", expanded=True)
        for cmd_key, glyph, name, desc in MONITORING:
            self.add_command_card(section, cmd_key, glyph, name, desc)

        # ---- Detailed telemetry --------------------------------------
        section = self.add_section("🔬  Detailed Telemetry")
        for key, command, glyph, name, desc in TELEMETRY:
            self.add_raw_card(section, key, glyph, name, desc, command,
                              risk="low")

        # ---- Optimization --------------------------------------------
        section = self.add_section("🚀  Optimization")
        self.add_command_card(section, "flush_dns", "🌐", "Flush DNS Cache",
                              "Clear the resolver cache — fixes online matchmaking "
                              "and connectivity hiccups.")
        self.add_command_card(section, "temp_clean", "🧹", "Temp File Cleaner",
                              "Delete temporary files to reclaim disk space.")
        for key, glyph, name, desc, command, risk, skip in OPTIMIZATION:
            self.add_raw_card(section, key, glyph, name, desc, command,
                              risk=risk, skip_confirm=skip)

        # ---- Platform installers -------------------------------------
        section = self.add_section("🕹️  Platform Installers")
        for entry in PLATFORM_APPS:
            key, name, desc, winget_id = entry[:4]
            req_admin = entry[4] if len(entry) > 4 else False
            self.add_app_card(section, key, "🎮", name, desc, winget_id, req_admin)

        # ---- Tools with no winget package ---------------------------
        for key, glyph, name, desc, url in GAMING_LINKS:
            self.add_url_card(section, key, glyph, name, desc, url)

        # ---- Preset profile ------------------------------------------
        section = self.add_section("🚀  Preset Profiles")
        self.add_batch_button(
            section, "gaming_essentials", "🚀", "Gamer Essentials Profile",
            "Silent batch install of DirectX, VC++ Runtimes, Discord, Steam, "
            "7-Zip and MSI Afterburner.",
        )
