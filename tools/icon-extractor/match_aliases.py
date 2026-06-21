"""Second pass: map the remaining iconless items to game icons whose asset name
differs from the item display name (raw-ore variants, Consumable_ eggs, Corp tokens,
the game's 'Syringe' spelling). Crab=Coralion, Fox=Vulpir per the consumable set."""
import json, re, os, shutil

SRC = r"F:\sr_extract\out"
ROOT = r"F:\starrupture_timer"
ICONS_JSON = os.path.join(ROOT, "icons.json")

ALIASES = {
    "Claywood Corp Reputation": "T_ClaywoodCorp_Icon",
    "Clever Corp Reputation":   "T_CleverCorp_Icon",
    "Future Corp Reputation":   "T_FutureCorp_Icon",
    "Griffiths Corp Reputation":"T_GriffithsCorp_Icon",
    "Moon Corp Reputation":     "T_MoonCorp_Icon",
    "Selenian Corp Reputation": "T_SelenianCorp_Icon",
    "Crab Egg":                 "T_Consumable_CrabEgg_Icon",
    "Processed Coralion Egg":   "T_Consumable_CrabEgg_Refined_Icon",
    "Fox Egg":                  "T_Consumable_FoxEgg_Icon",
    "Refined Vulpir Egg":       "T_Consumable_FoxEgg_Refined_Icon",
    "Vulpir Meal":              "T_Consumable_FoxMeal_Icon",
    "Goethite":                 "T_GoethiteOre_Icon",
    "Quartz":                   "T_QuartzOre_Icon",
    "Sulphur":                  "T_SulphurOre_Icon",
    "Magic Oil":                "T_MagicOilOre_Icon",
    "Syrigne":                  "T_Syringe_Icon",
    "FE_Battery":               "T_Battery_Icon",
    "Sulfuric Acid":            "T_SulphuricAcid_Icon",
    "Sulfur Ore":               "T_SulphurOre_Icon",
    "Nanofiber":                "T_Nanofibre_Icon",
    "Helium-3":                 "T_HeliumOre_Icon",
}

icons = json.load(open(ICONS_JSON, encoding="utf-8"))
added = 0
for disp, tex in ALIASES.items():
    src = os.path.join(SRC, tex + ".png")
    if not os.path.exists(src):
        print(f"  MISSING source: {tex}")
        continue
    slug = re.sub(r"[^a-z0-9]+", "_", disp.lower()).strip("_")
    rel = f"icons/{slug}.png"
    shutil.copy(src, os.path.join(ROOT, rel))
    icons[disp] = rel
    added += 1

json.dump(icons, open(ICONS_JSON, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
print(f"added {added} alias icons -> icons.json now {len(icons)} entries")
