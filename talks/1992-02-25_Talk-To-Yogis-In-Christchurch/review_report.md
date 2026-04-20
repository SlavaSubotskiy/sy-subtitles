# Language Review – 1992-02-25 Talk-To-Yogis-In-Christchurch

## Process

2+1 review of `transcript_uk.txt`: Reviewer L (Language) + Reviewer S (SY Domain) in parallel, then Critic filters and validates.

## Results

### L. Language (Orthography + Grammar + Punctuation)

| # | Paragraph | Error | Context | Fix |
|---|-----------|-------|---------|-----|
| L1 | all (63 instances) | Em-dash (U+2014) used instead of en-dash (U+2013) per CLAUDE.md | «Але тепер — ні...», «Його ім'я — Джон Пірсон»... | Replace all " — " with " – " (U+2013) |
| L2 | 27 | Pronoun inconsistency within a single quoted instruction: "ти займався" → "Ви маєте" | «Добре, це ТМ, ти займався, покінчив із нею і прийшов до Сахаджа Йоґи. ... Ви маєте над цим попрацювати...» | Unify to formal "ви": "ви займалися, покінчили з нею і прийшли... Ви маєте..." |
| L3 | 64 | Unmatched opening quotation mark (6 opens, 5 closes) – extraneous « before "Тож коли він запитав" | «Так, нам дозволено.» «Тож коли він запитав, чи хотів би він одружитися, може, папа... сказав: «Ми не хочемо платити пенсію вдові». | Remove extraneous opening «: «Так, нам дозволено.» Тож коли він запитав... |
| L4 | 7 | "дуже-дуже" hyphenation | "Я дуже-дуже рада приїхати" | Acceptable emphatic repetition; no fix. |
| L5 | 29 | "можете задати" – Russianism | "ви можете задати:" | Style preference; not an error. |
| L6 | 28 | Unusual construction "людям, слабим здоров'ям" | "допомогти людям, слабим здоров'ям, ми можемо..." | "слабий"/"слабим" is a valid literary variant; not an error. |
| L7 | 56 | "Немає досвіду неї" – awkward word order | "Немає досвіду неї." | Style issue; preserves spoken-text rhythm. |
| L8 | 67 | "шибениками" (brats) | "Вони всі стануть шибениками" | Acceptable translation of "brats". |

### S. SY Domain (Capitalization + Terminology + Consistency)

| # | Paragraph | Error | Context | Fix |
|---|-----------|-------|---------|-----|
| S1 | 15 | "Я" capitalized in a yogini's quoted speech – regular speaker, should be lowercase per CLAUDE.md | вони сказали: «Мати, з ним, Я не знаю» | «Мати, з ним, я не знаю» |
| S2 | 10 | "фотографії" lowercase – inconsistent with the rest of the document ("Фотографію", "Фотографії" capitalized in paras 20, 27, 28, 33, 41); refers to Shri Mataji's Photographs | "У вас є фотографії, ви бачили, як пульсує Кундаліні." | "У вас є Фотографії, ви бачили, як пульсує Кундаліні." |
| S3 | 8 | "істину" lowercase – could be Істина (absolute Truth) | "тепер мають очі, щоб бачити істину" | Ambiguous; EN has lowercase "truth"; follows source. |
| S4 | 54 | "він/свої" lowercase for Thomas (Хома) – EN capitalizes "He/His" | "він спустився до Єгипту, де написав усі свої трактати" | Correct per UK SY convention (Thomas is a disciple, not an Incarnation). |
| S5 | 57 | "Він бігав то туди, то сюди" – bishop of Durham is a regular person | "Він бігав то туди, то сюди, і ховався." | Correct: "Він" at sentence start is standard capitalization. |
| S6 | 65 | "Адвентисти Сьомого Дня", "П'ятидесятники" – capitalization style | "у них є Адвентисти Сьомого Дня, П'ятидесятники" | Style choice; acceptable. |
| S7 | 17 | "санньяса" | "вони говорять про санньясу" | Standard transliteration; OK. |

### Critic Filter

| Source | # | Verdict | Reason |
|--------|---|---------|--------|
| L | L1 | Keep | CLAUDE.md explicitly requires en-dash (U+2013). Other project transcripts use en-dash. Systemic fix (63 occurrences). |
| L | L2 | Keep | Clear grammatical inconsistency within a single quoted instruction – same addressee referred to with mixed ти/Ви. |
| L | L3 | Keep | Genuine punctuation error: unmatched quotation mark. The extraneous « is a transcription artifact from EN (EN has the same unmatched `'`). |
| L | L4 | Remove | "дуже-дуже" with hyphen is standard Ukrainian for emphatic repetition. |
| L | L5 | Remove | "задати запитання" is acceptable modern Ukrainian; not an error. |
| L | L6 | Remove | "слабим здоров'ям" is a valid compressed instrumental-of-quality construction. |
| L | L7 | Remove | Stylistic, preserves spoken-text fidelity. |
| L | L8 | Remove | "шибеники" is an acceptable rendering of "brats". |
| S | S1 | Keep | Per CLAUDE.md, "Я" is reserved for Shri Mataji. The speaker in the quote is a yogini describing her husband – a regular person, lowercase "я". |
| S | S2 | Keep | Internal consistency: all other occurrences in the same document capitalize "Фотографія/Фотографії". Context (seeing Kundalini pulsate) confirms reference to Shri Mataji's Photographs. |
| S | S3 | Remove | EN has lowercase "truth"; ambiguous whether this is "absolute Truth" or ordinary truth. Follow source. |
| S | S4 | Remove | Correctly lowercase per CLAUDE.md: Thomas is a disciple, not an Incarnation. |
| S | S5 | Remove | "Він" is at sentence start – standard Ukrainian capitalization. No error. |
| S | S6 | Remove | Religious-group naming style is acceptable. |
| S | S7 | Remove | Transliteration is standard. |

### Approved Corrections

| # | Paragraph | Error | Fix |
|---|-----------|-------|-----|
| 1 | all | Em-dash (U+2014) → en-dash (U+2013) | Replaced all 63 occurrences of " — " with " – " |
| 2 | 10 | "фотографії" → "Фотографії" (Shri Mataji's Photographs, consistency with the rest of the document) | "У вас є Фотографії, ви бачили, як пульсує Кундаліні." |
| 3 | 15 | "Я" → "я" in yogini's quoted speech (regular-person pronoun) | «Мати, з ним, я не знаю» |
| 4 | 27 | Pronoun unification (ти → ви) within quoted instruction | «Добре, це ТМ, ви займалися, покінчили з нею і прийшли до Сахаджа Йоґи. Але негайні результати неможливі. Ви маєте над цим попрацювати, бо це жахливо.» |
| 5 | 64 | Remove extraneous opening « (unmatched quotation marks) | «Так, нам дозволено.» Тож коли він запитав... |

## Summary

- Language (L): 8 issues found, 3 approved by Critic
- SY Domain (S): 7 issues found, 2 approved by Critic
- Total corrections applied: 5 (1 systemic spanning 63 occurrences + 4 targeted edits)
