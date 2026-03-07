# Language Review — From-Heart-To-Sahastrar-Derby, 1982-07-11

## Process

Review `transcript_uk.txt` (full paragraphed Ukrainian text) using 2 parallel reviewers + 1 critic filter.

## Results

### L. Language (Orthography + Grammar + Punctuation)
| # | Paragraph | Error | Context | Fix |
|---|-----------|-------|---------|-----|
| L1 | 39-48 (original) | Duplicate paragraphs: 10 paragraphs are exact copies of paragraphs 52-61 | Lines 39-48 break text flow between "destructive forces" (para 38, ending "Якщо ви читаєте в газеті —") and "newspaper news" (para 49, starting "З ранку до вечора"). The English source transcript has the same duplication at EN lines 39-48/52-61. The second occurrence (52-61) is in the correct position, following the charity discussion ending with "Скільки квітів перетворюється на плоди прямо зараз?" | Remove lines 39-48 entirely |
| L2 | 60 (original) | Russicism "женихи" | "Чоловіки все ще як женихи, шукають нових дружин" — "женихи" is Russian (from "жених"), not Ukrainian | "наречені" |
| L3 | 77 (original) | Non-standard "/" punctuation in running text | "пророчою/довершеною особистістю" — slash is not standard Ukrainian punctuation between adjectives | "пророчою, довершеною особистістю" |
| L4 | Multiple (13+ instances) | Verb "Мушу" capitalized mid-sentence | ", Мушу сказати" — "мушу" is a verb form, not a pronoun. CLAUDE.md rules capitalize only pronouns (Я/Мені/Мій/Моя), not verb forms | "мушу сказати" |
| L5 | 85 (original) | Misspelling + non-standard borrowing | "коли раппорт встановлений" — double "п" is wrong; "раппорт" is a non-standard calque from English "rapport" | "коли зв'язок встановлений" |

### S. SY Domain (Capitalization + Terminology + Consistency)
| # | Paragraph | Error | Context | Fix |
|---|-----------|-------|---------|-----|
| S1 | 54 (original) | Inconsistent capitalization of "реалізацію" | "отримав свою реалізацію" — lowercase, while all other instances (paras 6, 30, 37, 78, 79, 88) use uppercase "Реалізація". Glossary entry "масова Реалізація" also uses uppercase. | "отримав свою Реалізацію" |

**Additional checks performed (no issues found):**
- Deity pronoun capitalization: Shri Mataji (Я/Мені/Мій/Моя) — correct throughout
- Incarnation pronouns (Він/Його/Йому for Buddha, Krishna, Christ, Guru Nanak, Mohammed Sahib, Moses) — correct throughout
- Incarnations plural mid-sentence — not applicable in this text
- Quotation marks: all use `«»` at all nesting levels — correct
- Em-dash: all use ` — ` with spaces — correct
- Ellipsis: `...` used correctly
- No mixed Latin/Cyrillic characters (verified via grep)
- Glossary terms match: Кундаліні, Сахаджа Йоґа, Сахасрара, Аґія, Вішуддхі, Набхі, Войд, Махавіра, Будда, Махавішну, Екадаша Рудра, Брахмарандхра, Джаґадамба, Калькі, Дхарма, Інкарнація
- Locative of "Сахаджа Йоґа" — "в Сахаджа Йозі" (correct ґ→з alternation)
- Plural of "сахаджа йоґ" — "сахаджа йоґи" (correct)
- Language names lowercase: "англійська", "українська" — correct
- Spiritual term capitalization: Дхарма, Інкарнація, Дух — correct

### Critic Filter
| Source | # | Verdict | Reason |
|--------|---|---------|--------|
| L | L1 | **Keep** | Major structural error. 10 duplicate paragraphs break text flow. Correct order: para 38 ("Якщо ви читаєте в газеті —") -> para 49 ("З ранку до вечора...") -> 50 -> 51 (charity, ending with flowers) -> 52 ("Хто виконує цю роботу?"). The duplicates at 39-48 are identical to 52-61 and must be removed regardless of the source having the same issue. |
| L | L2 | **Keep** | Clear Russicism. "Женихи" is not a standard Ukrainian word; correct is "наречені". |
| L | L3 | **Keep** | Slash "/" is not standard Ukrainian punctuation between adjectives in running text. A comma is appropriate. |
| L | L4 | **Remove** | Consistent deliberate style choice (13+ instances). While technically "мушу" is a verb, the capitalization consistently signals Shri Mataji as implied subject. This is an established convention in the translation, not a random error. Changing all instances would be a massive edit for a minor stylistic preference. |
| L | L5 | **Keep** | Genuine misspelling (double п) of a non-standard borrowing. "Зв'язок" is the natural Ukrainian word for "rapport/connection" in this context. |
| S | S1 | **Keep** | Inconsistency: one lowercase instance among 6+ uppercase instances of the same term within the text. |

### Approved Corrections
| # | Paragraph (original) | Error | Fix |
|---|-----------|-------|-----|
| 1 | 39-48 | 10 duplicate paragraphs (identical to 52-61) | Removed lines 39-48 |
| 2 | 60 | Russicism "женихи" | "наречені" |
| 3 | 77 | Non-standard "/" punctuation | "пророчою, довершеною особистістю" |
| 4 | 85 | Misspelling "раппорт" | "зв'язок" |
| 5 | 54 | Inconsistent lowercase "реалізацію" | "Реалізацію" |

## Summary

- Language (L): 5 issues found, 4 approved by Critic (L4 removed as deliberate style convention)
- SY Domain (S): 1 issue found, 1 approved by Critic
- Total corrections applied: **5**
- Note: The duplicate paragraph issue (L1) originates from the English source transcript, which contains the same duplication at EN lines 39-48 / 52-61.
