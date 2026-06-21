using System;
using Serilog;
using System.IO;
using System.Net.Http;
using System.Text;
using System.Linq;
using System.Text.RegularExpressions;
using System.Collections.Generic;
using CUE4Parse.Compression;
using CUE4Parse.FileProvider;
using CUE4Parse.MappingsProvider;
using CUE4Parse.MappingsProvider.Usmap;
using CUE4Parse.UE4.Versions;
using CUE4Parse.UE4.Assets.Exports.Texture;
using CUE4Parse_Conversion.Textures;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using SkiaSharp;

// StarRupture icon extractor — turnkey.
// Double-click in your overlay folder (next to recipes.json + a .usmap). It finds
// your Steam copy of the game, pulls the item icons, and fills icons/ + icons.json.
class Program
{
    // item icons that match by a name different from the display name
    static readonly Dictionary<string, string> ALIASES = new()
    {
        ["Claywood Corp Reputation"] = "T_ClaywoodCorp_Icon",
        ["Clever Corp Reputation"]   = "T_CleverCorp_Icon",
        ["Future Corp Reputation"]   = "T_FutureCorp_Icon",
        ["Griffiths Corp Reputation"]= "T_GriffithsCorp_Icon",
        ["Moon Corp Reputation"]     = "T_MoonCorp_Icon",
        ["Selenian Corp Reputation"] = "T_SelenianCorp_Icon",
        ["Crab Egg"]                 = "T_Consumable_CrabEgg_Icon",
        ["Processed Coralion Egg"]   = "T_Consumable_CrabEgg_Refined_Icon",
        ["Fox Egg"]                  = "T_Consumable_FoxEgg_Icon",
        ["Refined Vulpir Egg"]       = "T_Consumable_FoxEgg_Refined_Icon",
        ["Vulpir Meal"]              = "T_Consumable_FoxMeal_Icon",
        ["Goethite"]                 = "T_GoethiteOre_Icon",
        ["Quartz"]                   = "T_QuartzOre_Icon",
        ["Sulphur"]                  = "T_SulphurOre_Icon",
        ["Magic Oil"]                = "T_MagicOilOre_Icon",
        ["Syrigne"]                  = "T_Syringe_Icon",
        ["FE_Battery"]               = "T_Battery_Icon",
        ["Sulfuric Acid"]            = "T_SulphuricAcid_Icon",   // US spelling
        ["Sulfur Ore"]               = "T_SulphurOre_Icon",
        ["Nanofiber"]                = "T_Nanofibre_Icon",       // US spelling
        ["Helium-3"]                 = "T_HeliumOre_Icon",
    };

    static string Norm(string s) => Regex.Replace((s ?? "").ToLowerInvariant(), "[^a-z0-9]", "");

    static string IconKey(string fn)
    {
        var k = Regex.Replace(fn, "^T_", "");
        k = Regex.Replace(k, "_?Icon$", "");
        k = Regex.Replace(k, "(?i)blueprint", "");
        k = Regex.Replace(k, "(?i)_?recv2", "");
        return Norm(k);
    }

    static int VariantPri(string fn)
    {
        var l = fn.ToLowerInvariant();
        if (l.Contains("recv2") || l.Contains("rec_v2")) return 2;
        if (l.Contains("blueprint")) return 1;
        return 0; // plain item icon = best
    }

    static void Main(string[] args)
    {
        Console.OutputEncoding = Encoding.UTF8;
        Log.Logger = new LoggerConfiguration().MinimumLevel.Error().WriteTo.Console().CreateLogger();
        try { Run(args); }
        catch (Exception e) { Console.WriteLine("\nERROR: " + e.Message); }
        if (!args.Contains("--no-pause"))
        {
            Console.WriteLine("\nPress any key to close...");
            try { Console.ReadKey(); } catch { }
        }
    }

    static void Run(string[] args)
    {
        string exeDir = AppContext.BaseDirectory;
        string overlayDir = GetArg(args, "--overlay") ?? FindOverlayDir(exeDir);
        if (overlayDir == null)
        {
            Console.WriteLine("Could not find recipes.json. Put this exe in your StarRupture overlay folder");
            Console.WriteLine("(next to recipes.json and icons.json), then run it again.");
            return;
        }
        string usmap = GetArg(args, "--usmap") ?? FindUsmap(exeDir, overlayDir) ?? DownloadUsmap(exeDir);
        if (usmap == null)
        {
            Console.WriteLine("Could not find or download a .usmap mappings file.");
            Console.WriteLine("Grab the StarRupture CLIENT .usmap from AlienX's SDK and drop it next to this exe:");
            Console.WriteLine("  https://github.com/AlienXAXS/StarRupture-Game-SDK/tree/main/usmap");
            return;
        }
        string paks = GetArg(args, "--paks") ?? AutoDetectPaks();
        if (paks == null)
        {
            Console.WriteLine("Could not auto-find your StarRupture install. Pass it manually:");
            Console.WriteLine(@"  srextract.exe --paks ""<...>\StarRupture\StarRupture\Content\Paks""");
            return;
        }

        Console.WriteLine($"Game paks : {paks}");
        Console.WriteLine($"Mappings  : {Path.GetFileName(usmap)}");
        Console.WriteLine($"Overlay   : {overlayDir}");
        Console.WriteLine("\nMounting game (first run downloads the oodle dll)...");

        OodleHelper.Initialize();
        var provider = new DefaultFileProvider(paks, SearchOption.AllDirectories, false,
            new VersionContainer(EGame.GAME_UE5_6));
        provider.Initialize();
        provider.MappingsContainer = new FileUsmapTypeMappingsProvider(usmap);
        provider.Mount();
        provider.PostMount();
        Console.WriteLine($"Mounted {provider.Files.Count} files. Exporting item icons...");

        // decode every /UI/ItemIcons/ texture in memory
        var byNorm = new Dictionary<string, (int pri, byte[] png, string fn)>();
        var byFile = new Dictionary<string, byte[]>();
        int decoded = 0;
        foreach (var path in provider.Files.Keys.Where(k =>
                     k.EndsWith(".uasset", StringComparison.OrdinalIgnoreCase) &&
                     k.ToLowerInvariant().Contains("/ui/itemicons/")))
        {
            try
            {
                var pkg = provider.LoadPackage(path);
                foreach (var exp in pkg.GetExports())
                {
                    if (exp is not UTexture2D tex) continue;
                    var ctex = tex.Decode(ETexturePlatform.DesktopMobile);
                    if (ctex == null) continue;
                    using var bmp = ctex.ToSkBitmap();
                    if (bmp == null) continue;
                    using var img = SKImage.FromBitmap(bmp);
                    using var data = img.Encode(SKEncodedImageFormat.Png, 100);
                    var png = data.ToArray();
                    var fn = exp.Name;
                    byFile[fn] = png;
                    var nk = IconKey(fn);
                    int pri = VariantPri(fn);
                    if (nk.Length > 0 && (!byNorm.TryGetValue(nk, out var cur) || pri < cur.pri))
                        byNorm[nk] = (pri, png, fn);
                    decoded++;
                }
            }
            catch { /* skip bad asset */ }
        }
        Console.WriteLine($"Decoded {decoded} icon textures.");

        // gather item names + existing icons
        var recRoot = JObject.Parse(File.ReadAllText(Path.Combine(overlayDir, "recipes.json")));
        var items = new SortedSet<string>(StringComparer.Ordinal);
        foreach (var r in (JArray)recRoot["recipes"])
        {
            var o = (string)r["output"];
            if (!string.IsNullOrEmpty(o)) items.Add(o);
            if (r["inputs"] is JArray ins)
                foreach (var i in ins) { var it = (string)i["item"]; if (!string.IsNullOrEmpty(it)) items.Add(it); }
        }

        string iconsPath = Path.Combine(overlayDir, "icons.json");
        var icons = File.Exists(iconsPath) ? JObject.Parse(File.ReadAllText(iconsPath)) : new JObject();
        // an item is only "covered" if its mapped PNG actually exists on disk — the
        // shipped icons.json lists names but the PNGs are generated locally (here).
        var existing = new HashSet<string>(icons.Properties()
            .Where(p => File.Exists(Path.Combine(overlayDir, (string)p.Value ?? "")))
            .Select(p => Norm(p.Name)));
        string iconsDir = Path.Combine(overlayDir, "icons");
        Directory.CreateDirectory(iconsDir);

        int added = 0;
        var missing = new List<string>();
        void Write(string disp, byte[] png)
        {
            var slug = Regex.Replace(disp.ToLowerInvariant(), "[^a-z0-9]+", "_").Trim('_');
            var rel = "icons/" + slug + ".png";
            File.WriteAllBytes(Path.Combine(overlayDir, rel), png);
            icons[disp] = rel;
            existing.Add(Norm(disp));
            added++;
        }

        foreach (var disp in items)
        {
            var nk = Norm(disp);
            if (existing.Contains(nk)) continue;
            if (byNorm.TryGetValue(nk, out var hit)) Write(disp, hit.png);
            else missing.Add(disp);
        }
        // alias pass for the leftovers
        foreach (var disp in missing.ToList())
        {
            if (existing.Contains(Norm(disp))) continue;
            if (ALIASES.TryGetValue(disp, out var tex) && byFile.TryGetValue(tex, out var png))
            {
                Write(disp, png);
                missing.Remove(disp);
            }
        }

        File.WriteAllText(iconsPath, icons.ToString(Formatting.Indented), new UTF8Encoding(false));
        Console.WriteLine($"\nDone. Added {added} game icons. icons.json now has {icons.Count} entries.");
        if (missing.Count > 0)
            Console.WriteLine($"No game icon found for {missing.Count} items (they'll show as text tiles): "
                              + string.Join(", ", missing));
        Console.WriteLine("\nNow run the overlay (or build.bat) — the real icons will show up.");
    }

    static string GetArg(string[] args, string name)
    {
        int i = Array.IndexOf(args, name);
        return (i >= 0 && i + 1 < args.Length) ? args[i + 1] : null;
    }

    static string FindOverlayDir(string exeDir)
    {
        foreach (var d in new[] { exeDir, Directory.GetCurrentDirectory(), Directory.GetParent(exeDir)?.FullName })
            if (d != null && File.Exists(Path.Combine(d, "recipes.json"))) return d;
        return null;
    }

    static string FindUsmap(string exeDir, string overlayDir)
    {
        foreach (var d in new[] { exeDir, overlayDir, Directory.GetCurrentDirectory() })
        {
            if (d == null || !Directory.Exists(d)) continue;
            var f = Directory.GetFiles(d, "*.usmap").FirstOrDefault();
            if (f != null) return f;
        }
        return null;
    }

    static string DownloadUsmap(string exeDir)
    {
        try
        {
            const string fn = "5.6.1-120722+++Earth20+Release-CU1-HF5-StarRupture-CLIENT.usmap";
            var url = "https://raw.githubusercontent.com/AlienXAXS/StarRupture-Game-SDK/main/usmap/"
                      + Uri.EscapeDataString(fn);
            Console.WriteLine("No .usmap found locally — downloading mappings from AlienX's SDK...");
            using var http = new HttpClient();
            var bytes = http.GetByteArrayAsync(url).GetAwaiter().GetResult();
            var dest = Path.Combine(exeDir, "StarRupture-CLIENT.usmap");
            File.WriteAllBytes(dest, bytes);
            Console.WriteLine($"  saved {bytes.Length / 1024} KB -> {Path.GetFileName(dest)}");
            return dest;
        }
        catch (Exception e) { Console.WriteLine("  download failed: " + e.Message); return null; }
    }

    static string AutoDetectPaks()
    {
        const string tail = @"steamapps\common\StarRupture\StarRupture\Content\Paks";
        var libs = new List<string>();
        foreach (var drive in DriveInfo.GetDrives().Where(d => d.IsReady && d.DriveType == DriveType.Fixed))
        {
            var root = drive.RootDirectory.FullName;
            libs.Add(Path.Combine(root, "SteamLibrary"));
            libs.Add(Path.Combine(root, "Steam"));
            libs.Add(Path.Combine(root, "Games", "Steam"));
            libs.Add(Path.Combine(root, "Program Files (x86)", "Steam"));
        }
        // parse libraryfolders.vdf from any steam dir we can find
        foreach (var steam in libs.ToList())
        {
            var vdf = Path.Combine(steam, "steamapps", "libraryfolders.vdf");
            if (!File.Exists(vdf)) continue;
            foreach (Match m in Regex.Matches(File.ReadAllText(vdf), "\"path\"\\s*\"(.*?)\""))
                libs.Add(m.Groups[1].Value.Replace("\\\\", "\\"));
        }
        foreach (var lib in libs.Distinct())
        {
            var p = Path.Combine(lib, tail);
            if (Directory.Exists(p)) return p;
        }
        return null;
    }
}
