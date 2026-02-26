# Language Review — {{SLUG}}, {{DATE}}

## Process

Review `transcript_uk.txt` (full paragraphed Ukrainian text) using 2 parallel reviewers + 1 critic filter.

### Input Format

Full paragraphed text from `transcript_uk.txt`:
```
Перший абзац українського тексту. Він містить кілька речень.

Другий абзац. Тут продовження перекладу.
```

### Review Agents

**Reviewer L — Language (Orthography + Grammar + Punctuation)**
Check for:
- Spelling errors, incorrect word forms, Latin characters mixed with Cyrillic
- Incorrect prefixes (напів-, пів-), doubled consonants
- Missing/extra commas, double periods, incorrect ellipsis (`...` without space before)
- Missing spaces after punctuation, extra spaces before punctuation
- Quotation mark consistency (use `«»`)
- Em-dash with spaces (` — `)
- Incorrect case forms, verb conjugations, gender agreement
- Reflexive verbs: `-ся` not `-сь` (e.g., `дотримуєтеся` not `дотримуєтесь`)

**Reviewer S — SY Domain (Capitalization + Terminology + Consistency)**
Check for:
- Deity pronoun capitalization:
  - Shri Mataji: ALWAYS uppercase (Я/Мені/Мій/Моя/Вона/Її/Їй)
  - Individual Incarnations singular: uppercase (Він/Його/Йому)
  - Incarnations plural mid-sentence: lowercase (вони/їм/їх)
  - Regular people: always lowercase
- Glossary terms: correct Ukrainian equivalents per `glossary/`
- Language names: lowercase in Ukrainian (англійська, not Англійська)
- SY terminology consistency across the entire text
- Mixed styles (quotation marks, dashes) within the same transcript

**Critic — Filter + Validate**
Reviews ALL corrections from Reviewer L and Reviewer S together:
- Removes false positives (corrections where original was actually correct)
- Removes trivial findings (style preferences, not errors)
- Validates each correction is genuinely needed with clear justification
- Catches conflicts between L and S suggestions
- Has final say on which corrections to apply

### Flow

1. Reviewers L and S run **in parallel** on `transcript_uk.txt`
2. Both produce corrections tables
3. Critic reviews both tables together, keeps only real issues
4. Apply filtered corrections to `transcript_uk.txt`

## Results

### L. Language (Orthography + Grammar + Punctuation)
| # | Paragraph | Error | Context | Fix |
|---|-----------|-------|---------|-----|
| | | | | |

### S. SY Domain (Capitalization + Terminology + Consistency)
| # | Paragraph | Error | Context | Fix |
|---|-----------|-------|---------|-----|
| | | | | |

### Critic Filter
| Source | # | Verdict | Reason |
|--------|---|---------|--------|
| | | Keep/Remove | |

### Approved Corrections
| # | Paragraph | Error | Fix |
|---|-----------|-------|-----|
| | | | |

## Summary

- Language (L): ___ issues found, ___ approved by Critic
- SY Domain (S): ___ issues found, ___ approved by Critic
- Total corrections applied: ___
