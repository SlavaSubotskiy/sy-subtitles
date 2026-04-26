# Language Review – 1996-06-09 Adi Shakti Puja: The compassion has to become active

## Process

Two-reviewer + critic pass on `transcript_uk.txt` against the English source,
glossary, and capitalization rules in CLAUDE.md.

## Results

### L. Language (Orthography + Grammar + Punctuation)

| # | Paragraph | Error | Context | Fix |
|---|-----------|-------|---------|-----|
| L1 | 9 | Three em-dashes for nested apposition | «Бога Всемогутнього – просто створити людей, нічого їм не кажучи, – щось – трохи кращих тварин» | Mirrors EN structure («– something –»); acceptable. |
| L2 | 19 | Pronoun reference unclear: «Але щойно ця людина зникне, він візьме інший меч і переріже їй горло» | Mixed gender/antecedent reflects ambiguity in EN original | EN itself is ambiguous; leave. |
| L3 | 39 | Inconsistent capitalization of «царство»: «в царстві Бога Всемогутнього» (lower) vs «до Його Царства» (upper) | Two consecutive sentences | EN distinguishes «realm» (lower) and «Kingdom» (upper); UK mirrors. Defensible. |
| L4 | 43 | «Я не знаю, якщо Мені треба говорити...» — «якщо» where subjunctive «якби» fits the conditional | EN: «if I have to talk» | Translator's choice; «якщо» also valid. |

### S. SY Domain (Capitalization + Terminology + Consistency)

| # | Paragraph | Error | Context | Fix |
|---|-----------|-------|---------|-----|
| S1 | 13 | Lowercase «я» in Shri Mataji's narration | «У Колумбії я виявила, що на їхніх статуях…» | «У Колумбії Я виявила…» |
| S2 | 16 | Lowercase «я» in Shri Mataji's narration | «Це дуже великий, я думаю, ви маєте сказати…» | «Це дуже великий, Я думаю, ви маєте сказати…» |
| S3 | 17 | Lowercase «я» in Shri Mataji's narration | «Тому, я думаю, для вас дуже важливо поклонятися…» | «Тому, Я думаю, для вас дуже важливо поклонятися…» |
| S4 | 32 | Lowercase «я» in Shri Mataji's narration | «з чорної раси, я думаю, з Африки» | «з чорної раси, Я думаю, з Африки» |
| S5 | 43 | «пуджу» lowercase — glossary requires «Пуджа» uppercase | «Чи потрібно проводити цю пуджу?» | «Чи потрібно проводити цю Пуджу?» |
| S6 | 43 | «пуджа» lowercase — glossary requires «Пуджа» uppercase | «якщо є якась пуджа, яку ви маєте проводити» | «якщо є якась Пуджа, яку ви маєте проводити» |
| S7 | 43 | «пуджа» lowercase — glossary requires «Пуджа» uppercase | «Дуже важливо, щоб ця пуджа була виконана» | «Дуже важливо, щоб ця Пуджа була виконана» |
| S8 | 27 | «святий Іван» — could be «Святий Іван» per religious tradition | «Яків чи святий Іван казав» | Both forms valid; lowercase acceptable. |
| S9 | 8 | «власного» lowercase in «до власного вираження…» where EN has «His own» | «з прагнення до власного вираження» | «власний» is a regular adjective; lowercase correct. |

### Critic Filter

| Source | # | Verdict | Reason |
|--------|---|---------|--------|
| L | L1 | Remove | Translation choice mirrors EN appositive structure; not an error. |
| L | L2 | Remove | EN original is itself ambiguous; translator's interpretation is defensible. |
| L | L3 | Remove | EN distinguishes «realm» / «Kingdom»; UK mirrors with same word in two cases. Stylistic, not an error. |
| L | L4 | Remove | «якщо» is a valid translation of conditional «if»; not strictly wrong. |
| S | S1 | Keep | CLAUDE.md rule: Shri Mataji's «Я» ALWAYS uppercase. Clear violation. |
| S | S2 | Keep | Same rule; «Я думаю» is Shri Mataji's narration, not a quoted speaker. |
| S | S3 | Keep | Same rule. |
| S | S4 | Keep | Same rule; «Я думаю» mid-sentence in Shri Mataji's voice. |
| S | S5 | Keep | Glossary `terms_lookup.yaml`: «Puja → Пуджа» uppercase; CLAUDE.md confirms. |
| S | S6 | Keep | Same rule; consistency with «наступної Пуджі Аді Шакті» two sentences later. |
| S | S7 | Keep | Same rule. |
| S | S8 | Remove | Both «святий» and «Святий» are acceptable in Ukrainian; not an error. |
| S | S9 | Remove | «власний» is a regular adjective, not a deity pronoun; lowercase correct per Ukrainian orthography. |

### Approved Corrections

| # | Paragraph | Error | Fix |
|---|-----------|-------|-----|
| 1 | 13 | «У Колумбії я виявила» | «У Колумбії Я виявила» |
| 2 | 16 | «Це дуже великий, я думаю, ви маєте сказати» | «Це дуже великий, Я думаю, ви маєте сказати» |
| 3 | 17 | «Тому, я думаю, для вас дуже важливо» | «Тому, Я думаю, для вас дуже важливо» |
| 4 | 32 | «з чорної раси, я думаю, з Африки» | «з чорної раси, Я думаю, з Африки» |
| 5 | 43 | «Чи потрібно проводити цю пуджу?» | «Чи потрібно проводити цю Пуджу?» |
| 6 | 43 | «якщо є якась пуджа» | «якщо є якась Пуджа» |
| 7 | 43 | «щоб ця пуджа була виконана» | «щоб ця Пуджа була виконана» |

## Summary

- Language (L): 4 issues raised, 0 approved by Critic
- SY Domain (S): 9 issues raised, 7 approved by Critic
- Total corrections applied: 7

All approved corrections fall into two clear categories:
1. **Shri Mataji's «Я»** (4 fixes): mid-sentence pronoun «я» referring to the
   speaker (Shri Mataji) was lowercased. Per CLAUDE.md, Shri Mataji's pronouns
   are ALWAYS capitalized — no exceptions for parentheticals like «я думаю».
2. **«Пуджа» capitalization** (3 fixes): paragraph 43 lowercased «пуджа»
   three times while the rest of the transcript (including the same paragraph,
   «наступної Пуджі Аді Шакті») uses uppercase. Glossary rule and internal
   consistency both demand uppercase.
