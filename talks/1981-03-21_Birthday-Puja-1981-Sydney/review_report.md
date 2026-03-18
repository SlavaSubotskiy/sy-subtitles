# Language Review – 1981-03-21_Birthday-Puja-1981-Sydney

## Process

Review `transcript_uk.txt` (full paragraphed Ukrainian text) using 2 parallel reviewers + 1 critic filter.
This is the second review round. Prior round fixed 3 issues (gender agreement, manґо spelling, one nested quote). One prior issue (nested quotes in para 32) remained unfixed and is included below.

## Results

### L. Language (Orthography + Grammar + Punctuation)
| # | Paragraph | Error | Context | Fix |
|---|-----------|-------|---------|-----|
| L1 | 9 | Latin 'e' (U+0065) mixed with Cyrillic text in word | `піднімeться` | `підніметься` (Cyrillic 'е' U+0435) |
| L2 | 32 | Nested quotation marks use ASCII `"..."` instead of Ukrainian `«»` (unfixed from prior review) | `він сказав: "Ви знаєте цю жінку?...чеки."` | `він сказав: «Ви знаєте цю жінку?...чеки.»` |
| L3 | 50 | Incorrect apostrophe in imperfective verb form; perfective "розп'яти" → imperfective "розпинати" (no apostrophe) | `розп'инаємо` | `розпинаємо` |

### S. SY Domain (Capitalization + Terminology + Consistency)
| # | Paragraph | Error | Context | Fix |
|---|-----------|-------|---------|-----|
| S1 | 42 | "Pranava" should be capitalized per glossary (sacred concept: Omkara / Pranava → Омкара / Пранава) | `пранава` | `Пранава` |
| S2 | 61 | "Adi Shakti" is two words per glossary ("Шрі Аді Шакті"), not one | `Адішакті` | `Аді Шакті` |

### Critic Filter
| Source | # | Verdict | Reason |
|--------|---|---------|--------|
| L | L1 | Keep | Confirmed programmatically: Latin U+0065 in Cyrillic word. Genuine mixed-script error. |
| L | L2 | Keep | Clear violation of CLAUDE.md quotation mark rules: nested quotes must use `«»`, never `"..."`. |
| L | L3 | Keep | Clear morphological error. Imperfective of "розп'яти" is "розпинати" without apostrophe. |
| S | S1 | Keep | Glossary entry "Omkara / Pranava → Омкара / Пранава" explicitly capitalizes Пранава. |
| S | S2 | Keep | Glossary entry "Shri Adi Shakti → Шрі Аді Шакті" uses two separate words. |

### Approved Corrections
| # | Paragraph | Error | Fix |
|---|-----------|-------|-----|
| 1 | 9 | Latin 'e' in `піднімeться` | `підніметься` |
| 2 | 32 | ASCII quotes `"..."` in nested quote | `«...»` |
| 3 | 50 | Apostrophe in `розп'инаємо` | `розпинаємо` |
| 4 | 42 | Lowercase `пранава` | `Пранава` |
| 5 | 61 | Merged `Адішакті` | `Аді Шакті` |

## Summary

- Language (L): 3 issues found, 3 approved by Critic
- SY Domain (S): 2 issues found, 2 approved by Critic
- Total corrections applied: 5

## Notes

The translation is of high quality overall:
- Deity pronoun capitalization (Shri Mataji, Ganesha, Christ, God) is consistently correct throughout all 68 paragraphs
- All SY terminology matches the glossary: Кундаліні, Муладхара, Сахаджа Йоґа/Йозі, Сакші, etc.
- Declension of "Ґанеша" is correct throughout (Ґанеші/Ґанешу/Ґанешею)
- Locative "Сахаджа Йозі" (ґ->з alternation) used correctly
- Plural forms "сахаджа йоґи/йоґах" follow glossary conventions
- Quotation marks use `«»` consistently (after fix)
- Dashes ` – ` with spaces used consistently
- Spiritual terms correctly capitalized: Дух, Інкарнація, Пуджа
