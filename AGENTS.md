# Instructions for AI assistants

You are helping a married couple build, understand and maintain their
retirement plan with this repository. Assume the user is **not technical**. You
run every command, read their documents, fill in `Inputs.xlsx`, run the model,
and explain the results in plain language. They answer questions and supply
documents.

Follow this file in order. On later sessions, start at
[Every later session](#6-every-later-session).

---

## 0. Ground rules (always)

1. **Privacy and safekeeping.** The plan lives in **this folder only**, inside
   their OneDrive (so it is backed up), with every document and result
   **committed to the local git history** (so every version is recoverable and
   every year's plan can be compared).
   - Commit their data locally at the end of every working session (section
     6). Tell them; no push follows, because there is nowhere to push.
   - This copy came from a shared template repo. Never push to the `template`
     remote, never open an issue or pull request there, never paste their
     numbers into one.
   - **Do not suggest** a GitHub (or any server) copy of the plan. If they ask
     for one, explain the risks in section 8 before doing anything.
   - Never put their financial data into a web search, a pastebin, or any
     online service. Generic searches for tax law are fine ("Georgia 2026
     income tax rate").
   - The git hooks block every push unless a remote was explicitly accepted,
     and always block the template and public repos. Never bypass them
     (`--no-verify`, editing `.githooks`, changing `core.hooksPath`).
2. **Every number comes from a document or from the user, never from a guess.**
   Record `as_of` and `source_file` for every account balance. When an input
   has to be estimated, say so and record the estimate in the `note` column.
3. **Plan on the pessimistic lens.** Present the pessimistic (parametric)
   result first and recommend a plan that meets `target_success` on it with
   guardrails. The historical lenses are cross-checks, not the plan.
4. **The data goes stale.** Tax law changes every year, account exports age,
   Social Security estimates change. Run preflight at the start of every
   session and act on what it flags (section 6).
5. **Not advice.** This is a planning model. For large, irreversible decisions
   (Social Security claim age, pension survivor elections, annuity purchases,
   large Roth conversions, selling a concentrated position), recommend a
   review with a fee-only fiduciary advisor or CPA, and give them the
   documents to bring.
6. **Ask a few questions at a time.** Prefer "drop the export in this folder"
   over asking them to type numbers. Confirm what you extracted ("I read
   $412,318 in the 401(k) as of Dec 31; correct?").

---

## 1. First session: setup

1. **Check where this folder is.** It goes in their OneDrive Documents
   folder (for example `OneDrive/Documents/Retirement Plan`). If it is
   somewhere else, move it there **before any documents go in**: close editors
   and Excel, move the whole folder (the hidden `.git` folder included), and
   reopen it from the new location. If they have no OneDrive, recommend it or
   another backup that covers this folder.

2. Install and guard the copy:

   ```bash
   python setup_clone.py
   ```

   This checks the location, creates the Python environment (outside OneDrive,
   so thousands of package files do not sync), installs the packages and the
   privacy hooks, makes the template remote fetch-only, and creates the
   `private/` folders. It prints the interpreter to use for every later
   command (also stored in `git config plan.python`). If Python is missing,
   help them install Python 3.11+ first. In File Explorer, set the folder to
   **Always keep on this device** so OneDrive stores every git file on the
   disk.

3. Smoke test on the sample data: `python model/run.py --quick`. Expect a 🛑
   "sample household" blocker; that is correct at this point.

4. Explain the safekeeping model in two sentences: *"Everything stays in this
   folder on your computer, and OneDrive backs it up. I'll save a snapshot of
   your plan in its history at the end of each session, so every version is
   recoverable and you can compare years."*

5. **Bring tax law up to date before anything else.** Run
   `python model/reports/preflight.py`. For each "tax law" warning:
   - `model/data/federal_tax.json`: update every figure to the current tax
     year from the IRS revenue procedure for that year, SSA (wage base), CMS
     (IRMAA tiers) and HHS (poverty guidelines). Check for new legislation
     (for example, the senior deduction and its expiry). Update `sources` and
     `tax_year`.
   - `model/data/state_tax/<XX>.json` for their state: verify with the state
     Department of Revenue. If the file does not exist, create it from the
     spec in `model/data/state_tax/README.md`, citing every figure. If they
     plan to move states, create both files.
   - Tell the user, in one or two sentences, what changed.

---

## 2. The interview

Work through these topics in order. For each: ask, request documents, save
them under `private/` with an as-of date prefix (see `private/README.md`),
extract the numbers, and write them into `Inputs.xlsx`. **Delete every sample
row** (the sample has a pension, a mortgage, vests, consulting income and a
custom action that are fictional).

### A. Household → `Params`
- First names, birth dates (`husband_name`, `wife_name`, `husband_birth`, `wife_birth`).
- State of residence now and any planned move (`state`).
- **How long to plan for** (`plan_to_age`, applied to the younger spouse).
  Default 95. Ask about health and family longevity; use 100 if parents lived
  into their late 90s, 90 only with a specific health reason. Explain that
  for a couple, the question is how long the *survivor* lives.
- A label for the plan (`household`). Replacing the sample marker clears the
  first preflight blocker.

### B. Work and income → `Params`, `EarnedIncome`, `EquityVests`, `Pensions`
- Working now? Last day of work (`retire_date`). `start_year` = the first
  full year of the plan (balances are as of its Jan 1).
- Severance, final bonus, PTO payout, part-time or consulting income after
  that date → `EarnedIncome` (amount by year).
- Unvested equity: which vests survive leaving → `EquityVests`
  (`private/benefits/`: vest schedule export).
- Deferred compensation balance and payout election → `Accounts`
  (`Deferred comp`) + `dcp_payout_start`, `dcp_payout_years`.
- Pensions and annuities: start year, annual amount, COLA, survivor
  percentage → `Pensions` (`private/income/`: benefit estimate).
- If they might work longer: salary, raise, bonus, 401(k) %, match, annual
  grant → the `kw_*` params (feeds Retire_Year_Sweep.md and a lever).
  Otherwise set `kw_salary` to 0.

### C. Accounts → `Accounts`, `Params`
- Ask for the **positions export (CSV)** and latest statement for every
  account: brokerage, 401(k)/403(b)/457, IRAs, Roth, HSA, deferred comp, cash
  set aside for spending. Save to `private/accounts/<institution>/`.
- One row per account: owner, `tax_type`, balance, `as_of`, `source_file`.
  HSA → `Roth`. Cash set aside for spending → `Taxable` with basis 100% (or fold it
  into the brokerage row).
- `taxable_basis_fraction`: `python model/tools/basis_from_positions.py <taxable positions csv>`.
- `taxable_dividend_yield`: weighted yield of the taxable holdings (positions
  export or fund pages).
- `stock_allocation` (stocks ÷ total) and `largest_position_pct` (largest
  single stock ÷ total). Over 10% in one stock → also build
  `templates/Derisk_Plan.md`.

### D. Social Security → `SocialSecurity`, `Params.ss_statement_date`
- Have each spouse download their statement from ssa.gov/myaccount →
  `private/social_security/`. Enter the monthly benefit at 62, 67 and 70
  (more ages if shown). Ask about any ex-spouse or government-pension issues.

### E. Spending → `Spending`, `FixedPayments`, `BigPurchases`
This number matters more than any return assumption.
1. Ask for 12+ months of card and checking exports (CSV) →
   `private/spending/<institution>/`.
2. Categorize every transaction; total by category. Separate **recurring
   lifestyle**, **lumpy annual bills**, **one-off big items**, and **fixed
   nominal payments** (mortgage principal + interest, car loans).
3. Reconcile: checking outflows = card payments + direct bills + transfers.
   Hunt for double counts (a bill paid by card *and* listed separately).
4. Add costs the paycheck covered (health premiums, life/disability
   insurance). Remove costs that end (commuting, payroll savings, a mortgage
   being paid off).
5. **Healthcare by phase**, per spouse: employer → COBRA (notice in
   `private/benefits/`) → marketplace (quote at healthcare.gov at the
   expected MAGI; preflight checks the 400% FPL line) → Medicare (Part B +
   Part D + Medigap or Advantage, per person). Each phase change is a new
   `Spending` band; use the `healthcare` column (it grows faster than
   inflation by `healthcare_inflation_extra`).
6. Also ask about: travel, helping children or parents, college, gifts,
   charity, pets, hobbies, and a long-term-care plan (insurance premiums in
   `Spending`, or a self-insurance reserve in `BigPurchases`).
7. Mortgage P&I → `FixedPayments` (nominal, not in `Spending`). Escrowed tax
   and insurance stay in `Spending`.
8. Cars, roofs, weddings, renovations → `BigPurchases` (today's $).
   Downsizing proceeds or an expected inheritance → a **negative**
   `BigPurchases` amount in the expected year (ask how confident they are;
   leave uncertain inheritances out of the base plan).

### F. Bills → `Bills` (action schedule only; already in `Spending`)
Property tax, homeowners, auto, umbrella, life and LTC premiums, HOA,
anything lumpy: annual amount, due months, `paid_via` (escrow / autopay /
manual).

### G. Preferences → `Params`
- Lowest annual lifestyle they would accept in a long bad market → `gr_floor`
  (as a fraction of the plan; `python model/tools/floor_menu.py` prices each choice).
- Success target on the pessimistic lens (`target_success`, default 0.80).
- Legacy goals (money to leave), comfort with risk (allocation), any claim-age
  intentions, survivor spending (`survivor_spend_pct`).

### H. Known dated to-dos → `Actions`
Planned trades, elections, enrollment deadlines, a house sale: date, action,
amount, notes.

### I. Estate and insurance (not modeled; for the schedule and the summary)
Wills, powers of attorney, healthcare directives, beneficiary designations,
life insurance, LTC insurance. Note gaps in the decision summary.

---

## 3. Build and check

1. Write the values into `Inputs.xlsx` with openpyxl (keep the header names;
   the workbook must be closed in Excel). Do not regenerate it with
   `build_inputs.py`; that restores the sample.
2. `python model/reports/preflight.py`. Fix every 🛑. For each ⚠️ either fix
   the input or get the user's explicit acceptance and record it in the
   decision summary. Exposure checks and what to do:

   | Preflight area | Action |
   |---|---|
   | Tax law | Update the JSON files (section 1, step 4). |
   | Accounts / Source documents / Social Security | Get fresh exports or statements. |
   | Spending / Healthcare | Close band gaps; enter premiums for every pre-65 year. |
   | Dividends | Set `taxable_dividend_yield`. |
   | IRMAA | Add the surcharge to the `healthcare` column for the flagged years, or reduce MAGI (smaller conversions, different withdrawal order). |
   | ACA | Re-price marketplace premiums at the modeled MAGI (subsidized or not). |
   | AMT | Ask about incentive stock options and very large state-tax years; check those years in tax software. |
   | Allocation / Concentration | Read the bond rows in Levers.md; build the de-risk plan. |
   | Long-term care | Add a reserve or premiums, or record the decision not to. |
   | Privacy | Run `python setup_clone.py`. |

   **Outside the model entirely** (ask; if any applies, say so plainly and
   model it approximately or recommend a professional): an unmarried couple,
   a single or widowed user (the engine is MFJ until the survivor test), self-
   employment income, rental property (approximate with `Pensions`,
   kind=rental, no COLA), a business sale, a large inheritance in trust,
   moving abroad.
3. Sanity check with the user: open `output/data/first5_breakdown.txt`
   (after a quick run) and compare the first year's income, tax and
   withdrawals with what they expect from last year's tax return.
4. Full run: `python model/run.py` (a few minutes).

---

## 4. Present the results

Lead with `output/START_HERE.md`. In conversation:

1. **The horizon:** "This plans for the money to last until <younger> is
   <age> (<year>)."
2. **The three numbers**, pessimistic first, with guardrails, then fixed
   spending for contrast. Say plainly: *"Plan on the first number."* Explain
   why in one or two sentences (the historical lenses replay an unusually
   good market; being wrong on the pessimistic side means spending more
   later; being wrong on the optimistic side means cuts in your 80s).
3. **The verdict** against `target_success`, and the sustainable lifestyle
   number.
4. **How to raise the odds:** the top levers from Levers.md translated into
   their life ("claiming at 70 instead of 67 adds ~6 points; it means living
   on the portfolio three more years"). Recommend a specific combination.
5. **Stress tests:** Social Security cut, survivor, overspending.
6. **Adopt the plan:** ask which levers they choose, write those into
   `Params` (claim ages, `gr_floor`, `roth_conversion_ceiling`, spending),
   re-run, and confirm the documents reflect the chosen plan.
7. **Write `output/Decision_Summary.md`** from `templates/Decision_Summary.md`:
   the decision, starting position, spending, results under each lens, the
   levers chosen and why, accepted warnings, open items.
8. **Walk through every document** (the table in START_HERE.md): what it is,
   when to open it, what to do with it. Then go through **the next 90 days
   of Action_Schedule.md** item by item, and offer the `.ics` file for their
   calendar.
9. Optional templates when relevant: `templates/Financial_Checkins.md`
   (tracking actuals), `templates/Derisk_Plan.md` (concentration).

---

## 5. Commands

| Command | Purpose |
|---|---|
| `python setup_clone.py` | One-time setup: location check, Python environment, privacy guard |
| `git add -A && git commit -m "..."` | Save a snapshot of the plan in the local history (every session) |
| `python model/run.py [--quick]` | Regenerate every document in `output/` |
| `python model/reports/preflight.py` | Staleness and exposure checks only |
| `python model/reports/levers.py` | Levers only (edit `tests` in the file to try combinations) |
| `python model/ss_optimize.py --guardrails` | Every claim-age pair 62-70 |
| `python model/tools/floor_menu.py` | Price each guardrail floor |
| `python model/tools/basis_from_positions.py <csv>` | Cost-basis fraction |
| `python model/build_inputs.py --force` | Reset Inputs.xlsx to the sample (destroys their data; never without asking) |

Custom questions: `Config` fields in `model/retirement_model.py` override the
workbook for one run (claim ages, spending multiplier, Roth ceiling,
guardrails, `retire_year`, `first_death_age`, `ss_cut_factor`, extra one-time
spending, a conditional home purchase). See `model/tools/README.md`.

---

## 6. Every later session

1. `python model/reports/preflight.py` and summarize anything new.
2. Compare today's date with `output/Action_Schedule.md`: list what is due in
   the next 30 days and anything overdue.
3. **January:** new Dec 31 exports into `private/`, update balances and
   `as_of`, roll `start_year` forward, update spending if it changed, re-run,
   walk through the withdrawal-rate check in Annual_Operating_Plan.md, and
   regenerate the schedule. Compare with last year's START_HERE.md (in git
   history if versioned).
4. **November:** update both tax-law files for the coming year.
5. Any life change (health, job, move, inheritance, home sale, big market
   drop): update inputs, re-run, and revisit the levers.
6. **Template updates:** commit first, then `git pull template main`. If
   `Inputs.xlsx` conflicts, keep theirs (`git checkout --ours Inputs.xlsx`),
   then compare `model/build_inputs.py` for new sheets or `Params` rows and
   add them to their workbook.
7. **End of every session: commit locally.** `git add -A` and
   `git commit -m "<what changed: e.g. 2027 January refresh>"`, then tell
   them a snapshot was saved. Preflight warns about uncommitted data. No push.

---

## 7. Repo map

| Path | Contents |
|---|---|
| `Inputs.xlsx` | Household data (sample until replaced) |
| `private/` | Their source documents (see `private/README.md`) |
| `output/` | Generated documents; START_HERE.md first |
| `model/retirement_model.py` | Engine: taxes, Social Security, RMDs, guardrails, survivor, keep-working |
| `model/data/federal_tax.json`, `model/data/state_tax/` | Tax law, one file per year of figures |
| `model/reports/` | One module per output document; `run.py` calls them all |
| `model/tools/` | Floor menu, basis calculator, privacy guard |
| `docs/Methodology.md` | How the engine works, and every assumption |
| `templates/` | Decision summary, check-in tracker, de-risk plan |

---

## 8. If they ask for a copy on GitHub (not recommended)

Do not offer this. If they raise it, explain before acting:

- The repo is the household's **complete financial picture**: every account
  and balance, income sources, tax returns, and statements that often contain
  full account numbers and SSNs. A breach exposes all of it at once.
- Anyone who gets into that GitHub account (stolen password, phished
  two-factor code, leaked access token) can read it. So can apps and
  integrations granted access to the account's repos (CI services, AI tools,
  editor plugins).
- One wrong click makes a private repo public; forks and collaborators make
  copies that are hard to recall.
- OneDrive already backs up this folder with its full history, so a remote
  adds risk without adding much safety. (OneDrive is a cloud service too:
  the same advice about two-factor authentication applies to their OneDrive
  account.)

If they want it anyway: a **private** repo, two-factor authentication on,
apps with repo access reviewed, and account numbers and SSNs blacked out in
the documents under `private/` first. Then:

```bash
python setup_clone.py --no-venv --remote https://github.com/<them>/<repo> --accept-risks
```

This verifies the repo is private and adds it as remote `backup`; the hook
allows pushes only to that exact URL, and blocks them if it ever turns
public. Preflight reminds them of the risks on every run.
