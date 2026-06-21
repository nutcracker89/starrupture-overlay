using System;
using Serilog;
using System.IO;
using System.Linq;
using System.Collections.Generic;
using CUE4Parse.Compression;
using CUE4Parse.Encryption.Aes;
using CUE4Parse.FileProvider;
using CUE4Parse.MappingsProvider;
using CUE4Parse.MappingsProvider.Usmap;
using CUE4Parse.UE4.Objects.Core.Misc;
using CUE4Parse.UE4.Versions;
using CUE4Parse.UE4.Assets.Exports.Texture;
using CUE4Parse_Conversion.Textures;
using SkiaSharp;

class Program
{
    const string Paks  = @"F:\SteamLibrary\steamapps\common\StarRupture\StarRupture\Content\Paks";
    const string Usmap = @"F:\sr_dump\sdk\usmap\5.6.1-120722+++Earth20+Release-CU1-HF5-StarRupture-CLIENT.usmap";
    const string OutDir = @"F:\sr_extract\out";

    static void Main(string[] args)
    {
        Serilog.Log.Logger = new Serilog.LoggerConfiguration()
            .MinimumLevel.Verbose().WriteTo.Console().CreateLogger();
        // Oodle (needed for IoStore .ucas decompression) — auto-downloads if missing
        OodleHelper.Initialize();

        var provider = new DefaultFileProvider(Paks, SearchOption.AllDirectories, false,
            new VersionContainer(EGame.GAME_UE5_6));
        provider.Initialize();
        provider.MappingsContainer = new FileUsmapTypeMappingsProvider(Usmap);
        provider.Mount();          // mounts unencrypted .pak + .utoc containers
        provider.PostMount();

        Console.WriteLine($"mounted: {provider.Files.Count} files");
        Console.WriteLine($"MountedVfs={provider.MountedVfs.Count} UnloadedVfs={provider.UnloadedVfs.Count}");
        Console.WriteLine($".uasset count={provider.Files.Keys.Count(k => k.EndsWith(".uasset"))}");
        foreach (var k in provider.RequiredKeys) Console.WriteLine($"REQUIRED AES key for guid: {k}");
        foreach (var v in provider.UnloadedVfs) Console.WriteLine($"UNLOADED: {v.Name}");

        string mode = args.Length > 0 ? args[0] : "list";

        if (mode == "list")
        {
            var paths = provider.Files.Keys.OrderBy(p => p).ToArray();
            File.WriteAllLines(@"F:\sr_extract\filelist.txt", paths);
            // quick peek: anything iconish
            var hits = paths.Where(p => {
                var l = p.ToLowerInvariant();
                return l.Contains("icon") || l.Contains("/items/") || l.Contains("itemdata") ||
                       l.Contains("/ui/") || l.Contains("thumbnail") || l.Contains("recipe");
            }).Take(80);
            Console.WriteLine("--- sample icon-ish paths ---");
            foreach (var h in hits) Console.WriteLine(h);
            return;
        }

        if (mode == "json")
        {
            var pkgPath = args[1];
            var pkg = provider.LoadPackage(pkgPath);
            var json = Newtonsoft.Json.JsonConvert.SerializeObject(pkg.GetExports(), Newtonsoft.Json.Formatting.Indented);
            File.WriteAllText(@"F:\sr_extract\dump.json", json);
            Console.WriteLine($"wrote dump.json ({json.Length} chars) for {pkgPath}");
            return;
        }

        if (mode == "foundable")
        {
            // list a sample of the Foundable tree to understand item->icon layout
            foreach (var k in provider.Files.Keys.Where(k => k.Contains("/Items/Foundable/")).OrderBy(k => k).Take(60))
                Console.WriteLine(k);
            return;
        }

        if (mode == "export")
        {
            Directory.CreateDirectory(OutDir);
            var subs = args.Skip(1).Select(s => s.ToLowerInvariant()).ToArray();
            if (subs.Length == 0) subs = new[] { "icon" };
            int ok = 0, tried = 0;
            foreach (var kv in provider.Files)
            {
                var path = kv.Key;
                if (!path.EndsWith(".uasset", StringComparison.OrdinalIgnoreCase)) continue;
                var lp = path.ToLowerInvariant();
                if (!subs.Any(s => lp.Contains(s))) continue;
                tried++;
                try
                {
                    var pkg = provider.LoadPackage(path);
                    foreach (var exp in pkg.GetExports())
                    {
                        if (exp is UTexture2D tex)
                        {
                            var ctex = tex.Decode(ETexturePlatform.DesktopMobile);
                            if (ctex == null) continue;
                            using var bmp = ctex.ToSkBitmap();
                            if (bmp == null) continue;
                            using var img = SKImage.FromBitmap(bmp);
                            using var data = img.Encode(SKEncodedImageFormat.Png, 100);
                            var name = exp.Name;
                            var dest = Path.Combine(OutDir, name + ".png");
                            File.WriteAllBytes(dest, data.ToArray());
                            ok++;
                        }
                    }
                }
                catch (Exception e) { /* skip bad asset */ _ = e; }
            }
            Console.WriteLine($"exported {ok} textures (from {tried} matching packages) -> {OutDir}");
            return;
        }

        Console.WriteLine("usage: srextract [list | export <substr>...]");
    }
}
