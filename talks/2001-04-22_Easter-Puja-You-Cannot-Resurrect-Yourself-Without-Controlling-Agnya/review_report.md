# Language Review – 2001-04-22 Easter Puja: You Cannot Resurrect Yourself Without Controlling Agnya

## Process

Reviewed `transcript_uk.txt` (60 paragraphs of Ukrainian translation) using 2 parallel reviewers + 1 critic filter, following `templates/language_review_template.md`.

Reference: `transcript_en.txt` (English original), `glossary/terms_lookup.yaml`, `glossary/terms_context.yaml`, `glossary/CLAUDE.md`, `CLAUDE.md`.

## Results

### L. Language (Orthography + Grammar + Punctuation)

| # | Paragraph | Error | Context | Fix |
|---|-----------|-------|---------|-----|
| L1 | 12 | Inconsistent second-person pronoun: switches from formal «ви» (used throughout the lecture as Mataji's mode of address) to informal «ти/тебе» outside any quotation — a consistency break within narrative text. | «це справді ламає тебе, коли ти лише чуєш, як люди б'ються за нісенітниці» | «це справді ламає вас, коли ви лише чуєте, як люди б'ються за нісенітниці» |
| L2 | 14 | Mid-sentence «Я» in quoted speech of a hypothetical ego-driven person should be lowercase per Ukrainian orthography («я» as first-person pronoun of a regular speaker is lowercase except at sentence start). Internal «Я» after «тож» continues the same sentence. | «Я прийшов із цієї країни, тож Я мушу мати его» | «Я прийшов із цієї країни, тож я мушу мати его» |
| L3 | 14 | Same as L2: mid-quote «Я» of a hypothetical ego-driven person (after comma, inside one sentence) should be lowercase. Compare Para 41 where the same pattern is handled correctly («Усе, що я зробив, – добре»). | «Я походжу з такої сім'ї, Я маю мати его» | «Я походжу з такої сім'ї, я маю мати его» |

### S. SY Domain (Capitalization + Terminology + Consistency)

| # | Paragraph | Error | Context | Fix |
|---|-----------|-------|---------|-----|
| S1 | 12 | Pronoun for Prophet Mohammed (individual Incarnation, singular) must be capitalized per CLAUDE.md rule ("Individual Incarnations singular: uppercase Він/Його/Йому"). Mohammed is listed as sacred figure in glossary (Prophet Muhammad → Пророк Мохаммед). Parallels the same treatment of Christ's crucifixion in the same sentence. | «з іншого боку – Мохаммед-сахіба для його розп'яття» | «з іншого боку – Мохаммед-сахіба для Його розп'яття» |

### Critic Filter

| Source | # | Verdict | Reason |
|--------|---|---------|--------|
| L | L1 | Keep | Real consistency break. The entire lecture uses «ви» for generic/audience address; a single sentence switching to «ти/тебе» outside any quoted speech is jarring and not stylistically justified. EN uses generic «you», which is consistently rendered as «ви» elsewhere. |
| L | L2 | Keep | Clear orthography rule: mid-sentence «я» for a regular (non-deity) speaker is lowercase. The sentence is one unit joined by «тож» (so/therefore). Consistent with correct handling in Para 41. |
| L | L3 | Keep | Same rule as L2. Though the comma between clauses could be read as a comma splice, orthographically the quote is one typographic sentence (no period), so the second «Я» must be lowercase. Applying uniformly preserves consistency with Para 41. |
| S | S1 | Keep | CLAUDE.md rule is explicit: singular pronouns for individual Incarnations are uppercase. Mohammed is named a sacred figure in the glossary. The parallel structure with Christ («Христа для чергового розп'яття») reinforces the need — both are Incarnations facing metaphorical crucifixion. |

### Approved Corrections

| # | Paragraph | Error | Fix |
|---|-----------|-------|-----|
| 1 | 12 | «ламає тебе, коли ти лише чуєш» | «ламає вас, коли ви лише чуєте» |
| 2 | 12 | «Мохаммед-сахіба для його розп'яття» | «Мохаммед-сахіба для Його розп'яття» |
| 3 | 14 | «тож Я мушу мати его» | «тож я мушу мати его» |
| 4 | 14 | «сім'ї, Я маю мати его» | «сім'ї, я маю мати его» |

## Verified Areas (No Issues)

- **Shri Mataji pronouns** (Я/Мені/Мій/Моя/Моїй) — uniformly capitalized across all 60 paragraphs.
- **Christ pronouns** (Він/Його/Йому/Нього/Себе/Свою/Своїм) — uniformly capitalized.
- **Quotation marks** — Ukrainian «» (yalynky) used at all levels. No German „" or English "" detected.
- **Em-dashes** — all interjections use ` – ` (U+2013) with surrounding spaces.
- **Ellipsis** — `...` three dots, correctly used (Para 23).
- **Glossary terminology** — Аґія / Аґія чакра, Сахасрара, Кундаліні, Шрі Ґанеша (incl. declension Ґанеші gen., Ґанешею instr.), Сахаджа Йоґа / Сахаджа Йозі (loc. ґ→з), сахаджа йоґи (lowercase plural), стан свідка, стан усвідомлення без думок, Реалізація, Інкарнація, Пуджа, Дух, Істина, Божественна Сила, Воскресіння, бхути, его/суперего, обумовленість — all correctly rendered.
- **Language/nationality names** — англійська, українська, англієць, британці, європейців — lowercase per Ukrainian rules.
- **Imaginary ego-speech quotes** (Paras 27, 40, 41, 42, 44, 45) — correctly use lowercase «я/ти/ми/мене» mid-sentence for regular-person speakers.
- **Closing blessing** (Para 60) — exact fixed form «Нехай Бог благословить усіх вас» per glossary.
- **Bracketed editorial additions** — [але] (Para 32), [якщо] (Para 34), [відчуття] (Para 49), stage direction [У чому справа?...] (Para 39) — preserved from EN source.
- **Feminine past-tense agreement for Mataji's verbs** (сказала, казала, відчула, могла, думаю, впевнена, рада, була здивована, бачила, читаю) — consistent.

## Summary

- **Language (L)**: 3 issues found, 3 approved by Critic
- **SY Domain (S)**: 1 issue found, 1 approved by Critic
- **Total corrections applied**: 4

The translation is of high quality overall: glossary discipline is strong, deity-pronoun capitalization is largely consistent, and punctuation style follows Ukrainian conventions. The only real issues were (a) a localized slip into informal «ти» in Para 12, (b) two missed lowercase-«я» cases inside quoted ego-speech in Para 14, and (c) one missed capital «Його» for Prophet Mohammed in Para 12.
