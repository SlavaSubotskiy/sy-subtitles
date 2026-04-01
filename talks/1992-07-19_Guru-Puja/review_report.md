# Language Review – 1992-07-19_Guru-Puja

## Process

Review `transcript_uk.txt` (full paragraphed Ukrainian text) using 2 parallel reviewers + 1 critic filter.

### Input Format

Full paragraphed text from `transcript_uk.txt` (61 lines, 60 paragraphs of Guru Puja talk).

## Results — Pass 1 (7 corrections, applied)

### L. Language (Orthography + Grammar + Punctuation)
| # | Paragraph | Error | Context | Fix |
|---|-----------|-------|---------|-----|
| L1 | 57 | Wrong case: accusative «яку» instead of dative with «кидати виклик» | «у вірі, яку нині кидають виклик» | «у вірі, якій нині кидають виклик» |
| L2 | 10 | Missing commas around appositive «як сахаджа йоґ» | «і як сахаджа йоґ це стає вашим знанням» | «і, як сахаджа йоґ, це стає вашим знанням» |
| L3 | 52 | Missing commas around comparative insertion «як Я» | «людина як Я обговорювала банківську справу» | «людина, як Я, обговорювала банківську справу» |
| L4 | 16 | Missing comma after «Отже» (inconsistent with all other 10+ usages in text) | «Отже тепер, коли ви починаєте» | «Отже, тепер, коли ви починаєте» |

### S. SY Domain (Capitalization + Terminology + Consistency)
| # | Paragraph | Error | Context | Fix |
|---|-----------|-------|---------|-----|
| S1 | 28 | Shri Mataji's first-person pronoun lowercase | «ідеї аскетизму, я не знаю, звідки» | «ідеї аскетизму, Я не знаю, звідки» |
| S2 | 29 | Shri Mataji's first-person pronoun lowercase | «слабких точок, я думаю» | «слабких точок, Я думаю» |
| S3 | 25 | Divine Power pronoun lowercase (inconsistent with para 23-24 where «Вона» is uppercase) | «Ця Сила не лише сповнена співчуття, вона також гнівна, вона гнівна.» | «...Вона також гнівна, Вона гнівна.» |

### Critic Filter — Pass 1
| Source | # | Verdict | Reason |
|--------|---|---------|--------|
| L | L1 | Keep | Clear grammar error: «кидати виклик» governs dative (кому?/чому?), not accusative |
| L | L2 | Keep | Appositive phrase «як сахаджа йоґ» requires comma separation per Ukrainian punctuation rules |
| L | L3 | Keep | Comparative insertion «як Я» requires comma separation; same pattern as L2 |
| L | L4 | Keep | All other 10+ instances of «Отже» in the text are followed by comma; this is the sole inconsistency |
| S | S1 | Keep | SM is the speaker narrating; all other ~40 instances of Her first-person pronoun in the text are uppercase |
| S | S2 | Keep | Same as S1; SM speaking about herself in first person |
| S | S3 | Keep | EN source has uppercase "It" for the Divine Power; para 23 has «Вона настільки ефективна», para 24 has «Вона у вашому розпорядженні» — both uppercase. Para 25 should match |

## Results — Pass 2 (2 additional corrections, applied)

### L. Language (Orthography + Grammar + Punctuation)
| # | Paragraph | Error | Context | Fix |
|---|-----------|-------|---------|-----|
| L5 | 31 | Incorrect ґ in non-Sanskrit word | «звичайну ґірлянду з тулсі» — "гірлянда" is a standard Ukrainian word (from French "guirlande"); the ґ convention applies only to Sanskrit/Hindi terms | «звичайну гірлянду з тулсі» |

### S. SY Domain (Capitalization + Terminology + Consistency)
| # | Paragraph | Error | Context | Fix |
|---|-----------|-------|---------|-----|
| S4 | 19 | Inconsistent capitalization of «реалізація» | «сили давати Реалізацію іншим» — all other 6 instances (paras 37, 41, 43, 56) use lowercase; glossary lists standalone form as lowercase | «сили давати реалізацію іншим» |

### Critic Filter — Pass 2
| Source | # | Verdict | Reason |
|--------|---|---------|--------|
| L | L5 | Keep | "Гірлянда" is a standard Ukrainian word borrowed from French centuries ago; the ґ transliteration convention in CLAUDE.md explicitly applies to "Sanskrit 'g'" only |
| S | S4 | Keep | Standalone «реалізація» is listed lowercase in the glossary. 6 out of 7 instances use lowercase. One uppercase instance is an inconsistency that should be normalized |

### All Approved Corrections (Pass 1 + Pass 2)
| # | Paragraph | Error | Fix |
|---|-----------|-------|-----|
| L1 | 57 | Wrong case «яку» with «кидати виклик» | «якій нині кидають виклик» |
| L2 | 10 | Missing commas around appositive | «і, як сахаджа йоґ, це стає» |
| L3 | 52 | Missing commas around comparison | «людина, як Я, обговорювала» |
| L4 | 16 | Missing comma after «Отже» | «Отже, тепер, коли» |
| L5 | 31 | Incorrect ґ in non-Sanskrit word | «гірлянду з тулсі» |
| S1 | 28 | SM pronoun lowercase | «Я не знаю» |
| S2 | 29 | SM pronoun lowercase | «Я думаю» |
| S3 | 25 | Divine Power pronoun lowercase | «Вона також гнівна, Вона гнівна» |
| S4 | 19 | Inconsistent capitalization of «реалізація» | «реалізацію іншим» |

## Results — Pass 3 (2 additional corrections, applied)

### L. Language (Orthography + Grammar + Punctuation)
| # | Paragraph | Error | Context | Fix |
|---|-----------|-------|---------|-----|
| L6 | 29 | Wrong verb: «одягнути» = to dress a person; «надіти» = to put on a specific item | «ви одягнете йому на голову корону» | «ви надінете йому на голову корону» |
| L7 | 54 | Non-standard dialectal form «стілько»; standard Ukrainian is «стільки» | «скинув стілько людей з пагорбів» | «скинув стільки людей з пагорбів» |

### S. SY Domain (Capitalization + Terminology + Consistency)
| # | Paragraph | Error | Context | Fix |
|---|-----------|-------|---------|-----|
| — | — | No additional issues found | — | — |

### Critic Filter — Pass 3
| Source | # | Verdict | Reason |
|--------|---|---------|--------|
| L | L6 | Keep | Genuine grammatical error. «Одягати/одягнути» = to dress someone (person as object). «Надівати/надіти» = to put on an item (item as object). A crown is an item, not clothing. Standard dictionaries confirm this distinction. |
| L | L7 | Keep | Genuine spelling error. «Стілько» is a western Ukrainian dialectal variant. Standard form «стільки» is used elsewhere in the same text (para 15: «Ми стільки разів їздили тією дорогою»). |

### All Approved Corrections (Pass 1 + Pass 2 + Pass 3)
| # | Paragraph | Error | Fix |
|---|-----------|-------|-----|
| L1 | 57 | Wrong case «яку» with «кидати виклик» | «якій нині кидають виклик» |
| L2 | 10 | Missing commas around appositive | «і, як сахаджа йоґ, це стає» |
| L3 | 52 | Missing commas around comparison | «людина, як Я, обговорювала» |
| L4 | 16 | Missing comma after «Отже» | «Отже, тепер, коли» |
| L5 | 31 | Incorrect ґ in non-Sanskrit word | «гірлянду з тулсі» |
| L6 | 29 | Wrong verb «одягнете» for putting on item | «надінете йому на голову корону» |
| L7 | 54 | Dialectal form «стілько» | «стільки людей з пагорбів» |
| S1 | 28 | SM pronoun lowercase | «Я не знаю» |
| S2 | 29 | SM pronoun lowercase | «Я думаю» |
| S3 | 25 | Divine Power pronoun lowercase | «Вона також гнівна, Вона гнівна» |
| S4 | 19 | Inconsistent capitalization of «реалізація» | «реалізацію іншим» |

## Summary

- Language (L): 7 issues found, 7 approved by Critic
- SY Domain (S): 4 issues found, 4 approved by Critic
- Total corrections applied: 11 (7 in pass 1, 2 in pass 2, 2 in pass 3)

## Quality Notes

The translation is of high quality overall:
- Quotation marks consistently use «» at all levels, including nested quotes
- Em-dash ` – ` used correctly with spaces throughout
- Ellipsis `...` used correctly without preceding space
- SY terminology matches glossary: Кундаліні, Нірвічара, Сакші, Рітамбхара Праг'я, Парамчайтанья, бхакті, бадхи, Принцип Ґуру
- Declension of «Сахаджа Йоґа» correct: genitive «Йоґи», locative «Йозі» (ґ→з), accusative «Йоґу»
- «сахаджа йоґ/йоґи» correctly lowercase as common noun
- Deity pronoun capitalization correct in 40+ instances
- Spiritual terms capitalized per rules: Дух, Істина, Пуджа
- Correct handling of complex dialogue passages with multiple speakers (para 54-55)
- Standard closing «Нехай Бог благословить вас.» matches EN
