# Glossary

Sahaja Yoga terminology dictionary (EN → UK) and subtle system reference.

**Status: v3** — 363 terms + chakra system reference.

## Structure

```
glossary/
  terms.yaml           # Main term dictionary (363 terms)
  chakra_system.yaml   # Subtle system reference (chakras, deities, channels, mantras)
  corpus/              # Cached EN+UK transcripts from amruta.org (gitignored)
    index.yaml         # Talk listing (38 talks)
    {slug}/en.txt      # English transcript
    {slug}/uk.txt      # Ukrainian transcript
  README.md            # This file
```

## terms.yaml — Term Sections

### Original (from 1983-07-24 Guru Puja)

| Section | Description |
|---|---|
| Subtle System | Chakras, nadis, energy (Kundalini, Sahasrara, Agnya, Vishuddhi, etc.) |
| Spiritual States | Self-realization, atita, akarma, avir bhava, samadhi |
| Key Concepts | Guru Principle, Dharma, protocol, tapasya, Incarnation, gunas |
| Puja and Rituals | Puja, sankalpa, abhisheka, Havan, mantra |
| Deities and Sacred Figures | Shri Mataji, Adi Shakti, Dattatreya, Shiva, Krishna, Ganesha, Jesus |
| Sacred Geography | Tamasa/Thames, Kailasha, desha/Pradesh |
| Puja Terminology | sakshat, namoh namaha, baddhas, siddhis |
| Translation Notes | Capitalization rules for deity pronouns, spiritual terms |

### Corpus terms (from 38-talk corpus)

18 thematic sections: Subtle System, Three Powers, Deities, Ganesha Epithets, Epic Figures, Saints, Avatars, Cosmic Concepts, Spiritual States, Ananda types, Practices, Sacred Texts, Geography, Festivals, Social Roles, Ayurvedic, Other.

### Book terms (from SY Mantrabook EN 2025 / UK 2014)

| Section | Description |
|---|---|
| Deities and Sacred Figures | Durga, Jagadamba, Hanumana, 10 Primordial Masters, Mary, Fatima, etc. |
| Incarnations of Vishnu | Varaha, Narasimha, Vamana, Parashurama |
| Spiritual Concepts | Advaita, Karma, Moksha, Six Enemies, Turiya, Prana/Mana/Laya, etc. |
| Chakra-Related | Lalita, Shri Chakra, Manipura, Ardha Bindu, Bindu, Valaya, Granthi |
| Ritual/Practice | Foot-soaking, Shoe-beating, Matka, Raising Kundalini, etc. |
| Scriptures | Ganesha Atharva Shirsha, Bhagavad Gita, Vedas, Puranas, Kavach, etc. |
| Cosmic Terms | Brahman, Parabrahman, Trimurti, Avatar, Deva/Devi, etc. |

## chakra_system.yaml — Subtle System Reference

Structured reference for the translator agent, covering:
- All 7 main chakras + sub-chakras (Hamsa, Lalita, Shri Chakra, Ekadasha Rudra)
- Deities per chakra (left/centre/right) with EN + UK names
- Three channels (Ida, Pingala, Sushumna) with qualities
- Three gunas, 10 Primordial Masters, 10 Incarnations of Vishnu
- Six Enemies, Three Granthis, Bija Mantras
- Above-Sahasrara centres, Deity relationships
- Affirmations, mantras, country-chakra correspondences

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
