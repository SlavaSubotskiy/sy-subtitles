# Glossary

Sahaja Yoga terminology dictionary (EN → UK).

**Status: v2** — 230 terms from 38 talks corpus.

## Structure

```
glossary/
  terms.yaml       # Main term dictionary (230 terms)
  corpus/           # Cached EN+UK transcripts from amruta.org (gitignored)
    index.yaml      # Talk listing (38 talks)
    {slug}/en.txt   # English transcript
    {slug}/uk.txt   # Ukrainian transcript
  README.md         # This file
```

## Sections in terms.yaml

### Original (from 1983-07-24 Guru Puja)

| Section | Description |
|---|---|
| Subtle System | Chakras, nadis, energy (Kundalini, Sahasrara, Agnya, Vishuddhi, etc.) |
| Spiritual States | Self-realization, atita, akarma, avir bhava, samadhi |
| Key Concepts | Guru Principle, Dharma, protocol, tapasya, Incarnation, gunas |
| Puja and Rituals | Puja, sankalpa, abhisheka, Havan, mantra |
| Deities and Sacred Figures | Shri Mataji, Adi Shakti, Datattreya, Shiva, Krishna, Ganesha, Jesus |
| Sacred Geography | Tamasa/Thames, Kailasha, desha/Pradesh |
| Puja Terminology | sakshat, namoh namaha, baddhas, siddhis |
| Translation Notes | Capitalization rules for deity pronouns, spiritual terms |

### New (from 38-talk corpus, 2026-02-25)

| Section | Description |
|---|---|
| Subtle System | Additional chakras, nadis, energy structures |
| Three Powers of God | Mahasaraswati, Mahalakshmi, Mahakali |
| Deities and Sacred Figures | Extended deity list |
| Ganesha Epithets | Sacred names of Ganesha |
| Epic and Mythological Figures | Ramayana, Mahabharata characters |
| Saints and Sages | Historical spiritual figures |
| Avatars | Incarnations of Vishnu |
| Cosmic Concepts | Cosmology, Virata, Paramchaitanya |
| Spiritual States and Qualities | Nirvikalpa, nirananda, etc. |
| Types of Ananda | Joy classifications |
| Practices and Rituals | Bandhan, shoe-beating, etc. |
| Sacred Texts | Gita, Devi Mahatmyam, etc. |
| Sacred Geography | Prithvi, Vaikuntha, etc. |
| Festivals | Diwali, Navaratri, etc. |
| Social and Spiritual Roles | Guru, rishi, sanyasi |
| Ayurvedic Terms | Healing terminology |
| Other Key Terms | Miscellaneous SY vocabulary |

## Entry Format

```yaml
- en: Kundalini
  uk: Кундаліні
  context: >
    Материнська духовна енергія, що перебуває в крижовій кістці (sacrum bone).
    Піднімається через центральний канал при самореалізації.
```

## Corpus Pipeline

```
amruta.org listing → scrape_listing.py → corpus/index.yaml
                   → fetch_transcripts.py → corpus/{slug}/en.txt + uk.txt
```

## Sources

- 38 Ukrainian-translated talks from amruta.org (1970–2008)
- Primary: 1983-07-24 Guru Puja, Lodge Hill, UK (original analysis)
