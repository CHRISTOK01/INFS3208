# The reference intakes

> Part of the MacroScope docs. Start at the [main README](../README.md); the food data as a whole is described in [etl/README.md](README.md).

`reference_intakes.csv` holds the NHMRC values gap-analysis uses as targets, by sex, age band
(14-18, 19-30, 31-50, 51-70, 71+) and life stage (none, pregnant, breastfeeding). They come from the
NHMRC Nutrient Reference Values for Australia and New Zealand:
https://www.eatforhealth.gov.au/nutrient-reference-values

| Column | What it is |
|---|---|
| `life_stage` | `none`, or `pregnant` / `breastfeeding` (women aged 14-50 only, like the NHMRC tables) |
| `rni_or_ai` | the daily target: the RDI where NHMRC gives one, otherwise the AI (`intake_type` says which) |
| `upper_limit` | the most that's safe from food each day (empty if there isn't one) |
| `sdt` | NHMRC's "suggested dietary target" for lowering the risk of chronic disease, for adults (fibre, vitamins A, C and E, potassium, omega-3). gap-analysis shows it as a longer-term "aim" |
| `unit` | mg, ug or g, except protein, which is in **g per kg** of body weight |

## How they were checked (16 October 2026)

Each nutrient's page on eatforhealth.gov.au was downloaded, and a script read every RDI, AI and
upper limit out of its tables, including the pregnancy and breastfeeding tables. The values for
people who aren't pregnant matched the earlier hand-checked version exactly. All rows are marked
`verified = true`.

After editing the CSV, reload it with `docker compose run --rm etl --replace`.

## Choices worth knowing about

- **Upper limits left empty on purpose.** NHMRC's upper limits for magnesium, niacin and folate only
  apply to supplements and fortified foods (as magnesium salts, nicotinic acid and folic acid), not
  to normal food. Using them would flag healthy meals as "too much", so they're left empty.
- **Sodium.** NHMRC doesn't give one target, just an AI range of 460 to 920 mg, which nearly everyone
  goes over. What matters is eating too much, so sodium has no target, only an upper limit:
  2,300 mg (the UL) for 14-18 year olds, and 2,000 mg (the "suggested dietary target") for adults,
  who have no UL.
- **Protein in pregnancy** is NHMRC's value for the 2nd and 3rd trimesters. In the 1st trimester
  gap-analysis uses the normal value, as NHMRC does.
- **Vitamin K and choline** are in the file, but gap-analysis doesn't use them, because the
  Australian food data doesn't have them.
- **Energy, fat, carbs, and the limits on saturated fat, free sugars, alcohol and caffeine** aren't
  in this file. gap-analysis works those out from each person's profile. The rules and their
  sources are at the top of `services/gap-analysis/app/targets.py`.
