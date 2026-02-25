# Glossary

Sahaja Yoga terminology dictionary (EN → UK) and subtle system reference.

**Status: v4** — 374 terms + chakra system reference. Optimized for LLM translator agent.

## Structure

```
glossary/
  terms_lookup.yaml    # Quick EN → UK mapping (374 terms, ~19 KB)
  terms_context.yaml   # Disambiguation context for ~68 ambiguous terms (~14 KB)
  chakra_map.yaml      # Chakra/deity/channel EN → UK mapping (~12 KB)
  chakra_system.yaml   # Full subtle system reference (on-demand, ~51 KB)
  corpus/              # Cached EN+UK transcripts from amruta.org (gitignored)
    index.yaml         # Talk listing (38 talks)
    {slug}/en.txt      # English transcript
    {slug}/uk.txt      # Ukrainian transcript
  CLAUDE.md            # Translator agent instructions
  README.md            # This file
```

## Agent Loading Strategy

| File | When to load | Size |
|---|---|---|
| `terms_lookup.yaml` | Always | ~19 KB |
| `terms_context.yaml` | Always | ~14 KB |
| `chakra_map.yaml` | Always | ~12 KB |
| **Total (always)** | | **~45 KB** |
| `chakra_system.yaml` | On demand (deep subtle system topics) | ~51 KB |

## terms_lookup.yaml

All 374 terms as clean `en` / `uk` pairs without context. Organized by thematic sections:
Subtle System, Spiritual States, Key Concepts, Puja and Rituals, Deities, Sacred Geography, etc.

## terms_context.yaml

~68 terms that need disambiguation context:
- Terms with variant Ukrainian translations (`/` in `uk` field)
- Gender-specific forms (сахаджа йоґ / сахаджа йоґиня)
- Non-obvious translations (catching → блокування, surrender → віддача на милість)
- Dialogue labels (ШМ, СЙ)

## chakra_map.yaml

Translation-oriented extract from `chakra_system.yaml`:
- 9 main chakras with deity names (left/centre/right) EN → UK
- 4 sub-chakras (Hamsa, Lalita, Shri Chakra, Ekadasha Rudra)
- 7 above-Sahasrara centres
- 3 channels (Ida, Pingala, Sushumna)
- 10 Primordial Masters, 10 Incarnations of Vishnu
- 14 other deities, 13 scripture names
- Mantra formula reference

## chakra_system.yaml — Full Reference

Complete subtle system encyclopedia (loaded on demand):
- Etymologies, Sanskrit IAST, meanings
- Body part projections, colors, petals, elements
- Six Enemies with remedies and mantras
- Affirmations (centre/left/right) in Ukrainian
- Bija mantras, sacred word mantras
- Three Granthis, Three Gunas, Three Great Mantras

## Transliteration Conventions

Follows the Ukrainian Mantra Book (Книга Мантр Сахаджа Йоґи, Київ, 2014):

| Convention | Rule | Example |
|---|---|---|
| Sanskrit 'g' | ґ (not г) | Ґанеша, Аґія, Ґуру |
| Aspirate 'dh' | дх | бандхан, Свадхістхана, Вішуддхі |
| Sanskrit short 'i' | і | Шіва, Садашіва |

## Sources

- SY Mantrabook, UK Slim Edition 2025 (English)
- Книга Мантр Сахаджа Йоґи, 3rd ed., Kyiv 2014 (Ukrainian)
- 38 Ukrainian-translated talks from amruta.org (1970–2008)
- 1983-07-24 Guru Puja, Lodge Hill, UK (original analysis)
