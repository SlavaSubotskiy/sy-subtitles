# Language Review – 1984-03-22_Birthday-Puja, 2026-04-20

## Process

Review of `transcript_uk.txt` using 2 parallel reviewers (Language + SY Domain) plus a Critic filter.

Line numbers below refer to paragraph indices in `transcript_uk.txt`.

## Results

### L. Language (Orthography + Grammar + Punctuation)

| #  | Paragraph | Error | Context | Fix |
|----|-----------|-------|---------|-----|
| L1 | 17 | `розквітати` is intransitive in Ukrainian — cannot take a direct object | ви **розквітаєте** свої власні лотоси | ви розпускаєте / розкриваєте свої власні лотоси |
| L2 | 32 | Spelling — Ukrainian `хихотіти` / `хихотіння` uses pattern и-и, not і-і (`хіхотіння` is non-standard) | постійне **хіхотіння** … Але **хіхотіння** є невідповідним | постійне хихотіння … Але хихотіння є невідповідним |
| L3 | 37 | Typo — synthetic future of `бити` is `битимуть`, not `бітимуть` (adjacent `плюватимуть` uses correct и) | інші **бітимуть** вас черевиками | інші битимуть вас черевиками |
| L4 | 53 | Russian-language predicative — `нехорошо` is not a Ukrainian word form | Це **нехорошо**. | Це недобре. |
| L5 | 81 | Euphony rule — preposition `в` before a word starting with `в`/`ф` must be `у` | усі землі **в ваших** руках | усі землі у ваших руках |

### S. SY Domain (Capitalization + Terminology + Consistency)

| # | Paragraph | Error | Context | Fix |
|---|-----------|-------|---------|-----|
| — | — | No issues found | All deity pronouns for Shri Mataji (Я / Мій / Моя / Моїх / Мого / Мене / Мені / Свою / Вона / Її / Їй) are correctly uppercase; references to the Mother (Мати / Матір / Матері / Матінко) are uppercase; Бог's pronoun (Він) is uppercase. Glossary terms are consistent with `terms_lookup.yaml` (Кундаліні, Сахасрара, Аґія, Екадаша, Сахаджа Йоґа, Дхарма, Пуджа, Дух, Веди, Махакалі, Махалакшмі, Махасарасваті, пунья, бхути, бадх, ашрам, садху, факір, гопі, Ґуру, Чанді, Кріта, Мати Земля, Будинок Матері). Sentence-initial quoted speech capitalizes first letter correctly. Language names (англійська, маратхі, гінді) are lowercase. Declensions of Сахаджа Йоґа (Йоґа / Йоґи / Йозі / Йоґу / Йоґою) and сахаджа йоґ (йоґ / йоґа / йоґи / йоґам / йоґами / йоґів) are all correct. Locative `у Сахаджа Йозі` / `в Сахаджа Йозі` used consistently. | — |

### Critic Filter

| Source | # | Verdict | Reason |
|--------|---|---------|--------|
| L | L1 | **Remove** | The EN original itself uses the non-standard construction "blooming high your own lotuses". The translator's awkward Ukrainian mirrors this source irregularity. Changing only the UK while EN remains unusual would drop the authorial voice. Preserve the deliberate stylistic mirroring. |
| L | L2 | **Keep** | Clear spelling error. СУМ standard: `хихотіти` / `хихотіння` (both и-и). The form `хіхотіння` does not exist in Ukrainian. Affects two occurrences in the same paragraph. |
| L | L3 | **Keep** | Clear typo. Synthetic future of `бити` is `битиму, битимеш, …, битимуть` (all и). The neighboring `плюватимуть` in the same sentence already uses correct и, making `бітимуть` an isolated slip. |
| L | L4 | **Keep** | `Нехорошо` is a Russian predicative with no Ukrainian equivalent of this morphological shape. Standard Ukrainian: `недобре` / `негарно` / `погано`. Chose `недобре` as closest to EN register ("It is not good"). |
| L | L5 | **Keep** | Ukrainian orthography: preposition `в` before a word starting with `в` or `ф` must be replaced by `у` to avoid consonant cluster. The same sentence already contains `у вас` — making `в ваших` immediately after inconsistent and phonetically awkward. |

### Approved Corrections

| # | Paragraph | Error | Fix |
|---|-----------|-------|-----|
| 1 | 32 | постійне хіхотіння | постійне хихотіння |
| 2 | 32 | Але хіхотіння є невідповідним | Але хихотіння є невідповідним |
| 3 | 37 | інші бітимуть вас черевиками | інші битимуть вас черевиками |
| 4 | 53 | Це нехорошо. | Це недобре. |
| 5 | 81 | усі землі в ваших руках | усі землі у ваших руках |

## Summary

- Language (L): 5 issues found, 4 approved by Critic (L1 retained as deliberate mirror of the non-standard EN original)
- SY Domain (S): 0 issues found, 0 approved by Critic
- Total corrections applied: 5 edits covering 4 distinct issues (хіхотіння appears twice in paragraph 32)

## Quality Notes

The translation is of very high quality overall:

- Shri Mataji's pronoun capitalization (Я / Мій / Моя / Моїх / Мого / Мене / Свою / Вона / Її / Їй) is consistently correct throughout all 86 paragraphs
- Mother address forms (Мати / Матір / Матері / Матінко) correctly uppercase whenever referring to Shri Mataji; first-letter-of-sentence capitalization preserved in quoted speech
- God's pronoun `Він` (paragraph 83) correctly uppercase
- Quotation marks use `«»` consistently at all levels — no German `„"` or English `""` found
- Nested quotes (e.g. the Marathi phrase embedded in Devanagari parenthesis in paragraph 53) correctly handled
- En-dash ` – ` with spaces used correctly for interjections throughout
- Ellipsis `...` used correctly (no space before)
- All glossary terms match `terms_lookup.yaml`
- Declension system for Сахаджа Йоґа and сахаджа йоґ is applied correctly in all cases (including the non-trivial alternation ґ→з in locative `в Сахаджа Йозі`, confirmed 6+ times)
- Numeral `61-й` (ordinal masculine) correctly written
- Language names (маратхі, гінді, англійська) correctly lowercase
- Marathi idioms preserved with explanatory parentheticals (`«Він заліз на кущ бобу»`, etc.)
- `Кріта` used correctly for "Krita (active)" per glossary
- Proper names (Мумбаї, Делі, Бомбей, Аґра, Гарішчандра, Акбар, Шіваджі Махарадж, Мавланкар, Халді-Кумкум) correctly transliterated and capitalized

The issues found are minor typos/Russianisms and one euphony violation — all localized and easily corrected.
