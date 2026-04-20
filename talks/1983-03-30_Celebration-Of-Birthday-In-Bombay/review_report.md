# Language Review – 1983-03-30_Celebration-Of-Birthday-In-Bombay

## Process

Review `transcript_uk.txt` (full paragraphed Ukrainian text) using 2 parallel reviewers + 1 critic filter.
This is a re-review pass after prior review corrections.

### Review Agents

- **Reviewer L** – Language (Orthography + Grammar + Punctuation)
- **Reviewer S** – SY Domain (Capitalization + Terminology + Consistency)
- **Critic** – Filter + Validate

## Results

### L. Language (Orthography + Grammar + Punctuation)
| # | Paragraph | Error | Context | Fix |
|---|-----------|-------|---------|-----|
| L1 | 11 | Conjunction mismatch: «Оскільки...але...» – causal «оскільки» contradicts concessive «але» | `Оскільки Я не маю звички носити прикраси, але Мені доводиться це робити.` | `Хоча Я не маю звички носити прикраси, але Мені доводиться це робити.` |
| L2 | 38 | Verb form: missing soft sign ь, 3 sg future perfective of «поширитися» | `вона поширится по всьому світу` | `вона пошириться по всьому світу` |
| L3 | 19 | End punctuation: rhetorical question starting with «Як же...» typically ends with «?» | `Як же пояснити людям, яке значення Пуджі.` | `Як же пояснити людям, яке значення Пуджі?` |
| L4 | 37 | Case form: Sanskrit name «Шанділья» in genitive context should decline to «Шандільї» | `це місце Шанділья Муні тощо` | `це місце Шандільї Муні тощо` |
| L5 | 21 | Redundant doubling: «У сахаджа йоґів також деякі з них» – pleonasm in spoken style | `У сахаджа йоґів також деякі з них мають проблеми` | `Серед сахаджа йоґів також деякі мають проблеми` |

**Verified correct:**
- Spelling, word forms – otherwise consistently correct
- Latin/Cyrillic mixing – none detected
- Quotation marks – `«»` used consistently at all levels
- Em-dash – ` – ` (U+2013) with spaces throughout
- Ellipsis – none present
- Apostrophes – consistent use in `п'ятдесят`, `пам'ятати`, `ім'я`, `з'явилася`
- Comma usage around subordinate clauses – verified

### S. SY Domain (Capitalization + Terminology + Consistency)
| # | Paragraph | Error | Context | Fix |
|---|-----------|-------|---------|-----|
| (none found) | | | | |

**Verified correct:**
- Deity pronoun capitalization:
  - Shri Mataji (1st person): Я/Мене/Мені/Моя/Моє/Мого/Мій/Моїх/Себе/Сама/Своєї – uppercase throughout
  - Shri Mataji (3rd person): Вона, Матаджі, Матінко, Мати – uppercase throughout
  - God: Він/Його/Йому/Нього/Богові/Богом/Свій/Своїх/Сам – uppercase throughout
  - Regular people (Varkari, tobacco users): він/його/йому – lowercase ✓
- Glossary terms all match `terms_lookup.yaml`:
  - Кундаліні, Пуджа, тапасьї, бхакті, бхактів, его
  - Сахаджа Йоґа / Йоґою (instr.) / Йоґи (gen.) / Йозі (loc.) / Йоґу (acc.) – correct declension with ґ→з alternation per `terms_context.yaml`
  - сахаджа йоґів (practitioners, lowercase per glossary)
  - Махайоґа/Махайоґою, Брахмашакті, Всепроникна Сила – preserved
  - Шрі Крішна, Шрі Рама (genitive «Шрі Рами»), Вітхала, Муні, Хануман (plural «Хануманів»)
  - Варкарі (religious community, capitalized per English source)
  - віддача на милість (surrender) – correct usage in para 18, 21
  - «Нехай Бог благословить усіх вас.» – exact glossary match (para 30)
- Sanskrit 'g' → ґ consistently applied: Йоґа, Йоґи, ґаті, Ардхамаґадхі, Махайоґа
- Aspirate 'dh' → дх: Махараштра, Свадхістхана (none here), Пітхи, Муладхара (none here)
- Sanskrit short 'i' → і: Шіва (none here), Махавіра (none here)
- Language names lowercase: англійська, маратхі ✓
- Ethnonyms lowercase: махараштрійці ✓
- Spiritual terms uppercase: Пуджа, Всесвіт, Царство Боже, Реалізація, Божественна любов, Всепроникна Сила, Брахмашакті, Шакті Пітхи, Аштавінаяки
- Saints/Gods collective uppercase: Святі, Боги (in Hindu/SY context) – consistent with English
- Proper names: Прахлад, Шанділья Муні, Рамдас Свамі, Трета Юги, Дандакаранья, Аштавінаяки – all correctly transliterated and capitalized

### Critic Filter
| Source | # | Verdict | Reason |
|--------|---|---------|--------|
| L | L1 | **Keep** | Genuine Ukrainian grammar error. «Оскільки» marks cause («since»), which is logically incompatible with adversative «але». Minimal fix: replace «Оскільки» with concessive «Хоча» (preserves sentence rhythm; the «хоча...але» pleonasm is widely tolerated in Ukrainian). |
| L | L2 | **Keep** | Clear typo: «поширится» is missing the soft sign. 3 sg future perfective of reflexive «поширитися» is «пошириться» per standard Ukrainian conjugation (порівн. «зробиться», «ходиться»). |
| L | L3 | **Remove** | Style preference, not an error. Source English also uses period («Now how to explain...is.»). The elliptical statement with period works as an expression of puzzlement; changing to «?» is translator discretion. |
| L | L4 | **Remove** | Sanskrit compound names with invariable «Муні» head are commonly treated as a unit and left uninflected in SY translations. Although strict grammar prefers «Шандільї», this is a translator style choice consistent with the broader practice around «Муні». Not a clear error. |
| L | L5 | **Remove** | Preserves the source speaking style («Sahaj Yogis also, some of them have problems...»). Reflects Shri Mataji's characteristic spoken English. Not a grammatical error, just colloquial redundancy that the translation faithfully carries over. |

### Approved Corrections
| # | Paragraph | Error | Fix |
|---|-----------|-------|-----|
| 1 | 11 | «Оскільки ... але» conjunction mismatch | `Хоча Я не маю звички носити прикраси, але Мені доводиться це робити.` |
| 2 | 38 | Typo «поширится» (missing ь) | `вона пошириться по всьому світу` |

## Summary

- Language (L): 5 issues found, 2 approved by Critic
- SY Domain (S): 0 issues found
- Total corrections applied: 2

## Quality Assessment

Translation is of high quality. Deity pronoun capitalization is meticulous and consistent (including Мої, Мене, Себе, Сама, Своєї for 1st person Shri Mataji). SY terminology precisely follows the glossary including transliteration conventions (ґ for Sanskrit 'g') and the ґ→з alternation for Sahaja Yoga in locative case (Йозі). Quotation marks «», em-dash ` – `, and apostrophes are all orthographically correct. Dialogue punctuation in embedded quotes (para 18, 35) follows Ukrainian direct-speech rules. Sacred register and devotional tone are well preserved. The two remaining issues were a single-character typo and a single-word conjunction mismatch in an awkward source sentence – both easily fixed without altering meaning.
