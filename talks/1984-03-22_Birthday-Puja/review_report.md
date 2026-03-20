# Language Review – 1984-03-22_Birthday-Puja

## Process

Review `transcript_uk.txt` (full paragraphed Ukrainian text) using 2 parallel reviewers + 1 critic filter.

### Input Format

Full paragraphed text from `transcript_uk.txt` (87 lines, covering both Marathi-translated and English sections of the talk).

## Results

### L. Language (Orthography + Grammar + Punctuation)
| # | Line | Error | Context | Fix |
|---|------|-------|---------|-----|
| L1 | 35 | Incorrect transliteration: "Hall" rendered as "Холі" (reads as "Holi" festival) | `в Мавланкар Холі, і подивіться` | `в Мавланкар Холл` |
| L2 | 35 | Same transliteration error, second occurrence | `програму в Мавланкар Холі – навіть` | `програму в Мавланкар Холл` |
| L3 | 61 | Non-standard verb "відлаяти" (від- prefix with "лаяти" is uncommon; standard perfective: "полаяти") | `потрібно відлаяти дітей` | `потрібно полаяти дітей` |

### S. SY Domain (Capitalization + Terminology + Consistency)
| # | Line | Error | Context | Fix |
|---|------|-------|---------|-----|
| S1 | 16 | "матері-землі" lowercase with hyphen; three divine Shaktis took birth from Mother Earth (sacred entity, glossary: "Бхумі Деві / Мати Земля") | `народилися з матері-землі` | `народилися з Матері Землі` |
| S2 | 41 | "(сіддхі)" = siddhis (supernatural powers); EN says "(Siddha)" = accomplished/perfected being – different concept | `розвинули (сіддхі)` | `розвинули (сіддха)` |

### Critic Filter
| Source | # | Verdict | Reason |
|--------|---|---------|--------|
| L | L1 | Keep | Clear transliteration error. English "Hall" /hɔːl/ → Ukrainian "Холл" or "Хол", not "Холі" which corresponds to "Holi" (Indian festival of colors). |
| L | L2 | Keep | Same error as L1, second occurrence in the same paragraph. |
| L | L3 | Remove | Borderline: "відлаяти" is non-standard but understandable in informal speech context. Ukrainian speakers routinely create ad hoc prefixed verbs. Not a clear-cut error, more a stylistic preference. |
| S | S1 | Keep | The three powers (Shri Mahakali, Shri Mahalakshmi, Shri Mahasaraswati) took birth from Mother Earth – a sacred concept in SY. Glossary specifies "Мати Земля" (capitalized, no hyphen). |
| S | S2 | Keep | EN unambiguously writes "(Siddha)" meaning "accomplished/perfected one." The translator used "сіддхі" (siddhis = supernatural powers/accomplishments), which shifts the meaning. Correct form: "(сіддха)". |

### Approved Corrections
| # | Line | Error | Fix |
|---|------|-------|-----|
| 1 | 16 | `матері-землі` (lowercase, hyphen) | `Матері Землі` (capitalized, no hyphen) |
| 2 | 35 | `Мавланкар Холі` (1st occurrence) | `Мавланкар Холл` |
| 3 | 35 | `Мавланкар Холі` (2nd occurrence) | `Мавланкар Холл` |
| 4 | 41 | `(сіддхі)` | `(сіддха)` |

## Summary

- Language (L): 3 issues found, 2 approved by Critic
- SY Domain (S): 2 issues found, 2 approved by Critic
- Total corrections applied: 4

## Quality Notes

The translation is of high quality overall:
- Shri Mataji's pronoun capitalization (Я/Мій/Мене/Моя/Вона/Її/Їй) is consistently correct throughout
- Quotation marks use «» consistently at all levels
- En-dash ` – ` with spaces is used correctly throughout
- Ellipsis `...` is used correctly (no space before)
- Glossary terms (Кундаліні, Сахасрара, Аґія, Екадаша, бхути, Дхарма, Пуджа, Дух, сахаджа йоґи) are all correct
- Locative form "Сахаджа Йозі" is used consistently and correctly
- Language names (маратхі, гінді, англійська) are correctly lowercase
- God's pronoun "Він" is correctly uppercase (line 84)
