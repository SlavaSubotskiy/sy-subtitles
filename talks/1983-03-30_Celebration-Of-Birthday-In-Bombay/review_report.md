# Language Review – 1983-03-30_Celebration-Of-Birthday-In-Bombay

## Process

Review `transcript_uk.txt` (full paragraphed Ukrainian text) using 2 parallel reviewers + 1 critic filter.

### Review Agents

- **Reviewer L** -- Language (Orthography + Grammar + Punctuation)
- **Reviewer S** -- SY Domain (Capitalization + Terminology + Consistency)
- **Critic** -- Filter + Validate

## Results

### L. Language (Orthography + Grammar + Punctuation)
| # | Line | Error | Context | Fix |
|---|------|-------|---------|-----|
| L1 | 15 | Missing comma before subordinating "що" | `на тій глибині що ми можемо сказати` | `на тій глибині, що ми можемо сказати` |
| L2 | 17 | Missing comma before "і" in compound sentence (different subjects: "час"/"Мені") | `прийшов час і Мені потрібно їх надіти` | `прийшов час, і Мені потрібно їх надіти` |
| L3 | 27 | Missing comma before indirect question "скільки" | `Я не знаю скільки років тому` | `Я не знаю, скільки років тому` |
| L4 | 28 | Missing comma before "і" in compound sentence (different subjects: "люди"/"світ") | `у своїй еволюції і новий світ може бути створений` | `у своїй еволюції, і новий світ може бути створений` |
| L5 | 39 | Missing comma before indirect question "чому" | `сказати чому` | `сказати, чому` |

### S. SY Domain (Capitalization + Terminology + Consistency)
| # | Line | Error | Context | Fix |
|---|------|-------|---------|-----|
| S1 | 23 | Inconsistent capitalization: "всесвіт" (lowercase x3) vs "Всесвіт" (uppercase) in lines 11, 20 | `цей всесвіт так красиво... цього прекрасного всесвіту цей всесвіт має` | `цей Всесвіт так красиво... цього прекрасного Всесвіту цей Всесвіт має` |

### Verified: no issues found in
- Deity pronoun capitalization (Shri Mataji: Я/Мені/Мій/Моя/Її/Себе/Своєї consistently uppercase; God: Він/Його/Йому/Нього/Своїх consistently uppercase; regular people: lowercase)
- Quotation marks (all use `<<>>` Ukrainian style at every level)
- Em-dash usage (all ` -- ` with spaces)
- Glossary term consistency (Кундаліні, Пуджа, Сахаджа Йоґа, Сахаджа Йозі [locative], тапасья, бхакті, его, чакри, Шрі Крішна, Вітхала, Муні -- all match glossary)
- SY terminology accuracy throughout
- No Latin/Cyrillic character mixing detected
- No spelling errors detected

### Critic Filter
| Source | # | Verdict | Reason |
|--------|---|---------|--------|
| L | L1 | Keep | Clear rule: comma before subordinating "що" introducing a clause |
| L | L2 | Keep | Clear rule: comma before "і" joining clauses with different subjects |
| L | L3 | Keep | Clear rule: comma before indirect question word |
| L | L4 | Keep | Clear rule: comma before "і" joining clauses with different subjects |
| L | L5 | Keep | Clear rule: comma before indirect question word |
| S | S1 | Keep | Inconsistency within same text; standardize to uppercase matching lines 11, 20 |

### Approved Corrections
| # | Line | Error | Fix |
|---|------|-------|-----|
| 1 | 15 | Missing comma before "що" | `на тій глибині, що ми можемо сказати` |
| 2 | 17 | Missing comma before "і" | `прийшов час, і Мені потрібно їх надіти` |
| 3 | 27 | Missing comma before "скільки" | `Я не знаю, скільки років тому` |
| 4 | 28 | Missing comma before "і" | `у своїй еволюції, і новий світ може бути створений` |
| 5 | 39 | Missing comma before "чому" | `сказати, чому` |
| 6 | 23 | "всесвіт" x3 lowercase | `Всесвіт` / `Всесвіту` x3 uppercase |

## Summary

- Language (L): 5 issues found, 5 approved by Critic
- SY Domain (S): 1 issue found, 1 approved by Critic
- Total corrections applied: 6
