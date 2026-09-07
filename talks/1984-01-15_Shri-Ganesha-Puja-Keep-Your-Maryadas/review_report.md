# Language Review – 1984-01-15 Shri Ganesha Puja: Keep Your Maryadas

## Process

Reviewed `transcript_uk.txt` (full paragraphed Ukrainian text) against the English
original (`transcript_en.txt`), the glossary (`terms_lookup.yaml`,
`terms_context.yaml`) and the orthography/capitalization rules in
`glossary/CLAUDE.md`, using 2 parallel reviewers + 1 critic filter.

Paragraph numbers below refer to the line numbers in `transcript_uk.txt`.

Automated character-level checks (run across the whole file) confirmed the text is
clean on every mechanical axis before the human-style review started: no Latin
letters inside Cyrillic words, all apostrophes are `’` (U+2019), all quotation marks
are `«»` (no `„“` / `""` at any level), all dashes are spaced en-dashes ` – `
(no `—`, no hyphen-as-dash), ellipsis is `...` (no `…`), and there are no double
spaces or spaces before punctuation. Language names in the header are lowercase
(`англійська`, `українська`). The closing blessing matches the fixed glossary form
(`Нехай Бог благословить усіх вас.`).

Deity-pronoun capitalization was checked sentence by sentence: Shri Mataji
(`Я/Мені/Мою/Моєї/Її`), Shri Ganesha (`Він/Його/Йому/Свої/Той/Сам`), Shri
Mahavira/Bhairava (`Він/Його/Йому/Своїх/Свій`), and Shri Krishna in disguise
(`Я/Мене/Моєму`, addressing Mahavira as `Ти/Тебе/Тобі/Свій`) are uppercase
throughout; yogis' own words (`«Я встановлю свого Ґанешу… дасть мені…»`, `«Де я?
Що я роблю?…»`) and `розум` → `Він` (sentence-initial only) are correctly
lowercase mid-sentence. Spiritual terms `Пуджа`, `Інкарнація`, `Дух`, `Кундаліні`,
`Муладхара`, `Набхі`, `бхути`, `маріяди`, `самаячара`, `Мати Земля`, `Ом`,
`Діґамбара` (Sanskrit `g` → `ґ`), `Сахаджа Йозі` (locative) and
`сахаджа йоґи/йоґів` all follow the glossary.

## Results

### L. Language (Orthography + Grammar + Punctuation)

| # | Paragraph | Error | Context | Fix |
|---|-----------|-------|---------|-----|
| L1 | ¶10 | Missing comma at the junction of two subordinating conjunctions (`що` + `якщо`) when the conditional clause has no correlative `то` (Правопис 2019, §118 п.7). The same text applies the rule correctly elsewhere (`…у тому, що, аби зберегти…`, ¶12; `…зрозуміти, що, аби бути…`, ¶15), so this is an isolated slip | `річ у тому, що **якщо** ваші очі чисті, ви можете зрозуміти` | `річ у тому, **що, якщо** ваші очі чисті, ви можете зрозуміти` |
| L2 | ¶11 | Calque of *ended up with cancer*: `закінчували раком` is not idiomatic Ukrainian, and in colloquial speech the bare instrumental `раком` carries a well-known vulgar reading — unacceptable on screen | `І такі люди, які так чинили, Я бачила, **закінчували раком**.` | `…Я бачила, **врешті захворювали на рак**.` |
| L3 | ¶15 | Euphony `у`/`в`: after a pause marked by a comma, before a consonant, `у` is used (Правопис 2019, §23 п.1). Also internally inconsistent — the identical phrase in ¶13 reads `…людина, **у** тому сенсі, що…` | `прийняти санньясу, **в** тому сенсі, що ваша сім’я…` | `прийняти санньясу, **у** тому сенсі, що ваша сім’я…` |

### S. SY Domain (Capitalization + Terminology + Consistency)

| # | Paragraph | Error | Context | Fix |
|---|-----------|-------|---------|-----|
| S1 | ¶15 | Name form inconsistency: glossary canonical form is `Махавіра` (nominative with final `-а`), and the text itself uses `Шрі Махавіри` (¶13), `Махавіра`, `Махавірою` (¶15) — but one nominative appears as `Шрі Махавір` (copying the source’s *Shri Mahavir* variant) | `що **Шрі Махавір** – Він був Діґамбарою` | `що **Шрі Махавіра** – Він був Діґамбарою` |
| S2 | ¶7 | SY-factual precision: *the fourth day of the moon* is the lunar day (tithi, Chaturthi). After `Щомісяця`, `четвертий день місяця` is read by any Ukrainian reader as "the 4th calendar day of the month", which is not what Shri Mataji says | `Щомісяця **четвертий день місяця** відзначають як дату народження Шрі Ґанеші.` | `Щомісяця **четвертий місячний день** відзначають як дату народження Шрі Ґанеші.` |
| S3 | ¶11 | Short form `Сахадж Йоґи` amid 18 occurrences of the full `Сахаджа Йоґа/Йоґи/Йозі/Йоґу/Йоґою` | `дбайте про те, що ви зробили для **Сахадж Йоґи**` | `…для **Сахаджа Йоґи**` (consistency) |
| S4 | ¶15 | Cross-corpus transliteration: this talk uses `санньяса/санньясу/санньясі` (doubled `нн`), while other talks in the repo mostly use `саньяса/саньясі`. Glossary has no entry | `Перш ніж прийняти справжню **санньясу**…` | unify with corpus (`саньяса`)? |

### Critic Filter

| Source | # | Verdict | Reason |
|--------|---|---------|--------|
| L1 | ¶10 | **Keep** | Codified punctuation rule (comma between adjoining conjunctions when no `то` follows), and the translator already follows it twice in the same document. Clear, low-risk fix. |
| L2 | ¶11 | **Keep** | Not a style preference: `закінчували раком` is an un-Ukrainian calque whose surface form collides with a vulgar colloquialism. For subtitles of a Puja talk that is a genuine defect. The replacement keeps the sense (*have ended up with cancer*) and matches the same talk’s own wording later (`люди захворювали на рак`, ¶15). |
| L3 | ¶15 | **Keep** | Правопис rule for `у` after a comma before a consonant, and the text is otherwise consistent (`у тому сенсі`, ¶13). Trivial but real. |
| S1 | ¶15 | **Keep** | `Махавіра` is the glossary form and the form used in the other three occurrences in this very text; the lone `Махавір` is an inconsistency, not an authorial choice. The source’s *Mahavir/Mahavira* alternation is a transcript artefact, not a distinction to preserve. |
| S2 | ¶7 | **Keep** | The rendering changes a factual detail about Shri Ganesha’s day (a lunar tithi, not a calendar date). `четвертий місячний день` is the standard Ukrainian term for a lunar day and reads naturally after `Щомісяця`. Justified, minimal, meaning-preserving. |
| S3 | ¶11 | **Remove** | False positive. The English original itself says *Sahaj Yoga* at exactly this point, and `terms_context.yaml` explicitly allows both `сахадж`/`сахаджа` "за оригіналом". Faithful to source; not an error. |
| S4 | ¶15 | **Remove** | The glossary is silent; `санньяса` is a valid transliteration of Sanskrit *sannyāsa* (doubled *n*); the talk is internally consistent across all four occurrences. Cross-corpus harmonisation is out of scope for a single-talk review and would need a glossary decision first. |

### Approved Corrections

| # | Paragraph | Error | Fix |
|---|-----------|-------|-----|
| 1 | ¶7 | `четвертий день місяця` (lunar day mistranslated as calendar day) | `четвертий місячний день` |
| 2 | ¶10 | `що якщо ваші очі чисті, ви можете` (missing comma between conjunctions) | `що, якщо ваші очі чисті, ви можете` |
| 3 | ¶11 | `закінчували раком` (calque; vulgar surface reading) | `врешті захворювали на рак` |
| 4 | ¶15 | `санньясу, в тому сенсі` (euphony after comma) | `санньясу, у тому сенсі` |
| 5 | ¶15 | `Шрі Махавір` (name form inconsistent with glossary and text) | `Шрі Махавіра` |

All five corrections have been applied to `transcript_uk.txt`; each target string
occurred exactly once and was verified after replacement.

## Summary

- Language (L): 3 issues found, 3 approved by Critic
- SY Domain (S): 4 issues found, 2 approved by Critic
- Total corrections applied: 5
