# Checking the reference intakes

`reference_intakes.csv` holds the recommended daily intakes gap-analysis uses as targets. The values
were filled in from the NHMRC Nutrient Reference Values, but **none of them have been checked against
the official tables yet**, so every row has `verified` set to `false`.

Official tables: https://www.eatforhealth.gov.au/nutrient-reference-values

## How to check

For each nutrient, open its NHMRC page, compare the RDI or AI (and the upper limit) for each age band
and sex, fix any wrong numbers in the CSV, then change `false` to `true` in the `verified` column.
After editing, reload with `docker compose run --rm etl --replace`.

## Checklist

- [ ] fibre (AI)
- [ ] calcium
- [ ] iron
- [ ] magnesium (upper limit left empty: NHMRC's UL is for supplements only, not food)
- [ ] phosphorus
- [ ] potassium (AI)
- [ ] **sodium: empty on purpose.** NHMRC gives an AI *range* (460 to 920 mg) and a separate
      "suggested dietary target". Decide which number gap-analysis should use, then fill it in.
- [ ] zinc
- [ ] copper (AI)
- [ ] manganese (AI)
- [ ] selenium
- [ ] iodine (low priority: USDA barely has iodine data, so gap-analysis skips it anyway)
- [ ] vitamin A (the UL applies to preformed vitamin A, i.e. retinol)
- [ ] vitamin C (no UL set)
- [ ] vitamin D (AI)
- [ ] vitamin E (AI; the 14 to 18 upper limit is left empty)
- [ ] vitamin K (AI)
- [ ] thiamin
- [ ] riboflavin
- [ ] niacin (UL left empty: it's for supplement forms only)
- [ ] pantothenic acid (AI)
- [ ] vitamin B6
- [ ] folate (UL left empty: it's for folic acid from supplements and fortified food only)
- [ ] vitamin B12
- [ ] choline (AI)

Energy, protein, carbs and fat aren't in this file. gap-analysis works those out from each
person's profile (weight, height, age, activity level and goal).
