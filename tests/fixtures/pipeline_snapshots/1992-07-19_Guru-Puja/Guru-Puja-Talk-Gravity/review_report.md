# Language Review – 1992-07-19_Guru-Puja

## Process

Review `transcript_uk.txt` (full paragraphed Ukrainian text) using 2 parallel reviewers + 1 critic filter.

### Review Agents

**Reviewer L** -- Language (Orthography + Grammar + Punctuation)
**Reviewer S** -- SY Domain (Capitalization + Terminology + Consistency)
**Critic** -- Filter + Validate

## Results

### L. Language (Orthography + Grammar + Punctuation)
| # | Paragraph | Error | Context | Fix |
|---|-----------|-------|---------|-----|
| L1 | 17 | Semicolon before relative clause `яка` -- should be comma per Ukrainian punctuation rules | `Божественна Сила; яка виглядає дуже легкою` | `Божественна Сила, яка виглядає дуже легкою` |
| L2 | 23 | Missing comma before comparative `як` (comma required before comparative clause) | `не виросте як кокосова пальма` | `не виросте, як кокосова пальма` |
| L3 | 10 | Missing commas around appositive `як сахаджа йоґ` (identity phrase requires comma separation) | `і як сахаджа йоґ це стає вашим знанням` | `і, як сахаджа йоґ, це стає вашим знанням` |

### S. SY Domain (Capitalization + Terminology + Consistency)
| # | Paragraph | Error | Context | Fix |
|---|-----------|-------|---------|-----|
| S1 | 37 | `реалізацію` lowercase -- should be capitalized (Self-realization, spiritual concept per glossary: `Realization` -> `Реалізація`). Already correct in para 19: `сили давати Реалізацію іншим` | `ви отримали реалізацію, абсолютно безкоштовно` | `ви отримали Реалізацію, абсолютно безкоштовно` |
| S2 | 37 | `реалізацію` lowercase | `отримали свою реалізацію, і якщо` | `отримали свою Реалізацію, і якщо` |
| S3 | 37 | `реалізацією` lowercase | `за реалізацією, ви повинні` | `за Реалізацією, ви повинні` |
| S4 | 41 | `реалізацію` lowercase | `як давати реалізацію` | `як давати Реалізацію` |
| S5 | 41 | `реалізацію` lowercase | `давали реалізацію – дотепер` | `давали Реалізацію – дотепер` |
| S6 | 43 | `реалізації` lowercase | `метою нашої реалізації або` | `метою нашої Реалізації або` |
| S7 | 43 | `реалізацію` lowercase | `давати реалізацію іншим` | `давати Реалізацію іншим` |
| S8 | 56 | `реалізації` lowercase | `не матиме реалізації!` | `не матиме Реалізації!` |
| S9 | 56 | `реалізацію` lowercase | `будь ласка, реалізацію?` | `будь ласка, Реалізацію?` |

### Critic Filter
| Source | # | Verdict | Reason |
|--------|---|---------|--------|
| L | L1 | **Keep** | Genuine punctuation error: Ukrainian grammar requires a comma (not semicolon) before relative pronoun `яка` |
| L | L2 | **Keep** | Genuine punctuation error: comparative clause with `як` requires a preceding comma in Ukrainian |
| L | L3 | **Keep** | Appositive phrase `як сахаджа йоґ` (in the capacity of) requires comma separation; EN source also has commas: `and, as a Sahaja Yogi, it becomes` |
| S | S1 | **Keep** | Glossary maps `Realization` -> `Реалізація` (capitalized); all 9 instances refer to spiritual Self-realization; already correctly capitalized in para 19 -- inconsistency |
| S | S2--S9 | **Keep** | Same root cause as S1: inconsistent capitalization of the spiritual term `Реалізація` |

### Approved Corrections
| # | Paragraph | Error | Fix |
|---|-----------|-------|-----|
| L1 | 17 | Semicolon before `яка` | `;` -> `,` before relative clause |
| L2 | 23 | Missing comma before comparative `як` | Added comma: `виросте, як` |
| L3 | 10 | Missing commas around appositive `як сахаджа йоґ` | Added commas: `і, як сахаджа йоґ, це` |
| S1--S9 | 37, 41, 43, 56 | `реалізацію/реалізацією/реалізації` lowercase | Capitalized to `Реалізацію/Реалізацією/Реалізації` (9 instances) |

### Items reviewed and found correct

The following areas were checked and confirmed correct (no corrections needed):

- **Deity pronoun capitalization**: Shri Mataji pronouns (Я/Мене/Мій/Мною/Мені) consistently uppercase in 40+ instances throughout. God/Incarnation pronouns (Він/Його/Йому) uppercase when referring to God. Regular person pronouns lowercase. Pronouns at sentence start follow standard capitalization.
- **Quotation marks**: All quotes use Ukrainian `«»` style at all nesting levels, including complex nested dialogue in paras 54--55.
- **En-dash usage**: Consistently ` – ` with spaces throughout.
- **Ellipsis**: Correctly formatted as `...` (three dots, no space before).
- **Glossary terms**: `Сахаджа Йоґа`, `сахаджа йоґ/йоґи`, `Кундаліні`, `Рітамбхара Праг'я`, `Парамчайтанья`, `Брахмачайтанья`, `Сакші`, `Принцип Ґуру`, `Мати Земля`, `бхакті`, `бадхи`, `Нірвічар` -- all match glossary.
- **Locative forms**: `в Сахаджа Йозі` (correct ґ->з alternation per `terms_context.yaml`), `в ґуру паді` (locative), `ґуру пади` (genitive) -- all correct.
- **Spiritual term capitalization**: `Дух` (para 28), `Істина/Істини` (paras 18, 46, 52), `Пуджа` (title), `Царство Боже/Божому/Бога` -- all uppercase per rules.
- **Language names**: `англійська` lowercase (para 4).
- **Transliterations**: `Санґамнер`, `Пратіштхан`, `Вільям Блейк`, `бхакті ґам'я`, `суті кара` -- all correct per transliteration conventions.
- **Spelling and word forms**: No mixed Latin/Cyrillic characters detected. Verb conjugations, gender agreement, and case forms correct throughout.
- **Divine Power references**: `Божественна Сила`, `Всепроникна Сила`, `Космічна Сила` consistently capitalized.
- **Sanskrit `g` convention**: `Ґуру`, `ґуру`, `Сахаджа Йоґа`, `Рітамбхара Праг'я` -- all use `ґ` for Sanskrit `g` per CLAUDE.md.
- **Non-Sanskrit words**: `гірлянду` (para 31) -- correctly uses `г` (French loanword, not Sanskrit).

## Summary

- Language (L): 3 issues found, 3 approved by Critic
- SY Domain (S): 9 issues found (1 root cause: inconsistent `Реалізація` capitalization), 9 approved by Critic
- Total corrections applied: 12
